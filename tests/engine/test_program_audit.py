"""Tests for auditing a program's requirement tree."""

from server.db import models
from server.engine import _program_audit


DONE = models.RequirementStatus.DONE
PARTIAL = models.RequirementStatus.PARTIAL
TODO = models.RequirementStatus.TODO
MANUAL = models.RequirementStatus.MANUAL


def _ref(code: str, resolved: str | None = None) -> models.CourseRef:
  return models.CourseRef(code=code, resolved=resolved or code)


def _slot(*codes: str) -> list[models.RequirementChoice]:
  return [
    models.RequirementChoice(
      course=_ref(c), title=None, units=models.Units(min=4, max=4)
    )
    for c in codes
  ]


def _req(
  position: int,
  parent: int | None,
  slots: list[list[models.RequirementChoice]],
  units: float | None = None,
  is_ge: bool = False,
) -> models.Requirement:
  return models.Requirement(
    position=position,
    parent=parent,
    title=f"R{position}",
    units=None if units is None else models.Units(min=units, max=units),
    notes="",
    is_general_education=is_ge,
    slots=slots,
  )


PROGRAM = models.Program(
  id="p",
  title="P (BS)",
  name="P",
  emphasis=None,
  kind="degree",
  degree_type="BS",
  school=None,
  total_units=128,
  total_units_stated=True,
  catalogue="C",
  description="",
  requirements=[
    _req(0, None, []),  # Major: met when its children are.
    _req(1, 0, [_slot("A-1"), _slot("A-2", "A-3")]),  # Every slot.
    _req(2, 0, [_slot("E-1"), _slot("E-2"), _slot("A-1")], units=8),
    _req(3, None, []),  # Prose only.
  ],
)


def _statuses(audit: models.ProgramAudit) -> list[models.RequirementStatus]:
  return [r.status for r in audit.requirements]


def test_nothing_done():
  audit = _program_audit.audit(PROGRAM, [], {}, {})
  assert _statuses(audit) == [TODO, TODO, TODO, MANUAL]
  assert audit.units == 0


def test_slots_units_and_parents():
  audit = _program_audit.audit(PROGRAM, ["A-1", "A-3", "E-1"], {}, {})
  assert _statuses(audit) == [PARTIAL, DONE, PARTIAL, MANUAL]
  # A-1 fills requirement 1 first, so it cannot also count toward 2.
  assert audit.requirements[1].courses == ["A-1", "A-3"]
  assert audit.requirements[2].courses == ["E-1"]
  assert audit.requirements[0].units == 12
  done = _program_audit.audit(PROGRAM, ["A-1", "A-2", "E-1", "E-2"], {}, {})
  assert _statuses(done)[:3] == [DONE, DONE, DONE]


def test_units_prefer_the_catalog_and_count_courses_outside_the_program():
  units = {
    "E-1": models.Units(min=2, max=4),
    "X-9": models.Units(min=3, max=3),
  }
  audit = _program_audit.audit(PROGRAM, ["E-1", "X-9", "Y-1"], units, {})
  assert audit.requirements[2].units == 2
  assert audit.units == 5  # Y-1's units are unknown.


def test_locked_courses_follow_prerequisites():
  needs_a1 = models.Requisites(
    prerequisite=[
      models.RequisiteGroup(required_count=1, options=[[_ref("A-1")]])
    ],
    corequisite=[],
    concurrent=[],
  )
  requisites = {"E-2": needs_a1, "E-1": needs_a1}
  assert _program_audit.audit(PROGRAM, [], {}, requisites).locked == {
    "E-1": ["A-1"],
    "E-2": ["A-1"],
  }
  assert _program_audit.audit(PROGRAM, ["A-1"], {}, requisites).locked == {}


def test_prerequisite_groups_need_their_count_of_complete_options():
  group = models.RequisiteGroup(
    required_count=1,
    options=[[_ref("A-1"), _ref("A-2")], [_ref("B-1")]],
  )
  req = models.Requisites(prerequisite=[group], corequisite=[], concurrent=[])
  assert _program_audit.unmet_prerequisites(req, {"A-1"}) == [group]
  assert not _program_audit.unmet_prerequisites(req, {"A-1", "A-2"})
  assert not _program_audit.unmet_prerequisites(req, {"B-1"})


def _ge(filled: int, required: int) -> models.GeProgress:
  return models.GeProgress(
    code="GE-A",
    name="Arts",
    area="core",
    required_count=required,
    courses=[f"X-{i}" for i in range(filled)],
    exams=[],
  )


def test_the_ge_audit_decides_ge_requirements():
  program = PROGRAM.model_copy(
    update={"requirements": [_req(0, None, [], units=20, is_ge=True)]}
  )
  ge = [_ge(1, 1), _ge(0, 2)]
  partial = _program_audit.audit(program, [], {}, {}, ge=ge, ge_units=4)
  assert partial.requirements[0].status == PARTIAL
  assert partial.requirements[0].units == 4
  done = _program_audit.audit(program, [], {}, {}, ge=[_ge(1, 1)], ge_units=4)
  assert done.requirements[0].status == DONE
  assert (
    _program_audit.audit(program, [], {}, {}).requirements[0].status == TODO
  )


def test_exam_units_count_toward_the_total():
  audit = _program_audit.audit(PROGRAM, ["A-1"], {}, {}, credit_units=4)
  assert audit.units == 8
