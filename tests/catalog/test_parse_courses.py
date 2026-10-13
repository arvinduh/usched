"""Tests for parse_courses against a trimmed real course index page."""

import pathlib

import pytest

from server.src.catalog import parse_courses


FIXTURE = (
  pathlib.Path(__file__).parent / "fixtures" / "courses-page.html"
).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page() -> parse_courses.CoursePage:
  return parse_courses.parse_page(FIXTURE, 22)


@pytest.fixture(scope="module")
def by_code(page):
  return {c.code: c for c in page.courses}


def test_index_navigation_and_page_count():
  assert parse_courses.course_index_navoid(FIXTURE) == 9384
  assert parse_courses.page_count(FIXTURE) == 131
  with pytest.raises(ValueError):
    parse_courses.course_index_navoid("<html></html>")


def test_codes_keep_catalogue_spelling(by_code):
  assert set(by_code) == {
    "ACAD-449",
    "ACAD-450",
    "ACAD-463",
    "ACAD-475a",
    "ACCT-415x",
    "ACCT-416",
    "ACCT-525x",
  }
  assert by_code["ACAD-475a"].title == "The Garage Experience"


def test_labeled_fields(by_code):
  course = by_code["ACCT-415x"]
  assert (course.units_min, course.units_max, course.units_text) == (4, 4, "4")
  assert course.terms_offered == "FaSp"
  assert course.prerequisite == "ACCT 410x or BUAD 280 or BUAD 305"
  assert course.registration_restriction == "Not open to accounting majors"
  assert course.credit_restriction.startswith("Not available for degree")
  assert course.duplicate_credit == "In former ACCT 411x and ACCT 412x"
  assert course.instruction_mode == "Lecture"
  assert course.grading_option == "Letter"


def test_grouped_prerequisites_keep_their_parentheses(by_code):
  assert by_code["ACCT-416"].prerequisite == (
    "(BUAD 215 or BUAD 306 or BUAD 308) and (BUAD 280 or BUAD 305 or ACCT 410)"
  )
  assert by_code["ACCT-416"].recommended_prep == "ACCT 370 or ACCT 377"


def test_maximum_units_and_cross_listing(by_code):
  assert by_code["ACAD-450"].max_units == 8
  assert by_code["ACAD-463"].cross_listed_code == "MEDS-463"


def test_enroll_in_stubs_point_at_the_real_course(by_code):
  stub = by_code["ACAD-449"]
  assert stub.enroll_in_code == "TAC-449"
  assert stub.description is None


def test_description_sentences_are_not_fields(by_code):
  course = by_code["ACCT-525x"]
  assert course.description.startswith("Technical accounting theory")
  assert "Satisfies the prerequisite" in course.description


def test_departments_come_from_headings(page):
  assert page.department_names == {
    "ACAD": "Arts, Technology and the Business of Innovation",
    "ACCT": "Accounting",
  }


def test_ge_statements_and_extra_prose():
  page = parse_courses.parse_page(
    "<h2>Anthropology</h2><li><h3>ANTH 123gp Global Health</h3>Units: 2, 4"
    "<hr>Health across cultures.<br>Credit on acceptance of thesis.<br>"
    "Satisfies New General Education in Category C: Social Analysis<br>"
    "Satisfies Global Perspective in Category H: Traditions<br>"
    "Concurrent enrollment: THTR 315a.</li>",
    22,
  )
  (course,) = page.courses
  assert (course.units_min, course.units_max) == (2, 4)
  assert course.description == "Health across cultures."
  assert course.notes == "Credit on acceptance of thesis."
  assert course.concurrent == "THTR 315a."
  assert [(g.ge_code, g.listed_code) for g in page.ge_courses] == [
    ("GE-C", "ANTH-123gp"),
    ("GE-H", "ANTH-123gp"),
  ]
