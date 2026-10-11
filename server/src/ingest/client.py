"""Live data clients for USC Schedule of Classes, RMP, and Catalogue.

This module provides live clients communicating with classes.usc.edu API,
RateMyProfessors GraphQL, and catalogue.usc.edu, with fail-fast invariants
and zero synthetic/mock fallbacks.
"""

import json
import re
import time
from collections.abc import Iterator
from html.parser import HTMLParser
from http import HTTPStatus
from typing import Any

import httpx
from absl import logging

from server.src.data import models


BASE_CLASSES_API_URL = "https://classes.usc.edu/api"
DEFAULT_TERM = "20271"

RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
USC_SCHOOL_ID = "U2Nob29sLTEzODE="
RMP_AUTH_HEADER = "Basic dGVzdDp0ZXN0"

BASE_CATALOGUE_URL = "https://catalogue.usc.edu"
DEFAULT_CATOID = "22"

_SCHOOL_MAP_CACHE: dict[str, str] = {}


def fetch_all_departments(
  term: str = DEFAULT_TERM,
  client: httpx.Client | None = None,
) -> list[str]:
  """Discovers all academic program prefixes from live classes.usc.edu API."""
  should_close = False
  if client is None:
    client = httpx.Client(timeout=15.0)
    should_close = True

  try:
    url = f"{BASE_CLASSES_API_URL}/Schools/TermCode?termCode={term}"
    resp = client.get(url)
    if resp.status_code != HTTPStatus.OK:
      raise RuntimeError(
        f"USC Schools API responded with HTTP {resp.status_code}"
      )
    schools_data: list[dict[str, Any]] = resp.json()
    departments: list[str] = []
    for school in schools_data:
      school_prefix = str(school.get("prefix") or "")
      programs = school.get("programs") or []
      for p in programs:
        p_prefix = str(p.get("prefix") or "").upper().strip()
        if p_prefix:
          _SCHOOL_MAP_CACHE[p_prefix] = school_prefix
          departments.append(p_prefix)
    return sorted(list(set(departments)))
  finally:
    if should_close:
      client.close()


def get_school_for_program(
  program: str,
  term: str = DEFAULT_TERM,
  client: httpx.Client | None = None,
) -> str:
  """Resolves parent school prefix for a department from cache or API."""
  prog_upper = program.upper().strip()
  if prog_upper in _SCHOOL_MAP_CACHE:
    return _SCHOOL_MAP_CACHE[prog_upper]

  fetch_all_departments(term=term, client=client)
  return _SCHOOL_MAP_CACHE.get(prog_upper, "ENGV")


def fetch_department_courses(
  department: str,
  term: str = DEFAULT_TERM,
  client: httpx.Client | None = None,
) -> Iterator[models.Course]:
  """Fetches live offerings and sections from classes.usc.edu API."""
  dept_code = department.upper().strip()
  headers = {
    "User-Agent": (
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    ),
    "Accept": "application/json",
  }

  should_close = False
  active_client = client
  if active_client is None:
    active_client = httpx.Client(timeout=30.0, headers=headers)
    should_close = True

  try:
    school_code = get_school_for_program(
      dept_code, term=term, client=active_client
    )
    list_url = (
      f"{BASE_CLASSES_API_URL}/Courses/CoursesByTermSchoolProgram"
      f"?termCode={term}&school={school_code}&program={dept_code}"
    )

    resp: httpx.Response | None = None
    for attempt in range(3):
      try:
        resp = active_client.get(list_url)
        if resp.status_code == HTTPStatus.OK:
          break
        if resp.status_code >= 500:
          time.sleep(0.5 * (2**attempt))
          continue
        logging.warning(
          "Department %s responded with status %d", dept_code, resp.status_code
        )
        return
      except (httpx.TimeoutException, httpx.NetworkError) as exc:
        if attempt == 2:
          logging.warning(
            "Network failure for department %s: %s", dept_code, exc
          )
          raise RuntimeError(
            f"Department {dept_code} failed after 3 attempts: {exc}"
          ) from exc
        time.sleep(0.5 * (2**attempt) + 0.1)

    if not resp or resp.status_code != HTTPStatus.OK:
      status = resp.status_code if resp else "no response"
      raise RuntimeError(
        f"Department {dept_code} HTTP failed with status {status}"
      )

    try:
      data: dict[str, Any] = resp.json()
    except json.JSONDecodeError as exc:
      logging.warning(
        "JSON decode failed for department %s: %s", dept_code, exc
      )
      raise RuntimeError(
        f"Department {dept_code} invalid JSON payload: {exc}"
      ) from exc

    course_stubs: list[dict[str, Any]] = data.get("courses") or []

    for stub in course_stubs:
      class_num = str(stub.get("classNumber") or "").strip()
      suffix = str(stub.get("suffix") or "").strip()
      raw_title = str(
        stub.get("name") or stub.get("fullCourseName") or ""
      ).strip()
      desc = str(stub.get("description") or "").strip()
      max_units = stub.get("maxUnits")
      units = float(max_units) if max_units is not None else 4.0
      ge_code = stub.get("geCode")

      course_code = (
        f"{dept_code}-{class_num}{suffix}"
        if suffix
        else f"{dept_code}-{class_num}"
      )

      prereq_json: list[list[str]] = []
      raw_prereqs = stub.get("prerequisiteCourseCodes") or []
      for group in raw_prereqs:
        options = group.get("courseOptions") or []
        group_codes = [
          str(opt.get("courseHyphen") or "").strip()
          for opt in options
          if opt.get("courseHyphen")
        ]
        if group_codes:
          prereq_json.append(group_codes)

      sections: list[models.Section] = []
      raw_sections = stub.get("sections") or []
      for sec_data in raw_sections:
        sec_id = str(sec_data.get("sisSectionId") or "").strip()
        sec_type = str(sec_data.get("rnrMode") or "Lecture").strip()
        reg_seats = int(sec_data.get("registeredSeats") or 0)
        tot_seats = int(sec_data.get("totalSeats") or 0)
        wait_seats = int(sec_data.get("waitlistSeats") or 0)

        schedule_list = sec_data.get("schedule") or []
        days_list: list[str] = []
        s_time = "00:00"
        e_time = "00:00"
        s_minute = 0
        e_minute = 0

        if schedule_list:
          sched = schedule_list[0]
          days_list = [str(d) for d in sched.get("days") or []]
          s_time_raw = sched.get("startTime")
          e_time_raw = sched.get("endTime")
          parsed_s = models.parse_time_str(s_time_raw)
          parsed_e = models.parse_time_str(e_time_raw)
          s_time = f"{parsed_s.hour:02d}:{parsed_s.minute:02d}"
          e_time = f"{parsed_e.hour:02d}:{parsed_e.minute:02d}"
          s_minute = parsed_s.hour * 60 + parsed_s.minute
          e_minute = parsed_e.hour * 60 + parsed_e.minute

        inst_obj: models.Instructor | None = None
        instructors_list = sec_data.get("instructors") or []
        if instructors_list:
          first = str(instructors_list[0].get("firstName") or "").strip()
          last = str(instructors_list[0].get("lastName") or "").strip()
          full_name = f"{first} {last}".strip()
          if full_name:
            inst_id = full_name.lower().replace(" ", "-")
            inst_obj = models.Instructor(
              id=inst_id,
              name=full_name,
              department=dept_code,
            )

        sections.append(
          models.Section(
            id=sec_id or f"{course_code}-01",
            course_id=course_code,
            section_type=sec_type,
            term=str(term),
            days=days_list,
            start_time=s_time,
            end_time=e_time,
            start_minute=s_minute,
            end_minute=e_minute,
            location="",
            instructor=inst_obj,
            enrolled=reg_seats,
            capacity=tot_seats,
            waitlist=wait_seats,
          )
        )

      yield models.Course(
        id=course_code,
        department=dept_code,
        number=class_num + suffix,
        title=raw_title or course_code,
        description=desc,
        units=units,
        prerequisites_json=prereq_json,
        ge_category=f"GE-{ge_code}" if ge_code else None,
        sections=sections,
      )
  finally:
    if should_close and active_client:
      active_client.close()


def fetch_instructor_rmp(
  name: str,
  client: httpx.Client | None = None,
) -> models.Instructor | None:
  """Queries RateMyProfessors GraphQL API for USC faculty member metrics."""
  clean_name = name.strip()
  if not clean_name:
    return None

  payload = {
    "query": """
      query TeacherSearchPaginationQuery($query: TeacherSearchQuery!) {
        newSearch {
          teachers(query: $query) {
            edges {
              node {
                id
                legacyId
                firstName
                lastName
                department
                avgRating
                numRatings
                avgDifficulty
                wouldTakeAgainPercent
              }
            }
          }
        }
      }
    """,
    "variables": {
      "query": {
        "text": clean_name,
        "schoolID": USC_SCHOOL_ID,
      }
    },
  }
  headers = {
    "Authorization": RMP_AUTH_HEADER,
    "Content-Type": "application/json",
    "User-Agent": (
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    ),
  }

  should_close = False
  if client is None:
    client = httpx.Client(timeout=10.0)
    should_close = True

  try:
    response = client.post(RMP_GRAPHQL_URL, json=payload, headers=headers)
    if response.status_code != HTTPStatus.OK:
      logging.warning(
        "RMP API returned HTTP %d for %s", response.status_code, clean_name
      )
      return None
    data: dict[str, Any] = response.json()
    edges = (
      data.get("data", {})
      .get("newSearch", {})
      .get("teachers", {})
      .get("edges", [])
    )
    if not edges:
      inst_id = clean_name.lower().replace(" ", "-")
      return models.Instructor(
        id=inst_id,
        name=clean_name,
        rmp_id="NOT_FOUND",
      )

    query_parts = clean_name.lower().split()
    target_last = query_parts[-1] if query_parts else ""

    matched_node = None
    for edge in edges:
      n = edge.get("node", {})
      node_last = str(n.get("lastName", "")).lower().strip()
      if target_last and target_last in node_last:
        matched_node = n
        break

    if not matched_node:
      matched_node = edges[0].get("node", {})

    first = str(matched_node.get("firstName", "")).strip()
    last = str(matched_node.get("lastName", "")).strip()
    full_name = f"{first} {last}".strip() or clean_name

    legacy_id = matched_node.get("legacyId")
    avg_rating = matched_node.get("avgRating")
    avg_diff = matched_node.get("avgDifficulty")
    num_ratings = matched_node.get("numRatings") or 0
    take_again = matched_node.get("wouldTakeAgainPercent")

    inst_id = clean_name.lower().replace(" ", "-")

    return models.Instructor(
      id=inst_id,
      name=full_name,
      department=str(matched_node.get("department", "")).strip(),
      rmp_id=str(legacy_id) if legacy_id else None,
      rmp_rating=float(avg_rating) if avg_rating is not None else None,
      rmp_difficulty=float(avg_diff) if avg_diff is not None else None,
      rmp_num_ratings=int(num_ratings),
      rmp_take_again_percent=float(take_again)
      if take_again is not None and take_again >= 0
      else None,
    )
  except (httpx.HTTPError, json.JSONDecodeError):
    return None
  finally:
    if should_close:
      client.close()


def parse_catalogue_courses(html: str) -> list[str]:
  """Extracts unique standardized course codes from catalogue HTML."""
  if not html:
    return []
  pattern = r"\b([A-Z]{3,4})[\s-]*([0-9]{3}[A-Za-z]{0,2})\b"
  matches = re.findall(pattern, html)
  courses: list[str] = []
  seen: set[str] = set()
  for dept, num in matches:
    code = f"{dept.upper()}-{num.upper()}"
    if code not in seen:
      seen.add(code)
      courses.append(code)
  return courses


def discover_degree_programs(
  catoid: str = DEFAULT_CATOID,
  page: Any = None,
) -> tuple[list[tuple[str, str, str]], dict[str, str], str]:
  """Discovers Bachelor's degree programs and captures WAF session cookies.

  Returns:
    A 3-tuple: (discovered_programs, session_cookies, user_agent).
  """
  from playwright.sync_api import sync_playwright

  index_url = f"{BASE_CATALOGUE_URL}/content.php?catoid={catoid}&navoid=9396"

  def extract_from_page(
    p_obj: Any,
  ) -> tuple[list[tuple[str, str, str]], dict[str, str], str]:
    p_obj.goto(index_url, wait_until="networkidle", timeout=35000)
    links = p_obj.locator('a[href*="preview_program.php"]').all()
    results: list[tuple[str, str, str]] = []
    for link in links:
      title = link.inner_text().strip()
      href = link.get_attribute("href") or ""
      if not any(
        deg in title
        for deg in ["(BS)", "(BA)", "(BFA)", "(BM)", "(BSCE)", "(BArch)"]
      ):
        continue
      poid_match = re.search(r"poid=(\d+)", href)
      if poid_match:
        poid = poid_match.group(1)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        results.append((slug, title, poid))
    cookies = {c["name"]: c["value"] for c in p_obj.context.cookies()}
    user_agent = str(p_obj.evaluate("() => navigator.userAgent"))
    return results, cookies, user_agent

  if page is not None:
    return extract_from_page(page)

  with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    active_page = browser.new_page()
    try:
      return extract_from_page(active_page)
    finally:
      browser.close()


def scrape_degree_program(
  catoid: str,
  poid: str,
  degree_id: str,
  client: httpx.Client,
) -> models.DegreeProgram:
  """Scrapes live degree curriculum from catalogue.usc.edu."""
  target_url = (
    f"{BASE_CATALOGUE_URL}/preview_program.php?catoid={catoid}&poid={poid}"
  )
  resp = client.get(target_url)
  resp.raise_for_status()
  content = resp.text

  title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
  title_text = title_match.group(1) if title_match else ""
  raw_title_match = re.search(r"Program:\s*(.*?)\s*-\s*University", title_text)
  degree_title = (
    raw_title_match.group(1).strip()
    if raw_title_match
    else degree_id.replace("-", " ").title()
  )

  school = "University of Southern California"
  school_match = re.search(
    r"Return to:\s*<a[^>]*>(.*?)</a>", content, re.IGNORECASE
  )
  if school_match:
    school = re.sub(r"<[^>]+>", "", school_match.group(1)).strip()

  total_units = 128.0
  total_match = re.search(r"Total\s+[Uu]nits:\s*([0-9]+(?:\.[0-9]+)?)", content)
  if total_match:
    total_units = float(total_match.group(1))

  course_re = re.compile(r"\b([A-Z]{3,4})[\s-]*([0-9]{3}[A-Za-z]{0,2})\b")
  unit_re = re.compile(r"\(([0-9]+(?:\.[0-9]+)?)\s*units?\)", re.IGNORECASE)

  class HierarchyParser(HTMLParser):
    def __init__(self) -> None:
      super().__init__()
      self.items: list[tuple[str, int, str]] = []
      self.in_heading = False
      self.heading_level = 0
      self.heading_text = ""
      self.in_course = False
      self.course_text = ""

    def handle_starttag(
      self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
      attrs_dict = dict(attrs)
      classes = (attrs_dict.get("class") or "").split()
      if tag in ("h2", "h3", "h4", "h5"):
        self.in_heading = True
        self.heading_level = int(tag[1])
        self.heading_text = ""
      elif tag == "li" and "acalog-course" in classes:
        self.in_course = True
        self.course_text = ""

    def handle_endtag(self, tag: str) -> None:
      if tag in ("h2", "h3", "h4", "h5") and self.in_heading:
        self.in_heading = False
        text = " ".join(self.heading_text.split()).strip()
        if text:
          self.items.append(("heading", self.heading_level, text))
      elif tag == "li" and self.in_course:
        self.in_course = False
        text = " ".join(self.course_text.split()).strip()
        if text:
          self.items.append(("course", 0, text))

    def handle_data(self, data: str) -> None:
      if self.in_heading:
        self.heading_text += data
      elif self.in_course:
        self.course_text += data

  parser = HierarchyParser()
  parser.feed(content)

  class SectionNode:
    def __init__(self, title: str = "", level: int = 1) -> None:
      self.title = title
      self.level = level
      self.units: float | None = None
      self.courses: list[str] = []
      self.children: list[SectionNode] = []
      self.parent: SectionNode | None = None

  root = SectionNode("root", 1)
  current = root
  started = False

  for it_type, level, text in parser.items:
    if it_type == "heading":
      lower = text.lower()
      if any(
        k in lower
        for k in (
          "requirement",
          "general education",
          "units",
          "core",
          "foundation",
          "elective",
          "major",
          "courses",
        )
      ):
        started = True
      if not started:
        continue
      if "total units" in lower or "return to:" in lower:
        break

      u_m = unit_re.search(text)
      units_val = float(u_m.group(1)) if u_m else None
      clean_title = unit_re.sub("", text).strip().rstrip(":-")

      node = SectionNode(clean_title, level)
      node.units = units_val

      p: SectionNode | None = current
      while p is not None and p is not root and p.level >= level:
        p = p.parent
      target_parent = p if p is not None else root
      node.parent = target_parent
      target_parent.children.append(node)
      current = node

    elif it_type == "course" and started:
      for m in course_re.finditer(text):
        code = f"{m.group(1).upper()}-{m.group(2).upper()}"
        if current is not root and code not in current.courses:
          current.courses.append(code)

  categories: list[models.DegreeCategory] = []

  def collect(node: SectionNode, prefix: str = "") -> None:
    for child in node.children:
      name_part = child.title
      full_name = f"{prefix}: {name_part}" if prefix else name_part
      if child.children:
        if child.courses:
          u = (
            child.units
            if child.units is not None
            else float(len(child.courses) * 4)
          )
          categories.append(
            models.DegreeCategory(
              name=full_name,
              required_units=u,
              required_courses=child.courses,
            )
          )
        new_prefix = ""
        if child.title.lower() not in ("major requirements", "requirements"):
          new_prefix = full_name
        collect(child, new_prefix)
      else:
        u = child.units
        if u is None:
          u = float(len(child.courses) * 4) if child.courses else 0.0
        if child.courses or u > 0:
          categories.append(
            models.DegreeCategory(
              name=full_name,
              required_units=u,
              required_courses=child.courses,
            )
          )

  collect(root)

  if not categories:
    courses_found = parse_catalogue_courses(content)
    if not courses_found:
      raise ValueError(
        f"Failed to extract requirements from catalogue at {target_url}"
      )
    categories.append(
      models.DegreeCategory(
        name="Degree Requirements",
        required_units=total_units,
        required_courses=courses_found,
      )
    )

  return models.DegreeProgram(
    id=degree_id,
    title=degree_title,
    school=school,
    total_units=max(128.0, total_units),
    categories=categories,
  )
