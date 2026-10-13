"""Tests for the GE audit's matching and AP rules."""

from server.db import models
from server.engine import _ge_audit


CATEGORIES = [
  models.GeCategory(
    code="GE-B", name="Humanistic Inquiry", area="core", required_count=2
  ),
  models.GeCategory(
    code="GE-C", name="Social Analysis", area="core", required_count=1
  ),
  models.GeCategory(
    code="GE-G", name="Global I", area="global", required_count=1
  ),
]
CALC = models.ApExam(
  id="AP_CALC", name="AP Calculus", min_score=4, units=4, ge=["GE-C"], waives=[]
)


def _filled(progress: list[models.GeProgress]) -> dict[str, list[str]]:
  return {p.code: [*p.courses, *p.exams] for p in progress}


def test_matching_moves_a_flexible_course_to_leave_room():
  # Greedy would put HIST-1 in GE-B and strand GE-C; matching does not.
  course_ge = {
    "HIST-1": ["GE-B", "GE-C"],
    "PHIL-1": ["GE-B"],
    "PHIL-2": ["GE-B"],
  }
  result = _ge_audit.audit(
    CATEGORIES, course_ge, ["HIST-1", "PHIL-1", "PHIL-2"], [], []
  )
  assert _filled(result) == {
    "GE-B": ["PHIL-1", "PHIL-2"],
    "GE-C": ["HIST-1"],
    "GE-G": [],
  }


def test_a_course_counts_once_per_area():
  course_ge = {"ANTH-1": ["GE-B", "GE-C", "GE-G"]}
  result = _filled(_ge_audit.audit(CATEGORIES, course_ge, ["ANTH-1"], [], []))
  core = result["GE-B"] + result["GE-C"]
  assert core == ["ANTH-1"]
  assert result["GE-G"] == ["ANTH-1"]


def test_ap_credit_needs_the_exams_minimum_score():
  passed = _ge_audit.audit(
    CATEGORIES, {}, [], [CALC], [models.ApCredit(exam_id="AP_CALC", score=4)]
  )
  failed = _ge_audit.audit(
    CATEGORIES, {}, [], [CALC], [models.ApCredit(exam_id="AP_CALC", score=3)]
  )
  assert _filled(passed)["GE-C"] == ["AP_CALC"]
  assert _filled(failed)["GE-C"] == []


def test_codes_match_case_insensitively_and_unknowns_are_ignored():
  result = _ge_audit.audit(
    CATEGORIES, {"PHIL-1": ["GE-B"]}, ["Phil-1", "X-1"], [], []
  )
  assert _filled(result)["GE-B"] == ["Phil-1"]


def test_earned_units_count_each_course_and_exam_once():
  progress = [
    models.GeProgress(
      code="GE-B", name="B", required_count=2, courses=["ANTH-1"], exams=[]
    ),
    models.GeProgress(
      code="GE-G",
      name="G",
      required_count=1,
      courses=["anth-1"],
      exams=["AP_CALC"],
    ),
  ]
  units = {"ANTH-1": models.Units(min=4, max=4)}
  assert _ge_audit.earned_units(progress, units, [CALC]) == 8


def test_seats_counted_by_hand_fill_only_what_is_left():
  result = _ge_audit.audit(
    CATEGORIES,
    {"PHIL-1": ["GE-B"]},
    ["PHIL-1"],
    [],
    [],
    {"GE-B": 2, "GE-C": 1, "GE-G": -1},
  )
  assert {p.code: (p.counted, p.filled) for p in result} == {
    "GE-B": (1, 2),
    "GE-C": (1, 1),
    "GE-G": (0, 0),
  }
