"""Builds the catalog database from scratch out of the raw cache and seeds.

Collects every cached payload through the parsers, deduplicates rows by
primary key, resolves course references against the catalog, and writes a
fresh database to a temporary file that atomically replaces the old one.
Builds are offline and deterministic: the same cache gives the same database.
"""

import collections
import dataclasses
import os
import pathlib
import re
import sqlite3
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from typing import Any

from absl import logging

from server.src.catalog import (
  cache,
  catalogue_site,
  classes_api,
  parse_catalogue,
  parse_classes,
  records,
  rmp,
  seeds,
)


SCHEMA_PATH = pathlib.Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = pathlib.Path(__file__).resolve().parents[2] / "data" / "catalog.db"
_GE_PAGE_TITLE = "General Education"
_BASE_CODE = re.compile(r"^([A-Za-z]+)-(\d+)")


def _code(code: str) -> str:
  return code.lower()


# Primary key of each term-data table, used to drop duplicate rows that the
# same course yields when it appears in more than one listing.
_KEYS: Mapping[str, Callable[[Any], Hashable]] = {
  "school": lambda r: r.code,
  "department": lambda r: _code(r.code),
  "course": lambda r: _code(r.code),
  "offering": lambda r: (r.term_code, _code(r.course_code)),
  "offering_usc_ge": lambda r: (
    r.term_code,
    _code(r.course_code),
    r.usc_ge_code,
  ),
  "requisite_group": lambda r: (
    r.term_code,
    _code(r.course_code),
    r.kind,
    r.position,
  ),
  "requisite_course": lambda r: (
    r.term_code,
    _code(r.course_code),
    r.kind,
    r.group_position,
    r.option_position,
    r.position,
  ),
  "restriction": lambda r: (
    r.term_code,
    _code(r.course_code),
    r.kind,
    r.position,
  ),
  "section": lambda r: (r.term_code, r.id),
  "meeting": lambda r: (r.term_code, r.section_id, r.position),
  "instructor": lambda r: r.key,
  "section_instructor": lambda r: (r.term_code, r.section_id, r.position),
}


def _capitals(row: Any) -> int:
  return sum(ch.isupper() for ch in f"{row.first_name}{row.last_name}")


# How to settle two different rows with one key, beyond listing priority:
# True when the first argument should replace the second.
_BETTER: Mapping[str, Callable[[Any, Any], bool]] = {
  # Some listings name a department by its code alone.
  "department": lambda row, kept: kept.name == kept.code != row.name,
  # "Nieto Manzer" over "Nieto manzer".
  "instructor": lambda row, kept: _capitals(row) > _capitals(kept),
}


class _Table:
  """Rows for one table, unique by primary key.

  A course appears in its home listing (its department's) and in every
  listing it is cross-listed into, and USC's copies sometimes disagree. A
  home row beats a cross-listed one; otherwise the table's `_BETTER` rule
  decides, and failing that the first row seen wins and the disagreement
  is counted as a conflict.

  Attributes:
    duplicates: Rows dropped because an identical row came first.
    settled: Differing rows settled by listing priority or a rule.
    conflicts: Differing rows kept first-come because nothing settled them.
    example: The first unsettled pair, (kept, dropped).
  """

  def __init__(
    self,
    key: Callable[[Any], Hashable],
    better: Callable[[Any, Any], bool] | None = None,
  ) -> None:
    self._key = key
    self._better = better or (lambda _row, _kept: False)
    self._rows: dict[Hashable, tuple[Any, bool]] = {}
    self.duplicates = 0
    self.settled = 0
    self.conflicts = 0
    self.example: tuple[Any, Any] | None = None

  def add(self, rows: Iterable[Any], home: bool = False) -> None:
    for row in rows:
      key = self._key(row)
      if key not in self._rows:
        self._rows[key] = (row, home)
        continue
      kept, kept_home = self._rows[key]
      if kept == row:
        self.duplicates += 1
        self._rows[key] = (kept, kept_home or home)
      elif home != kept_home:
        self.settled += 1
        if home:
          self._rows[key] = (row, home)
      elif self._better(row, kept):
        self.settled += 1
        self._rows[key] = (row, home)
      elif self._better(kept, row):
        self.settled += 1
      else:
        self.conflicts += 1
        self.example = self.example or (kept, row)

  def has(self, key: Hashable) -> bool:
    return key in self._rows

  def rows(self) -> list[Any]:
    return [row for row, _ in self._rows.values()]


@dataclasses.dataclass
class _Collected:
  """Everything parsed from the cache, before insertion."""

  terms: list[records.Term] = dataclasses.field(default_factory=list)
  tables: dict[str, _Table] = dataclasses.field(
    default_factory=lambda: {
      name: _Table(key, _BETTER.get(name)) for name, key in _KEYS.items()
    }
  )
  profiles: list[records.RmpProfile] = dataclasses.field(default_factory=list)
  catalogue: records.Catalogue | None = None
  ge_names: dict[str, str] = dataclasses.field(default_factory=dict)
  ge_courses: list[records.GeCourse] = dataclasses.field(default_factory=list)
  programs: list[parse_catalogue.ProgramPage] = dataclasses.field(
    default_factory=list
  )


def _collect_classes(raw: cache.RawCache, out: _Collected) -> None:
  out.terms = parse_classes.parse_terms(raw.read_json(classes_api.TERMS_KEY))
  for term in sorted(t.code for t in out.terms):
    if not raw.path(classes_api.schools_key(term)).is_file():
      continue
    schools, departments = parse_classes.parse_schools(
      raw.read_json(classes_api.schools_key(term))
    )
    out.tables["school"].add(schools)
    out.tables["department"].add(departments)
    for key in raw.keys(f"classes/{term}/listings", "*.json"):
      school, program = pathlib.PurePosixPath(key).stem.split("-", 1)
      listing = parse_classes.parse_listing(raw.read_json(key), term)
      _add_listing(listing, school, program, out.tables)


def _add_listing(
  listing: parse_classes.Listing,
  school: str,
  program: str,
  tables: dict[str, _Table],
) -> None:
  # A cross-listed course can carry a prefix its listing's school does not
  # own; record that department under the listing's school.
  for course in listing.courses:
    if not tables["department"].has(_code(course.department_code)):
      tables["department"].add(
        [
          records.Department(
            course.department_code, course.department_code, school, None
          )
        ]
      )
  # Rows of courses this listing's program owns come from their home
  # listing; the rest are cross-listed copies.
  home = {
    _code(c.code) for c in listing.courses if c.department_code == program
  }
  section_home = {
    s.id for s in listing.sections if _code(s.course_code) in home
  }

  def split(
    name: str, rows: Sequence[Any], is_home: Callable[[Any], bool]
  ) -> None:
    tables[name].add((r for r in rows if is_home(r)), home=True)
    tables[name].add(r for r in rows if not is_home(r))

  def by_course(row: Any) -> bool:
    return _code(row.course_code) in home

  def by_section(row: Any) -> bool:
    return row.section_id in section_home

  tables["course"].add(listing.courses)
  split("offering", listing.offerings, by_course)
  split("offering_usc_ge", listing.usc_ge_codes, by_course)
  split("requisite_group", listing.requisite_groups, by_course)
  split("requisite_course", listing.requisite_courses, by_course)
  split("restriction", listing.restrictions, by_course)
  split("section", listing.sections, by_course)
  split("meeting", listing.meetings, by_section)
  tables["instructor"].add(listing.instructors)
  split("section_instructor", listing.section_instructors, by_section)


def _collect_rmp(raw: cache.RawCache, out: _Collected) -> None:
  for instructor in out.tables["instructor"].rows():
    key = rmp.search_key(instructor.key)
    if raw.path(key).is_file():
      profile = rmp.parse_profile(instructor, raw.read_json(key))
      if profile is not None:
        out.profiles.append(profile)


def _collect_catalogue(raw: cache.RawCache, out: _Collected) -> None:
  indexes = raw.keys("catalogue", "*/index.html")
  if not indexes:
    logging.warning("No catalogue cached; programs and GE lists skipped")
    return
  index_html = raw.read_text(max(indexes, key=lambda k: int(k.split("/")[1])))
  out.catalogue = parse_catalogue.parse_catalogue(index_html)
  catoid = out.catalogue.id
  links = parse_catalogue.parse_index(index_html)
  ids = parse_catalogue.program_ids(links)
  for link in links:
    key = catalogue_site.program_key(catoid, link.poid)
    if not raw.path(key).is_file():
      continue
    page = raw.read_text(key)
    if link.title == _GE_PAGE_TITLE:
      out.ge_courses = parse_catalogue.parse_ge_lists(page, catoid)
      out.ge_names = parse_catalogue.ge_category_names(page)
    try:
      out.programs.append(
        parse_catalogue.parse_program(page, catoid, link, ids[link.poid])
      )
    except ValueError as e:
      logging.warning("Skipped program %s: %s", link.title, e)


class _Resolver:
  """Maps a course code as some source wrote it to a catalog course.

  Exact codes match case-insensitively. Otherwise a code like CSCI-103
  matches CSCI-103L only when exactly one course has that department and
  number; ambiguous codes (CHEM-105 with 105aLg and 105bL) stay unresolved.
  """

  def __init__(self, courses: Sequence[records.Course]) -> None:
    self._exact = {_code(c.code): c.code for c in courses}
    self._by_number: dict[tuple[str, str], list[str]] = collections.defaultdict(
      list
    )
    for c in courses:
      self._by_number[(_code(c.department_code), c.number)].append(c.code)

  def __call__(self, code: str) -> str | None:
    exact = self._exact.get(_code(code))
    if exact is not None:
      return exact
    match = _BASE_CODE.match(code)
    if match is None:
      return None
    key = (_code(match.group(1)), match.group(2))
    candidates = self._by_number.get(key, [])
    return candidates[0] if len(candidates) == 1 else None


def _insert(
  conn: sqlite3.Connection, table: str, rows: Iterable[Sequence[Any]]
) -> int:
  rows = list(rows)
  if rows:
    marks = ", ".join("?" * len(rows[0]))
    conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
  return len(rows)


def _tuples(rows: Iterable[Any]) -> list[tuple[Any, ...]]:
  return [dataclasses.astuple(r) for r in rows]


def _ge_categories(names: Mapping[str, str]) -> list[records.GeCategory]:
  categories = []
  for rule in seeds.ge_rules():
    name = names.get(rule.code)
    if name is None:
      logging.warning(
        "Catalogue gives no name for %s; using its code", rule.code
      )
    categories.append(
      records.GeCategory(
        rule.code, name or rule.code, rule.area, rule.required_count
      )
    )
  return categories


def _write(conn: sqlite3.Connection, data: _Collected) -> dict[str, int]:
  """Inserts everything in foreign-key order and returns row counts."""
  tables = data.tables
  resolve = _Resolver(tables["course"].rows())
  counts: dict[str, int] = {"term": _insert(conn, "term", _tuples(data.terms))}
  for name in (
    "school",
    "department",
    "course",
    "offering",
    "offering_usc_ge",
    "requisite_group",
  ):
    counts[name] = _insert(conn, name, _tuples(tables[name].rows()))
  counts["requisite_course"] = _insert(
    conn,
    "requisite_course",
    (
      (*dataclasses.astuple(r), resolve(r.required_code))
      for r in tables["requisite_course"].rows()
    ),
  )
  for name in ("restriction", "section", "meeting", "instructor"):
    counts[name] = _insert(conn, name, _tuples(tables[name].rows()))
  counts["section_instructor"] = _insert(
    conn, "section_instructor", _tuples(tables["section_instructor"].rows())
  )
  counts["rmp_profile"] = _insert(conn, "rmp_profile", _tuples(data.profiles))
  counts["ge_category"] = _insert(
    conn, "ge_category", _tuples(_ge_categories(data.ge_names))
  )
  counts.update(_write_catalogue(conn, data, resolve))
  counts.update(_write_ap(conn, resolve))
  _index_search(conn)
  return counts


def _write_catalogue(
  conn: sqlite3.Connection, data: _Collected, resolve: _Resolver
) -> dict[str, int]:
  if data.catalogue is None:
    return {}
  pages = data.programs
  return {
    "catalogue": _insert(conn, "catalogue", _tuples([data.catalogue])),
    "ge_course": _insert(
      conn,
      "ge_course",
      (
        (*dataclasses.astuple(g), resolve(g.listed_code))
        for g in data.ge_courses
      ),
    ),
    "program": _insert(conn, "program", _tuples(p.program for p in pages)),
    "program_requirement": _insert(
      conn,
      "program_requirement",
      _tuples(r for p in pages for r in p.requirements),
    ),
    "program_requirement_choice": _insert(
      conn,
      "program_requirement_choice",
      (
        (*dataclasses.astuple(c), resolve(c.listed_code))
        for p in pages
        for c in p.choices
      ),
    ),
  }


def _write_ap(conn: sqlite3.Connection, resolve: _Resolver) -> dict[str, int]:
  ap = seeds.ap_exams()
  return {
    "ap_exam": _insert(conn, "ap_exam", _tuples(ap.exams)),
    "ap_exam_ge": _insert(conn, "ap_exam_ge", _tuples(ap.ge)),
    "ap_exam_waiver": _insert(
      conn,
      "ap_exam_waiver",
      ((*dataclasses.astuple(w), resolve(w.waived_code)) for w in ap.waivers),
    ),
  }


def _index_search(conn: sqlite3.Connection) -> None:
  conn.execute(
    """
    INSERT INTO offering_fts
      (course_code, department, number, title, description, term_code)
    SELECT o.course_code, c.department_code, c.number || c.suffix,
           o.title, o.description, o.term_code
    FROM offering o JOIN course c ON c.code = o.course_code
    """
  )


def build(
  raw: cache.RawCache, target: pathlib.Path = DEFAULT_DB
) -> dict[str, int]:
  """Rebuilds the database at `target` from the cache; returns row counts.

  Raises:
    FileNotFoundError: The cache has no term list (nothing was fetched).
    sqlite3.IntegrityError: Collected rows violate the schema, e.g. a
      dangling reference; the existing database is left untouched.
  """
  data = _Collected()
  _collect_classes(raw, data)
  _collect_rmp(raw, data)
  _collect_catalogue(raw, data)
  for name, table in data.tables.items():
    if table.duplicates:
      logging.info("Dropped %d duplicate %s rows", table.duplicates, name)
    if table.settled:
      logging.info("Settled %d differing %s rows", table.settled, name)
    if table.conflicts:
      logging.warning(
        "Kept the first of %d conflicting %s rows, e.g. %s over %s",
        table.conflicts,
        name,
        *table.example or ("?", "?"),
      )

  target.parent.mkdir(parents=True, exist_ok=True)
  partial = target.with_name(target.name + ".building")
  partial.unlink(missing_ok=True)
  conn = sqlite3.connect(partial)
  try:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    with conn:
      counts = _write(conn, data)
    dangling = conn.execute("PRAGMA foreign_key_check").fetchall()
    if dangling:
      raise sqlite3.IntegrityError(f"Dangling references: {dangling[:5]}")
    conn.execute("ANALYZE")
  finally:
    conn.close()
  os.replace(partial, target)
  return counts
