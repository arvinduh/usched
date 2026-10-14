"""Audits a program's requirement tree against a student's completed courses.

Each completed course fills the first requirement slot that lists it, in
catalogue order, so no course counts twice. A requirement with a unit
count is met by units earned in it and its nested requirements; one
without needs every slot filled, or as many as its heading or notes pick
("Choose three of the following"); one with only prose rules is left for a
person to judge. Prerequisites decide which of the program's remaining
courses are locked. This module is pure; catalog_db supplies the data.
"""

import collections
import dataclasses
import re
from collections.abc import Mapping, Sequence

from server.db import models
from server.db.ingest import codes


_NUMBERS = {
  w: i
  for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve".split(),
    start=1,
  )
}
# "Choose one of the following:", "Select three courses from", "Take any two
# of", "Choose one:". "One course from each of" picks per group, not overall.
_PICK = re.compile(
  r"\b(?:choose|select|take|complete)\s+(?:at\s+least\s+|any\s+)?"
  rf"(\d+|{'|'.join(_NUMBERS)})\b"
  r"(?:\s+(?!of\b|from\b)[\w-]+){0,2}\s*(?:(?:of|from)\b(?!\s+each)|:)",
  re.IGNORECASE,
)


def _key(ref: models.CourseRef) -> str:
  return codes.identity(ref.resolved or ref.code)


def picks(req: models.Requirement) -> int:
  """How many of a requirement's slots it needs filled.

  Every slot, unless its heading or notes name one count to pick; two
  different counts are ambiguous, so every slot stays required.
  """
  counts = {
    int(n) if n.isdigit() else _NUMBERS[n.lower()]
    for n in _PICK.findall(f"{req.title}\n{req.notes}")
  }
  if len(counts) != 1:
    return len(req.slots)
  return min(counts.pop(), len(req.slots))


def _fill(
  program: models.Program, shown: Mapping[str, str]
) -> dict[int, dict[int, str]]:
  """Maps each requirement to its filled slots and the identity filling each.

  A requirement that picks fewer than all its slots, with no unit count,
  stops claiming once it has its pick, leaving extra courses for later
  requirements.
  """
  claimed: set[str] = set()
  filled: dict[int, dict[int, str]] = collections.defaultdict(dict)
  for req in program.requirements:
    need = None if req.units is not None else picks(req)
    for i, slot in enumerate(req.slots):
      if need is not None and len(filled[req.position]) >= need:
        break
      key = next(
        (
          _key(c.course)
          for c in slot
          if _key(c.course) in shown and _key(c.course) not in claimed
        ),
        None,
      )
      if key is not None:
        claimed.add(key)
        filled[req.position][i] = key
  return filled


def unmet_prerequisites(
  requisites: models.Requisites, done: set[str]
) -> list[models.RequisiteGroup]:
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
  program: models.Program,
  completed: Sequence[str],
  units: Mapping[str, models.Units],
  requisites: Mapping[str, models.Requisites],
  ge: Sequence[models.GeProgress] = (),
  ge_units: float = 0.0,
  exam_units: float = 0.0,
) -> models.ProgramAudit:
  """Audits `program` for a student.

  Args:
    program: The program and its requirement tree.
    completed: Course codes the student took.
    units: Course identity to its units; a variable-unit course
      counts its minimum. Courses missing here count the catalogue's units
      for the slot they fill, or nothing.
    requisites: Course identity to requisites in the planning term.
    ge: The student's GE audit, which decides GE requirements: done when
      every category is met.
    ge_units: Units filling GE seats, credited to GE requirements.
    exam_units: Units from passed AP exams, which count toward the total.
  """
  shown = {codes.identity(c): c for c in completed}
  own: dict[int, list[str]] = collections.defaultdict(list)
  own_units: dict[int, float] = collections.defaultdict(float)
  slot_units: dict[str, float] = {}
  fills = _fill(program, shown)
  for req in program.requirements:
    for i, key in fills[req.position].items():
      own[req.position].append(shown[key])
      hit = next(c for c in req.slots[i] if _key(c.course) == key)
      if key in units:
        slot_units[key] = units[key].min
      elif hit.units is not None:
        slot_units[key] = hit.units.min
      own_units[req.position] += slot_units.get(key, 0.0)

  children: dict[int | None, list[int]] = collections.defaultdict(list)
  for req in program.requirements:
    children[req.parent].append(req.position)
  progress: dict[int, models.RequirementProgress] = {}
  courses_below: dict[int, int] = {}
  # Children follow their parent in catalogue order, so walk backwards.
  ge_filled = sum(min(p.filled, p.required_count) for p in ge)
  ge_needed = sum(p.required_count for p in ge)
  for req in reversed(program.requirements):
    if req.is_general_education:
      courses_below[req.position] = ge_filled
      progress[req.position] = models.RequirementProgress(
        position=req.position,
        status=models.RequirementStatus.DONE
        if ge_needed and ge_filled >= ge_needed
        else models.RequirementStatus.PARTIAL
        if ge_filled
        else models.RequirementStatus.TODO,
        units=ge_units,
        courses=[],
      )
      continue
    kids = [progress[p] for p in children[req.position]]
    judged = [k for k in kids if k.status != models.RequirementStatus.MANUAL]
    earned = own_units[req.position] + sum(k.units for k in kids)
    count = len(own[req.position]) + sum(
      courses_below[p] for p in children[req.position]
    )
    courses_below[req.position] = count
    if req.units is not None:
      own_ok = earned >= req.units.min
    elif req.slots:
      own_ok = len(fills[req.position]) >= picks(req)
    elif judged:
      own_ok = True
    else:
      progress[req.position] = models.RequirementProgress(
        position=req.position,
        status=models.RequirementStatus.MANUAL,
        units=earned,
        courses=[],
      )
      continue
    if own_ok and all(
      k.status == models.RequirementStatus.DONE for k in judged
    ):
      status = models.RequirementStatus.DONE
    elif count:
      status = models.RequirementStatus.PARTIAL
    else:
      status = models.RequirementStatus.TODO
    progress[req.position] = models.RequirementProgress(
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
  total = exam_units + sum(
    units[k].min if k in units else slot_units.get(k, 0.0) for k in shown
  )
  return models.ProgramAudit(
    units=total,
    requirements=[progress[r.position] for r in program.requirements],
    locked=locked,
  )


@dataclasses.dataclass(frozen=True)
class Open:
  """What a requirement still needs from its own slots.

  Attributes:
    requirement: The requirement.
    slots: Its slots no completed course fills, in catalogue order.
    count: How many of `slots` it still needs, or None when units decide.
    units: Units it still needs when units decide; 0 otherwise.
  """

  requirement: models.Requirement
  slots: list[list[models.RequirementChoice]]
  count: int | None
  units: float


def left_to_take(
  program: models.Program,
  completed: Sequence[str],
  audit: models.ProgramAudit,
) -> list[Open]:
  """Lists what each unfinished requirement still needs from its slots.

  A slot filled by a completed course is gone, alternatives included, and a
  requirement that picks N of its slots needs only what is short of N. A
  requirement with a unit count that lists more than it needs is decided
  by units. GE requirements, prose-only ones, and those whose own slots are
  enough (only nested requirements remain) are left out.
  """
  fills = _fill(program, {codes.identity(c): c for c in completed})
  progress = {p.position: p for p in audit.requirements}
  left: list[Open] = []
  for req in program.requirements:
    status = progress[req.position].status
    if req.is_general_education or status in (
      models.RequirementStatus.DONE,
      models.RequirementStatus.MANUAL,
    ):
      continue
    filled = fills[req.position]
    slots = [s for i, s in enumerate(req.slots) if i not in filled]
    pick = picks(req)
    if not slots:
      continue
    if req.units is None or pick < len(req.slots):
      if (count := pick - len(filled)) > 0:
        left.append(Open(req, slots, count, 0.0))
      continue
    short = req.units.min - progress[req.position].units
    if short <= 0:
      continue
    listed = sum(
      min((c.units.min for c in s if c.units is not None), default=0.0)
      for s in slots
    )
    if listed <= short:
      left.append(Open(req, slots, len(slots), 0.0))
    else:
      left.append(Open(req, slots, None, short))
  return left
