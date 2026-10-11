"""Degree progress audit and curriculum prerequisite fulfillment engine.

This module evaluates student completed courses against degree requirements,
calculates units and completion percentages, and builds the prerequisite DAG,
adhering to pure, deterministic business logic without external I/O.
"""

import pydantic

from server.src.data import models


class PrereqNode(pydantic.BaseModel):
  """DAG node representation for prerequisite visualization."""

  course_id: str = pydantic.Field(description="Course code identifier.")
  title: str = pydantic.Field(description="Course descriptive title.")
  units: float = pydantic.Field(description="Credit units the course carries.")
  status: models.CourseStatus = pydantic.Field(
    description="Completion state: completed, eligible, or locked."
  )
  prerequisites: list[list[str]] = pydantic.Field(
    default_factory=list,
    description=(
      "Prerequisite groups that must all be met; any one course satisfies"
      " a group."
    ),
  )


class DegreeAuditResponse(pydantic.BaseModel):
  """Comprehensive degree progress evaluation output."""

  degree: models.DegreeProgram = pydantic.Field(
    description="Evaluated degree program roadmap."
  )
  total_completed_units: float = pydantic.Field(
    description="Sum of credit units verified completed."
  )
  percent_complete: float = pydantic.Field(
    description="Overall completion percentage toward graduation."
  )
  prereq_graph: list[PrereqNode] = pydantic.Field(
    default_factory=list,
    description="Interactive prerequisite DAG nodes and states.",
  )
  unfulfilled_prerequisites: list[str] = pydantic.Field(
    default_factory=list,
    description="Courses blocked by incomplete prerequisites.",
  )


def evaluate_course_eligibility(
  course: models.Course, completed_courses: set[str]
) -> tuple[models.CourseStatus, list[str]]:
  """Calculates completion state and missing prerequisites for course."""
  if course.id in completed_courses:
    return (models.CourseStatus.COMPLETED, [])

  missing_all: list[str] = []
  for clause in course.prerequisites_json:
    if not any(req in completed_courses for req in clause):
      missing_all.extend(clause)

  if missing_all:
    return (models.CourseStatus.LOCKED, list(dict.fromkeys(missing_all)))
  return (models.CourseStatus.ELIGIBLE, [])


def build_prerequisite_dag(
  courses: list[models.Course], completed_courses: list[str]
) -> list[PrereqNode]:
  """Constructs DAG representation for degree and catalogue visualizers."""
  completed_set = {c.upper().strip() for c in completed_courses}
  dag_nodes: list[PrereqNode] = []

  for course in courses:
    status, _ = evaluate_course_eligibility(course, completed_set)
    dag_nodes.append(
      PrereqNode(
        course_id=course.id,
        title=course.title,
        units=course.units,
        status=status,
        prerequisites=[list(clause) for clause in course.prerequisites_json],
      )
    )

  return dag_nodes


def audit_degree_progress(
  degree: models.DegreeProgram,
  completed_courses: list[str],
  course_map: dict[str, models.Course],
) -> DegreeAuditResponse:
  """Evaluates degree category completion and produces visual audit results."""
  completed_set = {c.upper().strip() for c in completed_courses}
  all_degree_course_ids: set[str] = set()
  claimed_completed: set[str] = set()

  # Pass 1: Identify all courses claimed by explicit course lists
  explicit_matches: dict[str, list[str]] = {}
  for cat in degree.categories:
    if cat.required_courses:
      matches: list[str] = []
      for req_cid in cat.required_courses:
        norm_cid = req_cid.upper().strip()
        all_degree_course_ids.add(norm_cid)
        if norm_cid in completed_set and norm_cid not in claimed_completed:
          matches.append(norm_cid)
          claimed_completed.add(norm_cid)
      explicit_matches[cat.name] = matches

  # Pass 2: Evaluate categories in original order
  evaluated_categories: list[models.DegreeCategory] = []
  total_completed_units = 0.0

  for cat in degree.categories:
    cat_completed_courses: list[str] = []
    cat_completed_units = 0.0

    if cat.required_courses:
      cat_completed_courses = explicit_matches.get(cat.name, [])
      for cid in cat_completed_courses:
        c_obj = course_map.get(cid)
        cat_completed_units += c_obj.units if c_obj else 4.0
    else:
      # Attribute-based matching (General Education) or pool matching.
      lower_name = cat.name.lower()
      is_ge = "general education" in lower_name or "ge" in lower_name
      is_elective = "elective" in lower_name

      for raw_cid in completed_courses:
        norm_cid = raw_cid.upper().strip()
        if norm_cid in claimed_completed:
          continue

        c_obj = course_map.get(norm_cid)
        units = c_obj.units if c_obj else 4.0

        if is_ge:
          has_ge = (
            (c_obj is not None and c_obj.ge_category is not None)
            or norm_cid.endswith(("G", "LG"))
            or norm_cid.startswith("GESM")
          )
          if has_ge and (
            cat_completed_units < cat.required_units or cat.required_units == 0
          ):
            cat_completed_courses.append(norm_cid)
            claimed_completed.add(norm_cid)
            cat_completed_units += units
        elif is_elective:
          if (
            cat_completed_units < cat.required_units or cat.required_units == 0
          ):
            cat_completed_courses.append(norm_cid)
            claimed_completed.add(norm_cid)
            cat_completed_units += units

    if cat_completed_units >= cat.required_units and cat.required_units > 0:
      status = models.CategoryStatus.COMPLETED
    elif cat_completed_units > 0:
      status = models.CategoryStatus.IN_PROGRESS
    else:
      status = models.CategoryStatus.PENDING

    total_completed_units += cat_completed_units
    evaluated_categories.append(
      models.DegreeCategory(
        name=cat.name,
        required_units=cat.required_units,
        completed_units=cat_completed_units,
        required_courses=cat.required_courses,
        completed_courses=cat_completed_courses,
        status=status,
      )
    )

  # Spillover electives: any remaining completed courses count toward
  # total degree units.
  for raw_cid in completed_courses:
    norm_cid = raw_cid.upper().strip()
    if norm_cid not in claimed_completed:
      c_obj = course_map.get(norm_cid)
      units = c_obj.units if c_obj else 4.0
      total_completed_units += units
      claimed_completed.add(norm_cid)

  percent = (
    round((total_completed_units / degree.total_units) * 100.0, 1)
    if degree.total_units > 0
    else 0.0
  )
  percent_complete = min(100.0, percent)

  dag_courses = [
    course_map[cid] for cid in all_degree_course_ids if cid in course_map
  ]
  prereq_graph = build_prerequisite_dag(dag_courses, completed_courses)

  unfulfilled: list[str] = []
  for node in prereq_graph:
    if node.status == models.CourseStatus.LOCKED:
      unfulfilled.append(node.course_id)

  evaluated_degree = models.DegreeProgram(
    id=degree.id,
    title=degree.title,
    school=degree.school,
    total_units=degree.total_units,
    categories=evaluated_categories,
  )

  return DegreeAuditResponse(
    degree=evaluated_degree,
    total_completed_units=total_completed_units,
    percent_complete=percent_complete,
    prereq_graph=prereq_graph,
    unfulfilled_prerequisites=unfulfilled,
  )
