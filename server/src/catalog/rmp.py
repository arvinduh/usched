"""RateMyProfessors: fetch searches into the raw cache, parse profiles.

The fetch side caches each instructor's raw search response, including
empty ones, so instructors not on RMP are not searched again until the
cache entry ages out. The parse side picks the matching teacher from a
response; it is pure.
"""

import concurrent.futures
import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

import httpx
from absl import logging

from server.src.catalog import cache, http, records


GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
USC_SCHOOL_ID = "U2Nob29sLTEzODE="
# RMP's public web client authenticates with this fixed demo credential.
_AUTH = "Basic dGVzdDp0ZXN0"
_WORKERS = 4
_QUERY = """
query TeacherSearch($query: TeacherSearchQuery!) {
  newSearch {
    teachers(query: $query) {
      edges {
        node {
          legacyId
          firstName
          lastName
          department
          avgRating
          avgDifficulty
          numRatings
          wouldTakeAgainPercent
        }
      }
    }
  }
}
"""


def search_key(instructor_key: str) -> str:
  """Cache key for one instructor's search, safe for any name."""
  digest = hashlib.sha1(instructor_key.encode("utf-8")).hexdigest()[:16]
  return f"rmp/{digest}.json"


def fetch_searches(
  client: httpx.Client,
  raw: cache.RawCache,
  instructors: Iterable[records.Instructor],
  max_age_s: float,
) -> tuple[int, int]:
  """Searches RMP for instructors without a fresh cached result.

  Returns:
    (searched, failed) counts.
  """
  pending = [
    i for i in instructors if not raw.is_fresh(search_key(i.key), max_age_s)
  ]

  def search(instructor: records.Instructor) -> bool:
    body = {
      "query": _QUERY,
      "variables": {
        "query": {
          "text": f"{instructor.first_name} {instructor.last_name}",
          "schoolID": USC_SCHOOL_ID,
        }
      },
    }
    try:
      response = http.request(
        client,
        "POST",
        GRAPHQL_URL,
        json=body,
        headers={"Authorization": _AUTH, "Content-Type": "application/json"},
      )
    except httpx.HTTPError as e:
      logging.warning("RMP search failed for %s: %s", instructor.key, e)
      return False
    raw.write_text(search_key(instructor.key), response.text)
    return True

  with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
    results = list(pool.map(search, pending))
  return sum(results), results.count(False)


def parse_profile(
  instructor: records.Instructor, response: Mapping[str, Any]
) -> records.RmpProfile | None:
  """Picks the teacher matching `instructor` from a search response.

  A teacher matches when last names agree and first names agree on their
  first letter, which tolerates "Mike" vs "Michael" but rejects a different
  person who shares a surname. Returns None when nobody matches.
  """
  edges = (
    ((response.get("data") or {}).get("newSearch") or {}).get("teachers") or {}
  ).get("edges") or []
  last = instructor.last_name.lower()
  first = instructor.first_name.lower()
  for edge in edges:
    node = edge.get("node") or {}
    if str(node.get("lastName") or "").lower() != last:
      continue
    node_first = str(node.get("firstName") or "").lower()
    if first and node_first and node_first[0] != first[0]:
      continue
    num_ratings = int(node.get("numRatings") or 0)
    take_again = node.get("wouldTakeAgainPercent")
    return records.RmpProfile(
      instructor_key=instructor.key,
      rmp_id=int(node["legacyId"]),
      department=str(node.get("department") or ""),
      rating=_rating(node.get("avgRating"), num_ratings),
      difficulty=_rating(node.get("avgDifficulty"), num_ratings),
      num_ratings=num_ratings,
      would_take_again=(
        float(take_again)
        if take_again is not None and take_again >= 0
        else None
      ),
    )
  return None


def _rating(value: Any, num_ratings: int) -> float | None:
  """RMP reports 0 for unrated teachers; that is missing, not zero."""
  if value is None or num_ratings == 0:
    return None
  return float(value)
