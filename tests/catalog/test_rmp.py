"""Tests for matching RateMyProfessors search results to instructors."""

from server.db import models
from server.db.ingest import _rmp


def _response(*nodes):
  return {
    "data": {"newSearch": {"teachers": {"edges": [{"node": n} for n in nodes]}}}
  }


def _node(first, last, rating=4.2, difficulty=3.1, count=12, again=80.0):
  return {
    "legacyId": 123,
    "firstName": first,
    "lastName": last,
    "department": "Computer Science",
    "avgRating": rating,
    "avgDifficulty": difficulty,
    "numRatings": count,
    "wouldTakeAgainPercent": again,
  }


CARTER = models.InstructorRow("carter slocum", "Carter", "Slocum")


def test_matches_last_name_and_first_initial():
  profile = _rmp.parse_profile(
    CARTER, _response(_node("Ann", "Slocum"), _node("Carl", "Slocum"))
  )
  assert profile is not None and profile.rating == 4.2


def test_rejects_same_surname_different_person():
  assert _rmp.parse_profile(CARTER, _response(_node("Ann", "Slocum"))) is None


def test_unrated_teacher_has_no_rating_and_no_take_again():
  profile = _rmp.parse_profile(
    CARTER, _response(_node("Carter", "Slocum", rating=0, count=0, again=-1))
  )
  assert profile is not None
  assert (profile.rating, profile.difficulty, profile.would_take_again) == (
    None,
    None,
    None,
  )


def test_empty_search_is_no_profile():
  assert _rmp.parse_profile(CARTER, _response()) is None
  assert _rmp.parse_profile(CARTER, {}) is None


def test_search_keys_are_filesystem_safe():
  key = _rmp.search_key("josé o'neil-smith")
  assert key.startswith("rmp/") and key.endswith(".json")
  assert "'" not in key and " " not in key
