"""Shared fixtures: a catalog database built from a small raw cache."""

import pathlib

import pytest

from server.src.catalog import build, cache, classes_api, rmp


FIXTURES = pathlib.Path(__file__).parent / "catalog" / "fixtures"
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
RMP_SEARCH = {
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
}


@pytest.fixture(scope="session")
def catalog_path(tmp_path_factory) -> pathlib.Path:
  """Builds the fixture cache over a stale file, which the build replaces."""
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
  raw.write_json(rmp.search_key("carter slocum"), RMP_SEARCH)
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
  return target
