"""Tests for parse_classes against trimmed real classes.usc.edu payloads."""

import collections
import json
import pathlib

import httpx
import pytest

from server.db.ingest import _cache, _classes_api, _parse_classes


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
TERM = 20271


@pytest.fixture(scope="module")
def listing() -> _parse_classes.Listing:
  raw = json.loads((FIXTURES / "listing.json").read_text(encoding="utf-8"))
  return _parse_classes.parse_listing(raw, TERM)


def test_course_codes_keep_usc_suffix_case(listing):
  codes = {c.code for c in listing.courses}
  assert {"CSCI-104L", "CHEM-251x", "CHEM-490x"} <= codes


def test_units_come_from_course_units(listing):
  units = {o.course_code: (o.units_min, o.units_max) for o in listing.offerings}
  assert units["CSCI-104L"] == (4.0, 4.0)
  assert units["CHEM-251x"] == (2.0, 2.0)
  assert units["CHEM-490x"] == (1.0, 8.0)


def test_optional_text_fields_are_kept(listing):
  offerings = {o.course_code: o for o in listing.offerings}
  assert offerings["CHEM-462L"].recommended_prep
  assert offerings["CHEM-108L"].duplicate_credit
  assert offerings["CSCI-104L"].course_notes is None


def test_prerequisite_options_and_their_ands(listing):
  rows = [
    (r.group_position, r.option_position, r.position, r.required_code)
    for r in listing.requisite_courses
    if r.course_code == "CSCI-420" and r.kind == "prerequisite"
  ]
  # CSCI 104, and (MATH 225, or EE 141 with one of MATH 126/127/129).
  assert (0, 0, 0, "CSCI-104") in rows
  assert (1, 0, 0, "MATH-225") in rows
  assert (1, 1, 0, "EE-141") in rows
  assert (1, 1, 1, "MATH-126") in rows
  groups = [g for g in listing.requisite_groups if g.course_code == "CSCI-420"]
  assert [g.required_count for g in groups] == [1, 1]


def test_corequisites_are_their_own_kind(listing):
  kinds = {
    (r.kind, r.required_code)
    for r in listing.requisite_courses
    if r.course_code == "CHEM-251x"
  }
  assert ("corequisite", "CHEM-322b") in kinds
  assert ("prerequisite", "CHEM-322a") in kinds


def test_restrictions_are_flat_and_marked_inclusive_or_not(listing):
  csci420 = [
    (r.kind, r.code, r.inclusive)
    for r in listing.restrictions
    if r.course_code == "CSCI-420"
  ]
  assert ("class", "U1", False) in csci420
  chem108 = [r for r in listing.restrictions if r.course_code == "CHEM-108L"]
  assert chem108 and all(r.kind == "major" and r.inclusive for r in chem108)


def test_link_codes_bundle_lecture_lab_and_quiz(listing):
  bundles = collections.Counter(
    (s.type, s.link_code)
    for s in listing.sections
    if s.course_code == "CSCI-104L"
  )
  assert bundles[("Lecture", "A")] == 1
  assert bundles[("Quiz", "A")] == 1
  assert bundles[("Lab", "A")] == 8
  assert bundles[("Lecture", "B")] == 1


def test_section_registration_fields(listing):
  sections = listing.sections
  assert any(s.requires_d_clearance for s in sections)
  assert all(s.waitlisted >= 0 and s.capacity >= 0 for s in sections)
  assert any(s.syllabus_url for s in sections)


def test_every_meeting_pattern_is_kept(listing):
  by_section = collections.defaultdict(list)
  for m in listing.meetings:
    by_section[m.section_id].append(m)
  assert max(len(v) for v in by_section.values()) > 1
  thursday = _parse_classes.DAY_BITS["Thu"]
  assert by_section["17523"][0].days == thursday


def test_tba_meetings_have_no_days_or_times(listing):
  tba = [m for m in listing.meetings if m.days == 0]
  assert tba
  assert all(m.start_minute is None and m.end_minute is None for m in tba)


def test_co_taught_sections_keep_every_instructor_in_order(listing):
  team = [
    s.instructor_key
    for s in sorted(listing.section_instructors, key=lambda s: s.position)
    if s.section_id == "30386"
  ]
  assert team == ["erdem biyik", "daniel seita"]


def test_department_listed_under_two_schools_keeps_the_first():
  raw = json.loads((FIXTURES / "schools.json").read_text(encoding="utf-8"))
  schools, departments = _parse_classes.parse_schools(raw)
  anat = [d for d in departments if d.code == "ANAT"]
  assert len(anat) == 1
  assert {s.code for s in schools} >= {"DNTR", "MEDK"}


def test_instructor_key_normalizes_spacing_and_case():
  assert _parse_classes.instructor_key(" Carter ", "SLOCUM") == "carter slocum"
  assert (
    _parse_classes.parse_instructor({"firstName": "", "lastName": ""}) is None
  )


def test_sequence_letters_join_the_code_before_the_suffix():
  raw = json.loads((FIXTURES / "listing.json").read_text(encoding="utf-8"))
  course = dict(raw["courses"][0], sequence="A", suffix="L", geCode="35")
  parsed = _parse_classes.parse_listing({"courses": [course]}, TERM)
  (code,) = {c.code for c in parsed.courses}
  assert code.endswith("AL")
  assert [g.usc_ge_code for g in parsed.usc_ge_codes] == ["35"]


def test_fetch_terms_filters_active(tmp_path: pathlib.Path):
  cache = _cache.RawCache(tmp_path)
  terms_payload = [
    {"termCode": 20271, "year": 2027, "season": "Spring", "status": "Active"},
    {"termCode": 20263, "year": 2026, "season": "Fall", "status": "Active"},
    {"termCode": 20253, "year": 2025, "season": "Fall", "status": "Inactive"},
  ]

  def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/Terms/All")
    return httpx.Response(200, json=terms_payload)

  transport = httpx.MockTransport(handler)
  with httpx.Client(transport=transport) as client:
    active_terms = _classes_api.fetch_terms(client, cache)

  assert active_terms == [20271, 20263]
  assert cache.read_json(_classes_api.TERMS_KEY) == terms_payload
