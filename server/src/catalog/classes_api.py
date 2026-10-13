"""Fetches classes.usc.edu into the raw cache: terms, schools, listings.

Owns the API's URLs and cache keys. Only the network side lives here; what
the payloads mean is parse_classes' concern. Listings are fetched per
(term, school, program), the API's natural unit, in parallel.
"""

import concurrent.futures
import dataclasses

import httpx
from absl import logging

from server.src.catalog import cache, http, parse_classes


BASE_URL = "https://classes.usc.edu/api"
TERMS_KEY = "classes/terms.json"
_WORKERS = 8


def schools_key(term: int) -> str:
  """Cache key for a term's school and program list."""
  return f"classes/{term}/schools.json"


def listing_key(term: int, school: str, program: str) -> str:
  """Cache key for one program's course listing in a term."""
  return f"classes/{term}/listings/{school}-{program}.json"


@dataclasses.dataclass
class Report:
  """What one fetch did."""

  fetched: int = 0
  skipped: int = 0
  failed: list[str] = dataclasses.field(default_factory=list)


def fetch_terms(client: httpx.Client, raw: cache.RawCache) -> list[int]:
  """Fetches the term list and returns the codes USC marks Active."""
  response = http.request(client, "GET", f"{BASE_URL}/Terms/All")
  raw.write_text(TERMS_KEY, response.text)
  terms = parse_classes.parse_terms(response.json())
  return sorted(
    (t.code for t in terms if t.status.lower() == "active"), reverse=True
  )


def fetch_term(
  client: httpx.Client,
  raw: cache.RawCache,
  term: int,
  max_age_s: float,
) -> Report:
  """Fetches a term's schools and every program listing not fetched lately.

  Args:
    client: Shared HTTP client.
    raw: Cache to write into.
    term: Term code, e.g. 20271.
    max_age_s: Listings younger than this are kept as-is.

  Returns:
    Counts of fetched and skipped listings, and the keys that failed.
  """
  key = schools_key(term)
  if not raw.is_fresh(key, max_age_s):
    response = http.request(
      client, "GET", f"{BASE_URL}/Schools/TermCode", params={"termCode": term}
    )
    raw.write_text(key, response.text)
  schools = raw.read_json(key)

  report = Report()
  pending: list[tuple[str, str]] = []
  for school in schools:
    for program in school.get("programs") or []:
      pair = (str(school["prefix"]), str(program["prefix"]))
      if raw.is_fresh(listing_key(term, *pair), max_age_s):
        report.skipped += 1
      else:
        pending.append(pair)

  def fetch(pair: tuple[str, str]) -> tuple[str, str | None]:
    school, program = pair
    target = listing_key(term, school, program)
    try:
      response = http.request(
        client,
        "GET",
        f"{BASE_URL}/Courses/CoursesByTermSchoolProgram",
        params={"termCode": term, "school": school, "program": program},
      )
    except httpx.HTTPError as e:
      return target, str(e)
    raw.write_text(target, response.text)
    return target, None

  with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
    for target, error in pool.map(fetch, pending):
      if error is None:
        report.fetched += 1
      else:
        logging.warning("Failed to fetch %s: %s", target, error)
        report.failed.append(target)
  return report
