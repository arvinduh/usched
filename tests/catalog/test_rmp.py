"""Tests for matching RateMyProfessors search results to instructors."""

import pathlib

import httpx
import pytest

from server.db import models
from server.db.ingest import _cache, _rmp


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


@pytest.mark.parametrize("payload", [_response(), {}])
def test_empty_search_is_no_profile(payload):
  assert _rmp.parse_profile(CARTER, payload) is None


@pytest.mark.parametrize(
  "name",
  ["josé o'neil-smith", "Carter Slocum", "O'Reilly"],
)
def test_search_keys_are_filesystem_safe(name: str):
  key = _rmp.search_key(name)
  assert key.startswith("rmp/") and key.endswith(".json")
  assert "'" not in key and " " not in key


def test_fetch_searches_writes_cache_and_handles_failures(
  tmp_path: pathlib.Path,
):
  cache = _cache.RawCache(tmp_path)
  carter = models.InstructorRow("carter slocum", "Carter", "Slocum")
  failing = models.InstructorRow("fail instructor", "Fail", "Instructor")

  def handler(request: httpx.Request) -> httpx.Response:
    if b"Fail" in request.read():
      return httpx.Response(400, content=b"Bad request")
    return httpx.Response(200, json=_response(_node("Carter", "Slocum")))

  transport = httpx.MockTransport(handler)
  with httpx.Client(transport=transport) as client:
    searched, failed = _rmp.fetch_searches(
      client, cache, [carter, failing], max_age_s=3600
    )

  assert searched == 1
  assert failed == 1
  assert cache.is_fresh(_rmp.search_key(carter.key), 3600)
  assert not cache.is_fresh(_rmp.search_key(failing.key), 3600)
