"""End-to-end: a small raw cache built into a database."""

import sqlite3
from collections.abc import Iterator

import pytest

from server.src.catalog import build, cache


@pytest.fixture(scope="module")
def db(catalog_path) -> Iterator[sqlite3.Connection]:
  conn = sqlite3.connect(catalog_path)
  yield conn
  conn.close()


def _one(db, sql, *args):
  return db.execute(sql, args).fetchone()


def test_every_term_is_recorded_but_only_fetched_terms_have_offerings(db):
  assert _one(db, "SELECT COUNT(*) FROM term")[0] == 3
  terms = {r[0] for r in db.execute("SELECT DISTINCT term_code FROM offering")}
  assert terms == {20271, 20263}


def test_course_codes_compare_case_insensitively(db):
  assert _one(db, "SELECT code FROM course WHERE code = 'csci-104l'") == (
    "CSCI-104L",
  )


def test_duplicate_listing_rows_were_dropped(db):
  per_term = _one(
    db,
    """SELECT COUNT(*) FROM section
       WHERE term_code = 20271 AND course_code = 'CSCI-104L'""",
  )[0]
  assert per_term == 11


def test_requisites_resolve_to_catalog_courses_when_unambiguous(db):
  rows = dict(
    db.execute(
      """SELECT required_code, resolved_code FROM requisite_course
         WHERE term_code = 20271 AND course_code = 'CSCI-420'"""
    ).fetchall()
  )
  assert rows["CSCI-104"] == "CSCI-104L"
  assert rows["MATH-225"] is None


def test_meetings_store_day_bitmasks(db):
  days = _one(
    db,
    """SELECT days FROM meeting
       WHERE term_code = 20271 AND section_id = '17523' AND position = 0""",
  )[0]
  assert days == 8  # Thursday


def test_rmp_profiles_attach_by_instructor_key(db):
  assert _one(
    db, "SELECT rating FROM rmp_profile WHERE instructor_key = 'carter slocum'"
  ) == (4.5,)


def test_ge_names_come_from_the_catalogue_and_policy_from_seeds(db):
  assert _one(
    db, "SELECT name, area, required_count FROM ge_category WHERE code = 'GE-B'"
  ) == ("GE-B", "core", 2)  # Not on this test page: falls back to its code.
  assert _one(db, "SELECT name FROM ge_category WHERE code = 'GE-A'") == (
    "The Arts",
  )
  assert _one(
    db, "SELECT resolved_code FROM ge_course WHERE listed_code = 'CSCI-104L'"
  ) == ("CSCI-104L",)


def test_programs_requirements_and_choices(db):
  program = _one(
    db,
    """SELECT kind, degree_type, total_units FROM program
       WHERE id = 'computer-science-bs'""",
  )
  assert program == ("degree", "BS", 128.0)
  alternatives = [
    r[0]
    for r in db.execute(
      """SELECT c.listed_code FROM program_requirement_choice c
         JOIN program_requirement r ON r.program_id = c.program_id
           AND r.position = c.requirement_position
         WHERE c.program_id = 'computer-science-bs'
           AND r.title = 'Mathematics'
           AND c.slot = 1 ORDER BY c.position"""
    )
  ]
  assert alternatives == ["MATH-126g", "MATH-129"]


def test_ap_seeds_load_with_waivers(db):
  assert _one(db, "SELECT COUNT(*) FROM ap_exam")[0] == 13
  assert _one(
    db,
    """SELECT waived_code FROM ap_exam_waiver
       WHERE exam_id = 'AP_CALC_BC' ORDER BY 1""",
  ) == ("MATH-125",)


def test_full_text_search_is_term_scoped(db):
  hits = db.execute(
    """SELECT course_code FROM offering_fts
       WHERE offering_fts MATCH 'structures' AND term_code = 20271"""
  ).fetchall()
  assert ("CSCI-104L",) in hits


def test_catalogue_courses_define_every_course(db):
  assert _one(db, "SELECT COUNT(*) FROM catalogue_course")[0] == 8
  # Offered nowhere, yet a course with an identity.
  assert _one(db, "SELECT key FROM course WHERE code = 'ACCT-415x'") == (
    "ACCT-415",
  )


def test_the_catalogues_spelling_is_canonical_everywhere(db):
  # The schedule wrote CSCI-445L; the catalogue's CSCI-445Lx wins.
  assert _one(
    db,
    """SELECT DISTINCT o.course_code FROM offering o
       JOIN course c ON c.code = o.course_code WHERE c.key = 'CSCI-445'""",
  ) == ("CSCI-445Lx",)
  assert _one(db, "SELECT COUNT(*) FROM course WHERE key = 'CSCI-445'")[0] == 1
  binary = _one(
    db,
    """SELECT COUNT(*) FROM section s JOIN course c ON c.code = s.course_code
       WHERE s.course_code != c.code COLLATE BINARY""",
  )
  assert binary == (0,)


def test_ge_unions_page_lists_and_course_statements(db):
  rows = set(db.execute("SELECT ge_code, resolved_code FROM ge_course"))
  assert ("GE-A", "CSCI-104L") in rows  # From the GE page.
  assert ("GE-E", "CSCI-445Lx") in rows  # From the course itself.


def test_catalogue_headings_name_departments_the_schedule_lacks(db):
  assert _one(
    db, "SELECT name, school_code FROM department WHERE code = 'ACCT'"
  ) == (
    "Accounting",
    None,
  )


def test_foreign_keys_hold(db):
  assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_build_without_a_fetch_fails_clearly(tmp_path):
  with pytest.raises(FileNotFoundError):
    build.build(cache.RawCache(tmp_path / "empty"), tmp_path / "x.db")
