"""Tests for catalog_db: API models assembled from the fixture catalog."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest

from server.db import models, store


@pytest.fixture(scope="module")
def conn(catalog_path) -> Iterator[sqlite3.Connection]:
  conn = store.CatalogDb(catalog_path).connect()
  yield conn
  conn.close()


def test_connect_refuses_a_missing_catalog(tmp_path: pathlib.Path):
  with pytest.raises(FileNotFoundError, match="npm run catalog"):
    store.CatalogDb(tmp_path / "none.db").connect()


def test_connection_is_read_only(conn):
  with pytest.raises(sqlite3.OperationalError, match="readonly"):
    conn.execute("DELETE FROM term")


def test_terms_newest_first_and_default_is_newest_with_courses(conn):
  terms = store.terms(conn)
  assert [t.code for t in terms] == [20271, 20263, 20253]
  assert [t.has_courses for t in terms] == [True, True, False]
  assert store.default_term(conn) == 20271


def test_course_assembles_every_child_table(conn):
  course = store.course(conn, 20271, "csci-104l")
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
  found = store.courses(conn, 20271, ["CSCI-420", "NOPE-1", "CHEM-108L"])
  assert [c.code for c in found] == ["CSCI-420", "CHEM-108L"]


def test_any_spelling_finds_a_course(conn):
  for spelling in ("CSCI 104", "csci-104l", "CSCI-104Lg"):
    course = store.course(conn, 20271, spelling)
    assert course is not None and course.code == "CSCI-104L", spelling
  assert len(store.courses(conn, 20271, ["CSCI-104L", "CSCI 104"])) == 1


def test_course_is_scoped_to_its_term(conn):
  assert store.course(conn, 20253, "CSCI-104L") is None


def test_requisite_options_resolve(conn):
  course = store.course(conn, 20271, "CSCI-420")
  assert course is not None
  refs = [
    ref
    for group in course.requisites.prerequisite
    for option in group.options
    for ref in option
  ]
  assert models.CourseRef(code="CSCI-104", resolved="CSCI-104L") in refs


def test_corequisites_and_restrictions_are_separated(conn):
  tutorial = store.course(conn, 20271, "CHEM-251x")
  assert tutorial is not None
  assert len(tutorial.requisites.corequisite) == 1
  chem = store.course(conn, 20271, "CHEM-108L")
  assert chem is not None
  assert {r.kind for r in chem.restrictions} == {"major"}
  assert len(chem.restrictions) == 5


def test_meetings_decode_day_bitmasks(conn):
  (section,) = store.sections(conn, 20271, ["17523"])
  assert section.meetings[0].days == [models.Weekday.THU]


def test_search_ranks_exact_code_first(conn):
  found = store.search_courses(conn, 20271, "csci 104")
  assert found[0].code == "CSCI-104L"


def test_search_by_text_ge_and_rating(conn):
  assert [c.code for c in store.search_courses(conn, 20271, "structures")] == [
    "CSCI-104L",
    "CSCI-103L",
  ]  # A title hit outranks a description hit.
  assert [
    c.code for c in store.search_courses(conn, 20271, None, ge="ge-a")
  ] == ["CSCI-104L"]
  rated = store.search_courses(
    conn, 20271, None, section=store.SectionFilter(min_rating=4.0)
  )
  assert [c.code for c in rated] == ["CSCI-104L"]


def test_search_by_meeting_time(conn):
  def codes(
    starts_from: int | None = None,
    ends_by: int | None = None,
    meets_at: int | None = None,
  ) -> list[str]:
    found = store.search_courses(
      conn,
      20271,
      None,
      section=store.SectionFilter(
        starts_from=starts_from, ends_by=ends_by, meets_at=meets_at
      ),
    )
    return [c.code for c in found]

  assert codes(starts_from=19 * 60) == ["CSCI-103L", "CSCI-104L"]
  # In class at 8 PM: a 5-9 PM lab counts, though it starts earlier.
  assert codes(meets_at=20 * 60) == ["CHEM-462L", "CSCI-103L", "CSCI-104L"]
  assert codes(starts_from=8 * 60, ends_by=9 * 60 + 30) == [
    "CSCI-104L",
    "CSCI-445Lx",
  ]


def test_search_by_units_level_and_instructor(conn):
  def codes(**kwargs) -> list[str]:
    return [c.code for c in store.search_courses(conn, 20271, None, **kwargs)]

  # A 1-8 unit course counts as a 2-unit one.
  assert codes(units=(2, 2)) == ["CHEM-251x", "CHEM-490x"]
  assert codes(levels=(400, 499)) == [
    "CHEM-462L",
    "CHEM-490x",
    "CSCI-420",
    "CSCI-445Lx",
  ]
  assert codes(section=store.SectionFilter(instructor="Biyik")) == [
    "CSCI-445Lx"
  ]
  easy = store.SectionFilter(max_difficulty=3.0)
  assert codes(section=easy) == ["CSCI-104L"]


def test_search_sorts_by_a_sections_best_value(conn):
  by_seats = store.search_courses(
    conn, 20271, "csci", sort=store.SearchSort.OPEN_SEATS
  )
  assert [c.code for c in by_seats][:2] == ["CSCI-104L", "CSCI-103L"]
  rated = store.search_courses(
    conn, 20271, "csci", sort=store.SearchSort.RATING
  )
  assert rated[0].code == "CSCI-104L"  # The only rated instructor.


def test_search_expands_abbreviations_to_phrases(conn):
  assert [c.code for c in store.search_courses(conn, 20271, "dsa")] == [
    "CSCI-104L"
  ]
  assert [c.code for c in store.search_courses(conn, 20271, "oop")] == [
    "CSCI-103L"
  ]


def test_search_pages(conn):
  every = store.search_courses(conn, 20271, None)
  page = store.search_courses(conn, 20271, None, limit=3, offset=2)
  assert [c.code for c in page] == [c.code for c in every[2:5]]


def test_program_tree_and_choices(conn):
  assert [p.id for p in store.programs(conn, kind="degree")] == [
    "computer-science-bs"
  ]
  program = store.program(conn, "computer-science-bs")
  assert program is not None
  assert program.catalogue == "USC Catalogue 2026-2027"
  math = next(r for r in program.requirements if r.title == "Mathematics")
  assert [c.course.code for c in math.slots[1]] == ["MATH-126g", "MATH-129"]
  titles = {
    c.course.resolved: c.title
    for r in program.requirements
    for slot in r.slots
    for c in slot
  }
  assert titles["CSCI-104L"] == "Data Structures"
  assert store.program(conn, "nope") is None


def test_ge_categories_and_ap_exams(conn):
  assert [g.code for g in store.ge_categories(conn)][:2] == [
    "GE-A",
    "GE-B",
  ]
  calc = next(e for e in store.ap_exams(conn) if e.id == "AP_CALC_BC")
  assert [w.code for w in calc.waives] == ["MATH-125", "MATH-126"]


def test_connection_performance_pragmas(conn):
  assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
  assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2
  assert conn.execute("PRAGMA cache_size").fetchone()[0] == -32000
  assert conn.execute("PRAGMA mmap_size").fetchone()[0] == 134217728


def test_cached_catalog_queries_and_clear(conn):
  # First call computes and caches
  progs1 = store.programs(conn)
  progs2 = store.programs(conn)
  assert progs1 == progs2

  ge1 = store.ge_categories(conn)
  ge2 = store.ge_categories(conn)
  assert ge1 == ge2

  p1 = store.program(conn, "computer-science-bs")
  p2 = store.program(conn, "computer-science-bs")
  assert p1 is p2

  ap1 = store.ap_exams(conn)
  ap2 = store.ap_exams(conn)
  assert ap1 == ap2

  # Cache clear resets without errors
  store.clear_catalog_caches()
  assert store.programs(conn) == progs1


def test_get_connection_module_helper(catalog_path):
  conn1 = store.get_connection(catalog_path)
  conn2 = store.get_connection(catalog_path)
  assert conn1 is conn2
  store.close_connection()
