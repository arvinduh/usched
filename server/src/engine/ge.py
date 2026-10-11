"""USC General Education audit engine and requirement rules evaluator.

This module evaluates student progress across USC Core Literacies (GE-A
through GE-F) and Global Perspectives (GE-G and GE-H), correctly resolving
double-counting rules and Advanced Placement (AP) exam equivalencies.
"""

from collections.abc import Mapping, Sequence

from server.src.data import models


GE_REQUIREMENT_RULES: tuple[tuple[str, str, int], ...] = (
  ("GE-A", "The Arts", 1),
  ("GE-B", "Humanistic Inquiry", 2),
  ("GE-C", "Social Analysis", 2),
  ("GE-D", "Life Sciences", 1),
  ("GE-E", "Physical Sciences", 1),
  ("GE-F", "Quantitative Reasoning", 1),
  ("GE-G", "Global Perspectives I: Citizenship in a Global Era", 1),
  ("GE-H", "Global Perspectives II: Traditions and Historical Foundations", 1),
)

CORE_LITERACIES: frozenset[str] = frozenset(
  {"GE-A", "GE-B", "GE-C", "GE-D", "GE-E", "GE-F"}
)
GLOBAL_PERSPECTIVES: frozenset[str] = frozenset({"GE-G", "GE-H"})


def evaluate_ge_audit(
  completed_courses: Sequence[str],
  course_ge_map: Mapping[str, Sequence[str]],
  ap_credits: Sequence[models.UserApCredit],
  ap_definitions: Sequence[models.ApExamDefinition],
) -> models.GeAuditSummary:
  """Audits courses and AP credits against USC General Education rules.

  Correctly honors USC's double-counting policy: an eligible course satisfying
  both a Core Literacy (GE-A..F) and a Global Perspective (GE-G..H) can satisfy
  one requirement in each respective group simultaneously.

  Args:
    completed_courses: List of course identifiers completed by student.
    course_ge_map: Map of course_id -> list of fulfilled GE categories.
    ap_credits: User AP exam credits with scores.
    ap_definitions: Official AP exam definitions with fulfilled GE categories.

  Returns:
    Evaluated GeAuditSummary with category-level breakdowns and completion
    flags.
  """
  ap_def_map = {d.id: d for d in ap_definitions}
  ap_ge_satisfied: dict[str, list[str]] = {}

  for cred in ap_credits:
    if cred.score < 4:
      continue
    defn = ap_def_map.get(cred.exam_id)
    if defn and defn.fulfills_ge_category:
      ap_ge_satisfied.setdefault(defn.fulfills_ge_category, []).append(
        defn.name
      )

  # Track which courses satisfy Core Literacies vs Global Perspectives
  core_allocations: dict[str, list[str]] = {}
  global_allocations: dict[str, list[str]] = {}

  rule_limits = {code: req for code, _, req in GE_REQUIREMENT_RULES}

  # First pass: Allocate AP credits to Core Literacies
  for ge_code, ap_names in ap_ge_satisfied.items():
    if ge_code in CORE_LITERACIES:
      core_allocations.setdefault(ge_code, []).extend(ap_names)

  # Second pass: Allocate completed courses
  for course_id in completed_courses:
    cats = course_ge_map.get(course_id, [])
    if not cats:
      continue

    # Course may satisfy one Core Literacy
    assigned_core = False
    for cat in cats:
      if cat in CORE_LITERACIES and not assigned_core:
        current_len = len(core_allocations.get(cat, []))
        if current_len < rule_limits.get(cat, 0):
          core_allocations.setdefault(cat, []).append(course_id)
          assigned_core = True

    # Course may also satisfy one Global Perspective (double-counting allowed)
    assigned_global = False
    for cat in cats:
      if cat in GLOBAL_PERSPECTIVES and not assigned_global:
        current_len = len(global_allocations.get(cat, []))
        if current_len < rule_limits.get(cat, 0):
          global_allocations.setdefault(cat, []).append(course_id)
          assigned_global = True

  # If any slots remain unfilled, allow surplus courses in multi-category
  for course_id in completed_courses:
    cats = course_ge_map.get(course_id, [])
    for cat in cats:
      if cat in CORE_LITERACIES:
        if course_id not in core_allocations.get(cat, []):
          if len(core_allocations.get(cat, [])) < rule_limits.get(cat, 0):
            core_allocations.setdefault(cat, []).append(course_id)
      elif cat in GLOBAL_PERSPECTIVES:
        if course_id not in global_allocations.get(cat, []):
          if len(global_allocations.get(cat, [])) < rule_limits.get(cat, 0):
            global_allocations.setdefault(cat, []).append(course_id)

  categories_progress: list[models.GeCategoryProgress] = []
  total_required = 0
  total_satisfied = 0

  for cat_code, cat_name, required in GE_REQUIREMENT_RULES:
    total_required += required
    if cat_code in CORE_LITERACIES:
      satisfied_items = core_allocations.get(cat_code, [])
    else:
      satisfied_items = global_allocations.get(cat_code, [])

    course_items = [i for i in satisfied_items if not i.startswith("AP ")]
    ap_items = [i for i in satisfied_items if i.startswith("AP ")]

    completed_count = min(len(satisfied_items), required)
    total_satisfied += completed_count
    is_satisfied = completed_count >= required

    categories_progress.append(
      models.GeCategoryProgress(
        category=cat_code,
        name=cat_name,
        required_count=required,
        completed_count=completed_count,
        satisfying_courses=course_items,
        satisfying_ap=ap_items,
        is_satisfied=is_satisfied,
      )
    )

  return models.GeAuditSummary(
    total_required=total_required,
    total_satisfied=total_satisfied,
    categories=categories_progress,
    is_complete=total_satisfied >= total_required,
  )
