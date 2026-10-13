"""Fetches catalogue.usc.edu (Acalog) pages into the raw cache.

The site sits behind a bot firewall, so a headless browser loads the
program index once to obtain session cookies; program pages and the
course index are then fetched over plain HTTP with those cookies, in
parallel. The current catalogue year is discovered from the site rather
than hard-coded.
"""

import concurrent.futures
import re

import httpx
from absl import logging

from server import config
from server.src.catalog import cache, http, parse_catalogue, parse_courses


BASE_URL = config.USC_CATALOGUE_BASE
_WORKERS = 6
_NAV_TIMEOUT_MS = 60_000


def index_key(catoid: int) -> str:
  """Cache key for a catalogue's program index page."""
  return f"catalogue/{catoid}/index.html"


def program_key(catoid: int, poid: int) -> str:
  """Cache key for one program page."""
  return f"catalogue/{catoid}/programs/{poid}.html"


def courses_key(catoid: int, page: int) -> str:
  """Cache key for one expanded course index page."""
  return f"catalogue/{catoid}/courses/{page:03d}.html"


def fetch_index(raw: cache.RawCache) -> tuple[int, dict[str, str], str]:
  """Loads the current catalogue's program index through a browser.

  Returns:
    (catoid, session cookies, the browser's user agent) for later requests.

  Raises:
    RuntimeError: The site did not expose a program index link.
  """
  # Imported lazily: Playwright is heavy and only this stage needs it.
  from playwright.sync_api import sync_playwright

  with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
      page = browser.new_page()
      page.goto(BASE_URL, wait_until="networkidle", timeout=_NAV_TIMEOUT_MS)
      home = page.content()
      link = re.search(
        r'href="([^"]*content\.php\?catoid=(\d+)&(?:amp;)?navoid=\d+)"[^>]*>\s*'
        r"Programs",
        home,
      )
      if link is None:
        raise RuntimeError("Catalogue home page has no Programs link")
      catoid = int(link.group(2))
      url = link.group(1).replace("&amp;", "&")
      page.goto(
        url if url.startswith("http") else f"{BASE_URL}/{url.lstrip('/')}",
        wait_until="networkidle",
        timeout=_NAV_TIMEOUT_MS,
      )
      raw.write_text(index_key(catoid), page.content())
      cookies = {
        c.get("name", ""): c.get("value", "") for c in page.context.cookies()
      }
      user_agent = str(page.evaluate("() => navigator.userAgent"))
    finally:
      browser.close()
  return catoid, cookies, user_agent


def fetch_programs(
  raw: cache.RawCache,
  catoid: int,
  cookies: dict[str, str],
  user_agent: str,
  max_age_s: float,
) -> tuple[int, int, list[str]]:
  """Fetches every program page listed in the index not fetched lately.

  Returns:
    (fetched, skipped, failed keys).
  """
  links = parse_catalogue.parse_index(raw.read_text(index_key(catoid)))
  pending = [
    link
    for link in links
    if not raw.is_fresh(program_key(catoid, link.poid), max_age_s)
  ]

  with http.client(
    cookies=cookies,
    headers={"User-Agent": user_agent, "Accept": "text/html"},
  ) as client:

    def fetch(link: parse_catalogue.ProgramLink) -> str | None:
      key = program_key(catoid, link.poid)
      try:
        response = http.request(
          client,
          "GET",
          f"{BASE_URL}/preview_program.php",
          params={"catoid": catoid, "poid": link.poid},
        )
      except httpx.HTTPError as e:
        logging.warning("Failed to fetch program %s: %s", link.title, e)
        return key
      raw.write_text(key, response.text)
      return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
      failed = [key for key in pool.map(fetch, pending) if key is not None]
  return len(pending) - len(failed), len(links) - len(pending), failed


def fetch_courses(
  raw: cache.RawCache,
  catoid: int,
  cookies: dict[str, str],
  user_agent: str,
  max_age_s: float,
) -> tuple[int, int, list[str]]:
  """Fetches every page of the expanded course index not fetched lately.

  Page one comes first because its pager says how many pages there are.

  Returns:
    (fetched, skipped, failed keys).

  Raises:
    httpx.HTTPError: Page one could not be fetched, so the count is unknown.
  """
  navoid = parse_courses.course_index_navoid(raw.read_text(index_key(catoid)))
  with http.client(
    cookies=cookies,
    headers={"User-Agent": user_agent, "Accept": "text/html"},
  ) as client:

    def get(page: int) -> str:
      return http.request(
        client,
        "GET",
        f"{BASE_URL}/content.php",
        params={
          "catoid": catoid,
          "navoid": navoid,
          "filter[cpage]": page,
          "expand": 1,
        },
      ).text

    def fetch(page: int) -> str | None:
      key = courses_key(catoid, page)
      try:
        raw.write_text(key, get(page))
      except httpx.HTTPError as e:
        logging.warning("Failed to fetch course page %d: %s", page, e)
        return key
      return None

    first = courses_key(catoid, 1)
    fetched_first = not raw.is_fresh(first, max_age_s)
    if fetched_first:
      raw.write_text(first, get(1))
    pages = parse_courses.page_count(raw.read_text(first))
    pending = [
      p
      for p in range(2, pages + 1)
      if not raw.is_fresh(courses_key(catoid, p), max_age_s)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
      failed = [key for key in pool.map(fetch, pending) if key is not None]
  fetched = len(pending) - len(failed) + fetched_first
  return fetched, pages - fetched - len(failed), failed
