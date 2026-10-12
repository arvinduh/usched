"""Tests for catalog_db: API models assembled from the fixture catalog."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest

from server.src.data import catalog_db
from server.src.data import catalog_models as m


@pytest.fixture(scope="module")
def conn(catalog_path) -> Iterator[sqlite3.Connection]:
  conn = catalog_db.CatalogDb(catalog_path).connect()
  yield conn
  conn.close()


def test_connect_refuses_a_missing_catalog(tmp_path: pathlib.Path):
  with pytest.raises(FileNotFoundError, match="npm run catalog"):
    catalog_db.CatalogDb(tmp_path / "none.db").connect()


def test_connection_is_read_only(conn):
  with pytest.raises(sqlite3.OperationalError, match="readonly"):
    conn.execute("DELETE FROM term")


def test_terms_newest_first_and_default_is_newest_with_courses(conn):
  terms = catalog_db.terms(conn)
  assert [t.code for t in terms] == [20271, 20263, 20253]
  assert [t.has_courses for t in terms] == [True, True, False]
  assert catalog_db.default_term(conn) == 20271


def test_course_assembles_every_child_table(conn):
  course = catalog_db.course(conn, 20271, "csci-104l")
  assert course is not None
  assert (course.code, course.department, course.number) == (
    "CSCI-104L",
    "CSCI",
    "104",
  )
  assert course.ge == ["GE-A"]
  assert len(course.requisites.prerequisite) == 2
  assert len(course.sections) == 11
  lecture = next(s for s in course.sections if s.id == "29905")
  assert (lecture.type, lecture.link_code) == ("Lecture", "A")
  assert lecture.requires_d_clearance
  slocum = next(i for i in lecture.instructors if i.key == "carter slocum")
  assert slocum.rmp is not None and slocum.rmp.rating == 4.5


def test_courses_keep_request_order_and_skip_unknown_codes(conn):
  found = catalog_db.courses(conn, 20271, ["CSCI-420", "NOPE-1", "CHEM-108L"])
  assert [c.code for c in found] == ["CSCI-420", "CHEM-108L"]


def test_course_is_scoped_to_its_term(conn):
  assert catalog_db.course(conn, 20253, "CSCI-104L") is None


def test_requisite_options_resolve(conn):
  course = catalog_db.course(conn, 20271, "CSCI-420")
  assert course is not None
  refs = [
    ref
    for group in course.requisites.prerequisite
    for option in group.options
    for ref in option
  ]
  assert m.CourseRef(code="CSCI-104", resolved="CSCI-104L") in refs


def test_corequisites_and_restrictions_are_separated(conn):
  tutorial = catalog_db.course(conn, 20271, "CHEM-251x")
  assert tutorial is not None
  assert len(tutorial.requisites.corequisite) == 1
  chem = catalog_db.course(conn, 20271, "CHEM-108L")
  assert chem is not None
  assert {r.kind for r in chem.restrictions} == {"major"}
  assert len(chem.restrictions) == 5


def test_meetings_decode_day_bitmasks(conn):
  (section,) = catalog_db.sections(conn, 20271, ["17523"])
  assert section.meetings[0].days == [m.Weekday.THU]


def test_search_ranks_exact_code_first(conn):
  found = catalog_db.search_courses(conn, 20271, "csci 104")
  assert found[0].code == "CSCI-104L"


def test_search_by_text_ge_and_rating(conn):
  assert [
    c.code for c in catalog_db.search_courses(conn, 20271, "structures")
  ] == ["CSCI-104L", "CSCI-103L"]  # A title hit outranks a description hit.
  assert [
    c.code for c in catalog_db.search_courses(conn, 20271, None, ge="ge-a")
  ] == ["CSCI-104L"]
  rated = catalog_db.search_courses(conn, 20271, None, min_rating=4.0)
  assert [c.code for c in rated] == ["CSCI-104L"]


def test_search_pages(conn):
  every = catalog_db.search_courses(conn, 20271, None)
  page = catalog_db.search_courses(conn, 20271, None, limit=3, offset=2)
  assert [c.code for c in page] == [c.code for c in every[2:5]]


def test_program_tree_and_choices(conn):
  assert [p.id for p in catalog_db.programs(conn, kind="degree")] == [
    "computer-science-bs"
  ]
  program = catalog_db.program(conn, "computer-science-bs")
  assert program is not None
  assert program.catalogue == "USC Catalogue 2026-2027"
  math = next(r for r in program.requirements if r.title == "Mathematics")
  assert [c.course.code for c in math.slots[1]] == ["MATH-126g", "MATH-129"]
  assert catalog_db.program(conn, "nope") is None


def test_ge_categories_and_ap_exams(conn):
  assert [g.code for g in catalog_db.ge_categories(conn)][:2] == [
    "GE-A",
    "GE-B",
  ]
  calc = next(e for e in catalog_db.ap_exams(conn) if e.id == "AP_CALC_BC")
  assert [w.code for w in calc.waives] == ["MATH-125", "MATH-126"]
