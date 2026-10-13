"""Audits a program's requirement tree against a student's completed courses.

Each completed course fills the first requirement slot that lists it, in
catalogue order, so no course counts twice. A requirement with a unit
count is met by units earned in it and its nested requirements; one
without needs every slot filled; one with only prose rules is left for a
person to judge. Prerequisites decide which of the program's remaining
courses are locked. This module is pure; catalog_db supplies the data.
"""

import collections
from collections.abc import Mapping, Sequence

from server.src.catalog import codes
from server.src.data import catalog_models as m


Status = m.RequirementStatus


def _key(ref: m.CourseRef) -> str:
  return codes.identity(ref.resolved or ref.code)


def unmet_prerequisites(
  requisites: m.Requisites, done: set[str]
) -> list[m.RequisiteGroup]:
  """Prerequisite groups completed courses (by identity) do not meet.

  Corequisites and concurrent courses may be taken alongside, so they never
  lock a course.
  """
  return [
    group
    for group in requisites.prerequisite
    if sum(all(_key(r) in done for r in option) for option in group.options)
    < group.required_count
  ]


def audit(
  program: m.Program,
  completed: Sequence[str],
  units: Mapping[str, m.Units],
  requisites: Mapping[str, m.Requisites],
) -> m.ProgramAudit:
  """Audits `program` for a student.

  Args:
    program: The program and its requirement tree.
    completed: Course codes the student took.
    units: Course identity to its units; a variable-unit course
      counts its minimum. Courses missing here count the catalogue's units
      for the slot they fill, or nothing.
    requisites: Course identity to requisites in the planning term.
  """
  shown = {codes.identity(c): c for c in completed}
  claimed: set[str] = set()
  own: dict[int, list[str]] = collections.defaultdict(list)
  own_units: dict[int, float] = collections.defaultdict(float)
  filled: dict[int, int] = collections.defaultdict(int)
  slot_units: dict[str, float] = {}
  for req in program.requirements:
    for slot in req.slots:
      hit = next(
        (
          c
          for c in slot
          if _key(c.course) in shown and _key(c.course) not in claimed
        ),
        None,
      )
      if hit is None:
        continue
      key = _key(hit.course)
      claimed.add(key)
      own[req.position].append(shown[key])
      filled[req.position] += 1
      if key in units:
        slot_units[key] = units[key].min
      elif hit.units is not None:
        slot_units[key] = hit.units.min
      own_units[req.position] += slot_units.get(key, 0.0)

  children: dict[int | None, list[int]] = collections.defaultdict(list)
  for req in program.requirements:
    children[req.parent].append(req.position)
  progress: dict[int, m.RequirementProgress] = {}
  courses_below: dict[int, int] = {}
  # Children follow their parent in catalogue order, so walk backwards.
  for req in reversed(program.requirements):
    kids = [progress[p] for p in children[req.position]]
    judged = [k for k in kids if k.status != Status.MANUAL]
    earned = own_units[req.position] + sum(k.units for k in kids)
    count = len(own[req.position]) + sum(
      courses_below[p] for p in children[req.position]
    )
    courses_below[req.position] = count
    if req.units is not None:
      own_ok = earned >= req.units.min
    elif req.slots:
      own_ok = filled[req.position] == len(req.slots)
    elif judged:
      own_ok = True
    else:
      progress[req.position] = m.RequirementProgress(
        position=req.position, status=Status.MANUAL, units=earned, courses=[]
      )
      continue
    if own_ok and all(k.status == Status.DONE for k in judged):
      status = Status.DONE
    elif count:
      status = Status.PARTIAL
    else:
      status = Status.TODO
    progress[req.position] = m.RequirementProgress(
      position=req.position,
      status=status,
      units=earned,
      courses=own[req.position],
    )

  done = set(shown)
  locked: dict[str, list[str]] = {}
  for req in program.requirements:
    for slot in req.slots:
      for choice in slot:
        key = _key(choice.course)
        if key in done or key not in requisites:
          continue
        if unmet := unmet_prerequisites(requisites[key], done):
          locked[choice.course.resolved or choice.course.code] = list(
            dict.fromkeys(
              ref.resolved or ref.code
              for group in unmet
              for option in group.options
              for ref in option
              if _key(ref) not in done
            )
          )
  total = sum(
    units[k].min if k in units else slot_units.get(k, 0.0) for k in shown
  )
  return m.ProgramAudit(
    units=total,
    requirements=[progress[r.position] for r in program.requirements],
    locked=locked,
  )
