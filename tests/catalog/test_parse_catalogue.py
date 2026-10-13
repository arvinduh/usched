"""Tests for parse_catalogue: a real program page plus small synthetic ones."""

import pathlib

import pytest

from server.db.ingest import _parse_catalogue


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CS = _parse_catalogue.ProgramLink(32086, "Computer Science (BS)")

# Mirrors Acalog markup: "or" as its own paragraph, a nested h5 rule, a unit
# range, footnotes after the total, and a "Return to" school link.
SYNTHETIC = """
<h1>Sample (BA)</h1>
<p>Intro paragraph.</p>
<h2>Major Requirements (12-16 Units)</h2>
<h3>Core (8 units)</h3>
<ul>
<li class="acalog-course">ECON 203 Principles of Microeconomics Units: 4</li>
<p>or</p>
<li class="acalog-course">ECON 205 Principles of Macroeconomics Units: 4</li>
<li class="acalog-course">MATH 118gx Calculus Units: 2-4</li>
</ul>
<h4>Electives (4 units)</h4>
<h5>Choose one of the following:</h5>
<li class="acalog-course">ECON 330 Labor Economics Units: 4 <span>or</span></li>
<li class="acalog-course">ECON 340 Development Units: 4</li>
<h2>Total units: 128</h2>
<p>* Footnote about the program.</p>
<p>Return to: Dornsife College</p>
<p class="close">Close</p>
<p>Not part of the program.</p>
"""


@pytest.fixture(scope="module")
def cs() -> _parse_catalogue.ProgramPage:
  html = (FIXTURES / "program-cs.html").read_text(encoding="utf-8")
  return _parse_catalogue.parse_program(html, 22, CS, "computer-science-bs")


@pytest.fixture(scope="module")
def sample() -> _parse_catalogue.ProgramPage:
  link = _parse_catalogue.ProgramLink(1, "Sample (BA)")
  return _parse_catalogue.parse_program(SYNTHETIC, 22, link, "sample-ba")


def _slots(page: _parse_catalogue.ProgramPage) -> list[list[str]]:
  slots: dict[tuple[int, int], list[str]] = {}
  for c in page.choices:
    slots.setdefault((c.requirement_position, c.slot), []).append(c.listed_code)
  return list(slots.values())


def test_real_page_alternatives_share_a_slot(cs):
  slots = _slots(cs)
  assert ["MATH-126g", "MATH-129"] in slots
  assert ["BISC-120Lg", "BISC-121Lg", "BISC-220Lg"] in slots
  assert ["CSCI-104L"] in slots


def test_real_page_requirement_tree_and_total(cs):
  titles = {r.title: r for r in cs.requirements}
  assert (
    titles["Mathematics"].parent_position
    == titles["Pre-Major Requirements"].position
  )
  assert titles["Mathematics"].units_min == 16.0
  assert "Take at least four" in titles["Core Electives"].notes
  assert cs.program.total_units == 128.0
  assert (cs.program.kind, cs.program.degree_type) == ("degree", "BS")


def test_footnotes_after_total_belong_to_the_program(cs, sample):
  assert "WRIT 340" in cs.program.description
  assert "Footnote" in sample.program.description
  assert all("Footnote" not in r.notes for r in sample.requirements)


def test_or_paragraph_and_trailing_or_both_join_slots(sample):
  assert ["ECON-203", "ECON-205"] in _slots(sample)
  assert ["ECON-330", "ECON-340"] in _slots(sample)
  assert ["MATH-118gx"] in _slots(sample)


def test_unit_ranges_and_nested_headings(sample):
  by_title = {r.title: r for r in sample.requirements}
  major = by_title["Major Requirements"]
  assert (major.units_min, major.units_max) == (12.0, 16.0)
  rule = by_title["Choose one of the following"]
  assert rule.parent_position == by_title["Electives"].position
  math = next(c for c in sample.choices if c.listed_code == "MATH-118gx")
  assert (math.units_min, math.units_max) == (2.0, 4.0)


def test_school_and_end_of_content(sample):
  assert sample.program.school == "Dornsife College"
  assert "Not part" not in sample.program.description


def test_ge_lists_and_names():
  page = """
  <h3>Core Literacies</h3>
  <h4>GE-A. The Arts</h4>
  <li class="acalog-course">AHIS 120g Foundations of Western Art Units: 4</li>
  <h4>GE-G: Global Perspectives I</h4>
  <li class="acalog-course">AHIS 120g Foundations of Western Art Units: 4</li>
  <h2>Writing</h2>
  <li class="acalog-course">WRIT 150 Writing Units: 4</li>
  """
  courses = _parse_catalogue.parse_ge_lists(page, 22)
  assert {(g.ge_code, g.listed_code) for g in courses} == {
    ("GE-A", "AHIS-120g"),
    ("GE-G", "AHIS-120g"),
  }
  assert _parse_catalogue.ge_category_names(page) == {
    "GE-A": "The Arts",
    "GE-G": "Global Perspectives I",
  }


@pytest.mark.parametrize(
  ("title", "expected"),
  [
    (
      "American Studies and Ethnicity (Asian American Studies) (BA)",
      (
        "American Studies and Ethnicity",
        "Asian American Studies",
        "degree",
        "BA",
      ),
    ),
    ("Art (BA)*", ("Art", None, "degree", "BA")),
    (
      "Applied Data Science (MS) (Online)",
      ("Applied Data Science", "Online", "degree", "MS"),
    ),
    ("Pharmacy (PharmD/MS)", ("Pharmacy", None, "degree", "PharmD/MS")),
    ("Minor in Business Law", ("Minor in Business Law", None, "minor", None)),
    ("General Education", ("General Education", None, "other", None)),
  ],
)
def test_program_identity(title, expected):
  assert _parse_catalogue.program_identity(title) == expected


def test_program_ids_disambiguate_repeated_titles():
  links = [
    _parse_catalogue.ProgramLink(1, "Computer Science (BS)"),
    _parse_catalogue.ProgramLink(2, "Computer Science (BS)"),
  ]
  assert _parse_catalogue.program_ids(links) == {
    1: "computer-science-bs",
    2: "computer-science-bs-2",
  }


@pytest.mark.parametrize(
  ("line", "total"),
  [
    ("Total units: 128", 128.0),
    ("Total minimum units: 132", 132.0),
    ("Total required units: 128", 128.0),
    ("Total Units Required: 128", 128.0),
    ("Total units required for the degree: 128", 128.0),
    ("Total program units: 84", 84.0),
    ("Total Units: Minimum of 32", 32.0),
    ("Total business units: 60", None),
    ("The degree requires a minimum of 128 units.", None),
  ],
)
def test_program_totals_and_not_subtotals(line, total):
  page = f"<h1>Sample (BS)</h1><h2>Core (8 units)</h2><p>{line}</p>"
  link = _parse_catalogue.ProgramLink(1, "Sample (BS)")
  parsed = _parse_catalogue.parse_program(page, 22, link, "sample-bs")
  assert parsed.program.total_units == total


def test_units_written_after_a_heading_label():
  page = "<h1>Sample (BA)</h1><h2>Elective Units: 6</h2><h2>Units: 4-8</h2>"
  link = _parse_catalogue.ProgramLink(1, "Sample (BA)")
  reqs = _parse_catalogue.parse_program(
    page, 22, link, "sample-ba"
  ).requirements
  assert [(r.title, r.units_min, r.units_max) for r in reqs] == [
    ("Elective", 6.0, 6.0),
    ("Units: 4-8", 4.0, 8.0),
  ]
