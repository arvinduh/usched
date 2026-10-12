"""Tests for auditing a program's requirement tree."""

from server.src.data import catalog_models as m
from server.src.engine import program_audit


DONE = m.RequirementStatus.DONE
PARTIAL = m.RequirementStatus.PARTIAL
TODO = m.RequirementStatus.TODO
MANUAL = m.RequirementStatus.MANUAL


def _ref(code: str, resolved: str | None = None) -> m.CourseRef:
  return m.CourseRef(code=code, resolved=resolved or code)


def _slot(*codes: str) -> list[m.RequirementChoice]:
  return [
    m.RequirementChoice(course=_ref(c), units=m.Units(min=4, max=4))
    for c in codes
  ]


def _req(
  position: int,
  parent: int | None,
  slots: list[list[m.RequirementChoice]],
  units: float | None = None,
) -> m.Requirement:
  return m.Requirement(
    position=position,
    parent=parent,
    title=f"R{position}",
    units=None if units is None else m.Units(min=units, max=units),
    notes="",
    slots=slots,
  )


PROGRAM = m.Program(
  id="p",
  title="P (BS)",
  name="P",
  emphasis=None,
  kind="degree",
  degree_type="BS",
  school=None,
  total_units=128,
  catalogue="C",
  description="",
  requirements=[
    _req(0, None, []),  # Major: met when its children are.
    _req(1, 0, [_slot("A-1"), _slot("A-2", "A-3")]),  # Every slot.
    _req(2, 0, [_slot("E-1"), _slot("E-2"), _slot("A-1")], units=8),
    _req(3, None, []),  # Prose only.
  ],
)


def _statuses(audit: m.ProgramAudit) -> list[m.RequirementStatus]:
  return [r.status for r in audit.requirements]


def test_nothing_done():
  audit = program_audit.audit(PROGRAM, [], {}, {})
  assert _statuses(audit) == [TODO, TODO, TODO, MANUAL]
  assert audit.units == 0


def test_slots_units_and_parents():
  audit = program_audit.audit(PROGRAM, ["a-1", "A-3", "E-1"], {}, {})
  assert _statuses(audit) == [PARTIAL, DONE, PARTIAL, MANUAL]
  # A-1 fills requirement 1 first, so it cannot also count toward 2.
  assert audit.requirements[1].courses == ["a-1", "A-3"]
  assert audit.requirements[2].courses == ["E-1"]
  assert audit.requirements[0].units == 12
  done = program_audit.audit(PROGRAM, ["A-1", "A-2", "E-1", "E-2"], {}, {})
  assert _statuses(done)[:3] == [DONE, DONE, DONE]


def test_units_prefer_the_catalog_and_count_courses_outside_the_program():
  units = {"e-1": m.Units(min=2, max=4), "x-9": m.Units(min=3, max=3)}
  audit = program_audit.audit(PROGRAM, ["E-1", "X-9", "Y-1"], units, {})
  assert audit.requirements[2].units == 2
  assert audit.units == 5  # Y-1's units are unknown.


def test_locked_courses_follow_prerequisites():
  needs_a1 = m.Requisites(
    prerequisite=[m.RequisiteGroup(required_count=1, options=[[_ref("A-1")]])],
    corequisite=[],
    concurrent=[],
  )
  requisites = {"e-2": needs_a1, "e-1": needs_a1}
  assert program_audit.audit(PROGRAM, [], {}, requisites).locked == [
    "E-1",
    "E-2",
  ]
  assert program_audit.audit(PROGRAM, ["A-1"], {}, requisites).locked == []


def test_prerequisite_groups_need_their_count_of_complete_options():
  group = m.RequisiteGroup(
    required_count=1, options=[[_ref("A-1"), _ref("A-2")], [_ref("B-1")]]
  )
  req = m.Requisites(prerequisite=[group], corequisite=[], concurrent=[])
  assert not program_audit.prerequisites_met(req, {"a-1"})
  assert program_audit.prerequisites_met(req, {"a-1", "a-2"})
  assert program_audit.prerequisites_met(req, {"b-1"})
