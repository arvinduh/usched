"""Command-line entry point: fetch USC data into the cache, build the DB.

    uv run catalog            # fetch what is stale, then build
    uv run catalog fetch      # refresh the raw cache only
    uv run catalog build      # rebuild the database offline from the cache

Each source keeps its own freshness window, so routine runs only refetch
section listings; RateMyProfessors and the catalogue change slowly.

A fetch that fails keeps the cache's previous copy, so the build still
runs, but the command then exits 1: a scheduled refresh never reports
success while serving stale data. A build that fails verification leaves
the live database untouched and exits 1 as well.
"""

import logging as std_logging
import sys
from collections.abc import Sequence

import httpx
from absl import app, flags, logging

from server.src.catalog import (
  build,
  cache,
  catalogue_site,
  classes_api,
  http,
  parse_classes,
  records,
  rmp,
)


_HOUR_S = 3600.0

FLAGS = flags.FLAGS
flags.DEFINE_list(
  "terms", [], "Term codes to fetch, e.g. 20271. Default: every Active term."
)
flags.DEFINE_float(
  "listings_max_age_hours", 12, "Refetch section listings older than this."
)
flags.DEFINE_float(
  "rmp_max_age_days", 30, "Re-search RateMyProfessors entries older than this."
)
flags.DEFINE_float(
  "catalogue_max_age_days", 7, "Refetch catalogue pages older than this."
)
flags.DEFINE_bool("skip_rmp", False, "Skip RateMyProfessors searches.")
flags.DEFINE_bool(
  "skip_catalogue", False, "Skip catalogue programs and courses."
)


def fetch(raw: cache.RawCache) -> int:
  """Refreshes the raw cache from every source; returns how many failed."""
  failures = 0
  with http.client() as client:
    active = classes_api.fetch_terms(client, raw)
    terms = [int(t) for t in FLAGS.terms] or active
    for term in terms:
      report = classes_api.fetch_term(
        client, raw, term, FLAGS.listings_max_age_hours * _HOUR_S
      )
      print(
        f"Term {term}: fetched {report.fetched} listings, "
        f"{report.skipped} fresh, {len(report.failed)} failed"
      )
      failures += len(report.failed)
    if not FLAGS.skip_rmp:
      failures += _fetch_rmp(client, raw, terms)
  if not FLAGS.skip_catalogue:
    catoid, cookies, agent = catalogue_site.fetch_index(raw)
    fetched, fresh, failed = catalogue_site.fetch_programs(
      raw, catoid, cookies, agent, FLAGS.catalogue_max_age_days * 24 * _HOUR_S
    )
    print(
      f"Catalogue {catoid}: fetched {fetched} programs, {fresh} fresh, "
      f"{len(failed)} failed"
    )
    failures += len(failed)
    fetched, fresh, failed = catalogue_site.fetch_courses(
      raw, catoid, cookies, agent, FLAGS.catalogue_max_age_days * 24 * _HOUR_S
    )
    print(
      f"Catalogue {catoid}: fetched {fetched} course pages, {fresh} fresh, "
      f"{len(failed)} failed"
    )
    failures += len(failed)
  return failures


def _fetch_rmp(
  client: httpx.Client, raw: cache.RawCache, terms: Sequence[int]
) -> int:
  instructors: dict[str, records.Instructor] = {}
  for term in terms:
    for key in raw.keys(f"classes/{term}/listings", "*.json"):
      listing = parse_classes.parse_listing(raw.read_json(key), term)
      instructors.update((i.key, i) for i in listing.instructors)
  searched, failed = rmp.fetch_searches(
    client,
    raw,
    instructors.values(),
    FLAGS.rmp_max_age_days * 24 * _HOUR_S,
  )
  print(f"RateMyProfessors: searched {searched}, {failed} failed")
  return failed


def main(argv: Sequence[str]) -> None:
  # httpx logs every request at INFO; thousands of them bury the summary.
  std_logging.getLogger("httpx").setLevel(std_logging.WARNING)
  stages = argv[1:] or ["fetch", "build"]
  unknown = set(stages) - {"fetch", "build"}
  if unknown:
    raise app.UsageError(f"Unknown stage(s): {', '.join(sorted(unknown))}")
  raw = cache.RawCache()
  failures = fetch(raw) if "fetch" in stages else 0
  if "build" in stages:
    try:
      built = build.build(raw)
    except build.VerificationError as e:
      print(f"Build failed verification; the live catalog is unchanged: {e}")
      sys.exit(1)
    logging.info("Built %s", build.DEFAULT_DB)
    print("Built " + ", ".join(f"{n} {t}" for t, n in built.counts.items()))
    print(
      "Verified: "
      + ", ".join(f"{name} {rate}%" for name, rate in built.rates.items())
    )
  if failures:
    print(f"{failures} fetches failed; the cache kept their previous copies.")
    sys.exit(1)


def cli_main() -> None:
  """Console-script entry point."""
  app.run(main)


if __name__ == "__main__":
  cli_main()
