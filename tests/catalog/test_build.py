"""End-to-end: a small raw cache built into a database."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest

from server.src.catalog import build, cache, classes_api, rmp


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
TERMS = [
  {"termCode": 20271, "year": 2027, "season": "Spring", "status": "Active"},
  {"termCode": 20263, "year": 2026, "season": "Fall", "status": "Active"},
  {"termCode": 20253, "year": 2025, "season": "Fall", "status": "Inactive"},
]
INDEX = """
<select><option value="22" selected="">USC Catalogue 2026-2027</option></select>
<a href="preview_program.php?catoid=22&amp;poid=32086">Computer Science (BS)</a>
<a href="preview_program.php?catoid=22&amp;poid=31554">General Education</a>
"""
GE_PAGE = """
<h1>General Education</h1>
<h4>GE-A. The Arts</h4>
<li class="acalog-course">CSCI 104L Data Structures Units: 4</li>
<h4>GE-F. Quantitative Reasoning</h4>
<li class="acalog-course">MATH 125g Calculus I Units: 4</li>
"""


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Iterator[sqlite3.Connection]:
  root = tmp_path_factory.mktemp("raw")
  raw = cache.RawCache(root)
  listing = (FIXTURES / "listing.json").read_text(encoding="utf-8")
  schools = (FIXTURES / "schools.json").read_text(encoding="utf-8")
  raw.write_json(classes_api.TERMS_KEY, TERMS)
  for term in (20271, 20263):
    raw.write_text(classes_api.schools_key(term), schools)
    raw.write_text(classes_api.listing_key(term, "ENGV", "CSCI"), listing)
  # The same listing under a second school must deduplicate, not collide.
  raw.write_text(classes_api.listing_key(20271, "DRNS", "CHEM"), listing)
  raw.write_json(
    rmp.search_key("carter slocum"),
    {
      "data": {
        "newSearch": {
          "teachers": {
            "edges": [
              {
                "node": {
                  "legacyId": 7,
                  "firstName": "Carter",
                  "lastName": "Slocum",
                  "department": "CS",
                  "avgRating": 4.5,
                  "avgDifficulty": 3.0,
                  "numRatings": 20,
                  "wouldTakeAgainPercent": 90,
                }
              }
            ]
          }
        }
      }
    },
  )
  raw.write_text("catalogue/22/index.html", INDEX)
  raw.write_text(
    "catalogue/22/programs/32086.html",
    (FIXTURES / "program-cs.html").read_text(encoding="utf-8"),
  )
  raw.write_text("catalogue/22/programs/31554.html", GE_PAGE)

  target = root.parent / "catalog.db"
  target.write_text("stale database to be replaced")
  counts = build.build(raw, target)
  assert counts["offering"] > 0
  assert not target.with_name(target.name + ".building").exists()
  conn = sqlite3.connect(target)
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


def test_foreign_keys_hold(db):
  assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_build_without_a_fetch_fails_clearly(tmp_path):
  with pytest.raises(FileNotFoundError):
    build.build(cache.RawCache(tmp_path / "empty"), tmp_path / "x.db")
