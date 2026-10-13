"""Tests for the GE audit's matching and AP rules."""

from server.src.data import catalog_models as m
from server.src.engine import ge_audit


CATEGORIES = [
  m.GeCategory(
    code="GE-B", name="Humanistic Inquiry", area="core", required_count=2
  ),
  m.GeCategory(
    code="GE-C", name="Social Analysis", area="core", required_count=1
  ),
  m.GeCategory(code="GE-G", name="Global I", area="global", required_count=1),
]
CALC = m.ApExam(
  id="AP_CALC", name="AP Calculus", min_score=4, units=4, ge=["GE-C"], waives=[]
)


def _filled(progress: list[m.GeProgress]) -> dict[str, list[str]]:
  return {p.code: [*p.courses, *p.exams] for p in progress}


def test_matching_moves_a_flexible_course_to_leave_room():
  # Greedy would put HIST-1 in GE-B and strand GE-C; matching does not.
  course_ge = {
    "HIST-1": ["GE-B", "GE-C"],
    "PHIL-1": ["GE-B"],
    "PHIL-2": ["GE-B"],
  }
  result = ge_audit.audit(
    CATEGORIES, course_ge, ["HIST-1", "PHIL-1", "PHIL-2"], [], []
  )
  assert _filled(result) == {
    "GE-B": ["PHIL-1", "PHIL-2"],
    "GE-C": ["HIST-1"],
    "GE-G": [],
  }


def test_a_course_counts_once_per_area():
  course_ge = {"ANTH-1": ["GE-B", "GE-C", "GE-G"]}
  result = _filled(ge_audit.audit(CATEGORIES, course_ge, ["ANTH-1"], [], []))
  core = result["GE-B"] + result["GE-C"]
  assert core == ["ANTH-1"]
  assert result["GE-G"] == ["ANTH-1"]


def test_ap_credit_needs_the_exams_minimum_score():
  passed = ge_audit.audit(
    CATEGORIES, {}, [], [CALC], [m.ApCredit(exam_id="AP_CALC", score=4)]
  )
  failed = ge_audit.audit(
    CATEGORIES, {}, [], [CALC], [m.ApCredit(exam_id="AP_CALC", score=3)]
  )
  assert _filled(passed)["GE-C"] == ["AP_CALC"]
  assert _filled(failed)["GE-C"] == []


def test_codes_match_case_insensitively_and_unknowns_are_ignored():
  result = ge_audit.audit(
    CATEGORIES, {"PHIL-1": ["GE-B"]}, ["Phil-1", "X-1"], [], []
  )
  assert _filled(result)["GE-B"] == ["Phil-1"]
