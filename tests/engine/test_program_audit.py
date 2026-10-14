"""Tests for auditing a program's requirement tree."""

import pytest

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


def _titled(req: models.Requirement, title: str) -> models.Requirement:
  return req.model_copy(update={"title": title})


# BUAI-shaped: two "or" slots, then a heading that picks 3 of 9 courses,
# then a bucket of its own that later courses can still fill.
PICKS = PROGRAM.model_copy(
  update={
    "requirements": [
      _req(0, None, [_slot("B-306", "B-308"), _slot("B-311", "B-313")]),
      _titled(
        _req(1, None, [_slot(f"P-{i}") for i in range(9)]),
        "Choose three of the following:",
      ),
      _req(2, None, [_slot("P-8"), _slot("X-1")]),
    ]
  }
)


@pytest.mark.parametrize(
  "text, picked",
  [
    ("Choose one of the following:", 1),
    ("Select three courses from the following", 3),
    ("Students must complete 3 of the following 9 courses", 3),
    ("Take any two of these", 2),
    ("Choose one course from each of the following areas", 9),
    ("Take at least four 300- or 400- level CSCI courses", 9),
    ("Choose one of these. Choose two of those.", 9),
    ("Choose twelve of the following", 9),
  ],
)
def test_picks_read_the_count_from_the_heading_or_notes(text, picked):
  req = _req(0, None, [_slot(f"P-{i}") for i in range(9)])
  assert _program_audit.picks(_titled(req, text)) == picked
  noted = req.model_copy(update={"notes": text})
  assert _program_audit.picks(noted) == picked


def test_a_pick_requirement_is_done_at_its_count():
  audit = _program_audit.audit(PICKS, ["B-308", "B-311", "P-1", "P-4"], {}, {})
  assert _statuses(audit)[:2] == [DONE, PARTIAL]
  done = _program_audit.audit(PICKS, ["P-1", "P-4", "P-6"], {}, {})
  assert _statuses(done)[1] == DONE


def test_courses_past_a_pick_count_flow_to_later_requirements():
  audit = _program_audit.audit(PICKS, ["P-0", "P-1", "P-2", "P-8"], {}, {})
  assert audit.requirements[1].courses == ["P-0", "P-1", "P-2"]
  assert audit.requirements[2].courses == ["P-8"]


def _left(program, completed):
  audit = _program_audit.audit(program, completed, {}, {})
  return [
    (
      o.requirement.position,
      [[c.course.code for c in s] for s in o.slots],
      o.count,
      o.units,
    )
    for o in _program_audit.left_to_take(program, completed, audit)
  ]


def test_left_to_take_drops_a_filled_slots_alternatives():
  left = _left(PICKS, ["B-306", "P-1", "P-2"])
  assert left[0] == (0, [["B-311", "B-313"]], 1, 0.0)
  position, slots, count, _ = left[1]
  assert (position, count, len(slots)) == (1, 1, 7)
  assert ["P-1"] not in slots


def test_left_to_take_skips_requirements_already_met():
  left = _left(PICKS, ["B-306", "B-313", "P-1", "P-2", "P-3", "X-1"])
  assert [position for position, *_ in left] == [2]


def test_left_to_take_lets_units_decide_when_more_is_listed():
  # Requirement 2 needs 8 units from three 4-unit slots; A-1 fills one in 1.
  left = dict((p, rest) for p, *rest in _left(PROGRAM, ["E-1"]))
  assert left[2] == [[["E-2"], ["A-1"]], None, 4.0]
  assert left[1] == [[["A-1"], ["A-2", "A-3"]], 2, 0.0]
  # Parents with no slots of their own and prose-only requirements are out.
  assert set(left) == {1, 2}


def test_waived_courses_fill_slots_without_adding_units():
  audit = _program_audit.audit(
    PROGRAM, ["A-3"], {}, {}, credit_units=4, waived=["A-1"]
  )
  assert _statuses(audit)[1] == DONE
  assert audit.requirements[1].courses == ["A-1", "A-3"]
  assert audit.units == 8  # The exam's 4 and A-3's 4; A-1 adds none.


def test_waived_courses_meet_prerequisites():
  needs_a1 = models.Requisites(
    prerequisite=[
      models.RequisiteGroup(required_count=1, options=[[_ref("A-1")]])
    ],
    corequisite=[],
    concurrent=[],
  )
  audit = _program_audit.audit(
    PROGRAM, [], {}, {"E-1": needs_a1}, waived=["A-1"]
  )
  assert audit.locked == {}
