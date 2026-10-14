"""Read-only, term-scoped access to the catalog database.

The only module that queries catalog.db at runtime. Pages of courses load
in batches (one query per child table for the whole page) and are
assembled into API models, so a 100-course search costs about ten queries
rather than one per course. Codes from callers may be spelled any way a
source spells them (MATH-118xg, math 118); they are matched by identity
(codes.identity) and results are keyed the same way. Building the
database belongs to the ingest subpackage; this module never writes.
"""

import collections
import contextlib
import functools
import pathlib
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from server import config
from server.db import models, search
from server.db.ingest.codes import identity


DEFAULT_PATH = config.DB_PATH
_DAYS: Sequence[tuple[int, models.Weekday]] = (
  (1, models.Weekday.MON),
  (2, models.Weekday.TUE),
  (4, models.Weekday.WED),
  (8, models.Weekday.THU),
  (16, models.Weekday.FRI),
  (32, models.Weekday.SAT),
  (64, models.Weekday.SUN),
)
_QUERY_LOCK = threading.RLock()


def _marks(values: Sequence[Any]) -> str:
  return ", ".join("?" * len(values))


@contextlib.contextmanager
def _query(
  conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()
) -> Iterator[sqlite3.Cursor]:
  with _QUERY_LOCK:
    with contextlib.closing(conn.execute(sql, params)) as cur:
      yield cur


def _units(low: float | None, high: float | None) -> models.Units | None:
  if low is None or high is None:
    return None
  return models.Units(min=low, max=high)


class CatalogDb:
  """Opens connections to a built catalog database.

  Attributes:
    path: The database file.
  """

  def __init__(self, path: pathlib.Path = DEFAULT_PATH) -> None:
    self.path = path

  def connect(self) -> sqlite3.Connection:
    """Opens a read-only connection.

    Raises:
      FileNotFoundError: The catalog has not been built yet.
    """
    resolved = self.path.resolve()
    if not resolved.is_file():
      raise FileNotFoundError(
        f"No catalog at {resolved}; build it with `npm run catalog`"
      )
    conn = sqlite3.connect(
      f"{resolved.as_uri()}?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA mmap_size = 134217728;")
    conn.execute("PRAGMA cache_size = -32000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA query_only = ON;")
    return conn


_cached_conn: sqlite3.Connection | None = None
_cached_conn_path: pathlib.Path | None = None


def get_connection(path: pathlib.Path = DEFAULT_PATH) -> sqlite3.Connection:
  """Returns a persistent read-only connection to the catalog database."""
  global _cached_conn, _cached_conn_path
  resolved = path.resolve()
  with _QUERY_LOCK:
    if _cached_conn is None or _cached_conn_path != resolved:
      if _cached_conn is not None:
        _cached_conn.close()
      _cached_conn = CatalogDb(resolved).connect()
      _cached_conn_path = resolved
    return _cached_conn


def close_connection() -> None:
  """Closes the persistent read-only connection if open."""
  global _cached_conn, _cached_conn_path
  with _QUERY_LOCK:
    if _cached_conn is not None:
      _cached_conn.close()
      _cached_conn = None
      _cached_conn_path = None


def terms(conn: sqlite3.Connection) -> list[models.Term]:
  """Lists every known term, newest first."""
  with _query(
    conn,
    """
    SELECT t.code, t.season, t.year, t.status,
           EXISTS (SELECT 1 FROM offering o WHERE o.term_code = t.code)
             AS has_courses
    FROM term t ORDER BY t.code DESC
    """,
  ) as cur:
    return [models.Term(**dict(r)) for r in cur]


def default_term(conn: sqlite3.Connection) -> int | None:
  """Returns the newest term with courses, the one students plan for."""
  with _query(conn, "SELECT MAX(term_code) FROM offering") as cur:
    row = cur.fetchone()
    return row[0] if row else None


def search_courses(
  conn: sqlite3.Connection,
  term: int,
  q: str | None,
  ge: str | None = None,
  min_rating: float | None = None,
  limit: int = 100,
  offset: int = 0,
) -> list[models.Course]:
  """Finds a term's courses by text, GE category, and instructor rating.

  Text matches rank by exact course-code prefix, then BM25 relevance.
  """
  where = ["o.term_code = ?"]
  params: list[Any] = [term]
  order = ["o.course_code"]
  order_params: list[Any] = []
  join = ""
  match = search.parse(q) if q else None
  if match is not None:
    join = (
      "JOIN offering_fts f ON f.term_code = o.term_code"
      " AND f.course_code = o.course_code"
    )
    where.append("offering_fts MATCH ?")
    params.append(match.fts)
    order.insert(0, "bm25(offering_fts, 10.0, 4.0, 6.0, 8.0, 1.0, 0.0)")
    if match.code_prefix is not None:
      order.insert(0, "o.course_code NOT LIKE ?")
      order_params.append(match.code_prefix)
  if ge:
    where.append(
      """EXISTS (SELECT 1 FROM ge_course g
          WHERE g.catalogue_id = (SELECT MAX(id) FROM catalogue)
            AND g.resolved_code = o.course_code AND g.ge_code = ?)"""
    )
    params.append(ge.upper())
  if min_rating:
    where.append(
      """EXISTS (SELECT 1 FROM section s
          JOIN section_instructor si
            ON si.term_code = s.term_code AND si.section_id = s.id
          JOIN rmp_profile r ON r.instructor_key = si.instructor_key
          WHERE s.term_code = o.term_code AND s.course_code = o.course_code
            AND r.rating >= ?)"""
    )
    params.append(min_rating)
  sql = f"""SELECT o.course_code FROM offering o {join}
      WHERE {" AND ".join(where)}
      ORDER BY {", ".join(order)} LIMIT ? OFFSET ?"""
  with _query(conn, sql, [*params, *order_params, limit, offset]) as cur:
    matched_codes = [row[0] for row in cur]
  return courses(conn, term, matched_codes)


def canonical(conn: sqlite3.Connection, codes: Iterable[str]) -> dict[str, str]:
  """Maps each code's identity to the catalog's spelling, for known courses."""
  keys = list(dict.fromkeys(map(identity, codes)))
  if not keys:
    return {}
  with _query(
    conn,
    f"SELECT key, code FROM course WHERE key IN ({_marks(keys)})",
    keys,
  ) as cur:
    return dict(cur.fetchall())


def course(
  conn: sqlite3.Connection, term: int, code: str
) -> models.Course | None:
  """Loads one course in a term, or None if it is not offered then."""
  found = courses(conn, term, [code])
  return found[0] if found else None


def courses(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> list[models.Course]:
  """Loads full courses in `codes` order; codes not offered are skipped.

  Two spellings of one course load it once.
  """
  known = list(canonical(conn, codes).values())
  if not known:
    return []
  with _query(
    conn,
    f"""SELECT o.*, c.key, c.department_code, c.number, c.suffix
        FROM offering o JOIN course c ON c.code = o.course_code
        WHERE o.term_code = ? AND o.course_code IN ({_marks(known)})""",
    [term, *known],
  ) as cur:
    rows = {r["key"]: r for r in cur}
  wanted = dict.fromkeys(map(identity, codes))
  found = [rows[k] for k in wanted if k in rows]
  offered_codes = [r["course_code"] for r in found]
  ge = _ge(conn, offered_codes)
  requisites = _requisites(conn, term, offered_codes)
  restrictions = _restrictions(conn, term, offered_codes)
  sections_by_course = collections.defaultdict(list)
  for s in _sections_where(conn, term, "s.course_code", offered_codes):
    sections_by_course[identity(s.course_code)].append(s)
  return [
    models.Course(
      term=term,
      code=r["course_code"],
      department=r["department_code"],
      number=r["number"],
      suffix=r["suffix"],
      title=r["title"],
      description=r["description"],
      units=models.Units(min=r["units_min"], max=r["units_max"]),
      recommended_prep=r["recommended_prep"],
      duplicate_credit=r["duplicate_credit"],
      course_notes=r["course_notes"],
      term_notes=r["term_notes"],
      is_cross_listed=bool(r["is_cross_listed"]),
      ge=ge.get(r["key"], []),
      requisites=requisites.get(
        r["key"],
        models.Requisites(prerequisite=[], corequisite=[], concurrent=[]),
      ),
      restrictions=restrictions.get(r["key"], []),
      sections=sections_by_course.get(r["key"], []),
    )
    for r in found
  ]


def sections(
  conn: sqlite3.Connection, term: int, ids: Sequence[str]
) -> list[models.Section]:
  """Loads sections by number in one term, in no particular order."""
  return _sections_where(conn, term, "s.id", ids) if ids else []


def offered(
  conn: sqlite3.Connection, term: int, codes: Iterable[str]
) -> set[str]:
  """Identities of the given courses that `term` offers."""
  known = list(canonical(conn, codes).values())
  if not known:
    return set()
  with _query(
    conn,
    f"""SELECT course_code FROM offering
        WHERE term_code = ? AND course_code IN ({_marks(known)})""",
    [term, *known],
  ) as cur:
    return {identity(row[0]) for row in cur}


def requisites_of(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> dict[str, models.Requisites]:
  """Maps identities of courses offered in `term` to their requisites."""
  known = list(canonical(conn, codes).values())
  return _requisites(conn, term, known) if known else {}


def units_of(
  conn: sqlite3.Connection, codes: Sequence[str]
) -> dict[str, models.Units]:
  """Maps identities to units: the latest offering's, else the catalogue's.

  Courses with neither are absent.
  """
  out: dict[str, models.Units] = {}
  known = list(canonical(conn, codes).values())
  if known:
    with _query(
      conn,
      f"""SELECT course_code, units_min, units_max FROM offering
          WHERE course_code IN ({_marks(known)}) ORDER BY term_code DESC""",
      known,
    ) as cur:
      for code, low, high in cur:
        out.setdefault(identity(code), models.Units(min=low, max=high))
    with _query(
      conn,
      f"""SELECT code, units_min, units_max FROM catalogue_course
          WHERE catalogue_id = (SELECT MAX(id) FROM catalogue)
            AND units_min IS NOT NULL AND code IN ({_marks(known)})""",
      known,
    ) as cur:
      for code, low, high in cur:
        out.setdefault(identity(code), models.Units(min=low, max=high))
  return out


def _ge(conn: sqlite3.Connection, codes: Sequence[str]) -> dict[str, list[str]]:
  out: dict[str, list[str]] = collections.defaultdict(list)
  if not codes:
    return out
  with _query(
    conn,
    f"""SELECT resolved_code, ge_code FROM ge_course
        WHERE catalogue_id = (SELECT MAX(id) FROM catalogue)
          AND resolved_code IN ({_marks(codes)})
        ORDER BY ge_code""",
    list(codes),
  ) as cur:
    for row in cur:
      out[identity(row[0])].append(row[1])
  return out


def _requisites(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> dict[str, models.Requisites]:
  groups: dict[tuple[str, str, int], models.RequisiteGroup] = {}
  if not codes:
    return {}
  with _query(
    conn,
    f"""SELECT course_code, kind, position, required_count
        FROM requisite_group
        WHERE term_code = ? AND course_code IN ({_marks(codes)})
        ORDER BY course_code, kind, position""",
    [term, *codes],
  ) as cur:
    for row in cur:
      groups[(identity(row[0]), row[1], row[2])] = models.RequisiteGroup(
        required_count=row[3], options=[]
      )
  with _query(
    conn,
    f"""SELECT course_code, kind, group_position, option_position,
               required_code, resolved_code
        FROM requisite_course
        WHERE term_code = ? AND course_code IN ({_marks(codes)})
        ORDER BY course_code, kind, group_position, option_position,
          position""",
    [term, *codes],
  ) as cur:
    for row in cur:
      options = groups[(identity(row[0]), row[1], row[2])].options
      while len(options) <= row[3]:
        options.append([])
      options[row[3]].append(models.CourseRef(code=row[4], resolved=row[5]))
  out: dict[str, models.Requisites] = {}
  for (code, kind, _), group in groups.items():
    req = out.setdefault(
      code, models.Requisites(prerequisite=[], corequisite=[], concurrent=[])
    )
    getattr(req, kind).append(group)
  return out


def _restrictions(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> dict[str, list[models.Restriction]]:
  out: dict[str, list[models.Restriction]] = collections.defaultdict(list)
  if not codes:
    return out
  with _query(
    conn,
    f"""SELECT course_code, kind, code, description, inclusive
        FROM restriction
        WHERE term_code = ? AND course_code IN ({_marks(codes)})
        ORDER BY course_code, kind, position""",
    [term, *codes],
  ) as cur:
    for row in cur:
      out[identity(row[0])].append(
        models.Restriction(
          kind=row[1], code=row[2], description=row[3], inclusive=bool(row[4])
        )
      )
  return out


def _sections_where(
  conn: sqlite3.Connection, term: int, column: str, values: Sequence[str]
) -> list[models.Section]:
  if not values:
    return []
  if column == "s.id":
    sql = f"""SELECT * FROM section s
        WHERE s.term_code = ? AND s.id IN ({_marks(values)})
        ORDER BY s.course_code, s.id"""
  elif column == "s.course_code":
    sql = f"""SELECT * FROM section s
        WHERE s.term_code = ? AND s.course_code IN ({_marks(values)})
        ORDER BY s.course_code, s.id"""
  else:
    raise ValueError(f"Unsupported column: {column}")
  with _query(conn, sql, [term, *values]) as cur:
    rows = cur.fetchall()
  ids = [r["id"] for r in rows]
  meetings = _meetings(conn, term, ids) if ids else {}
  teaching = _instructors(conn, term, ids) if ids else {}
  return [
    models.Section(
      term=term,
      id=r["id"],
      course_code=r["course_code"],
      type=r["type"],
      link_code=r["link_code"],
      session=r["session_code"],
      name=r["name"],
      units=_units(r["units_min"], r["units_max"]),
      requires_d_clearance=bool(r["requires_d_clearance"]),
      is_cancelled=bool(r["is_cancelled"]),
      registered=r["registered"],
      capacity=r["capacity"],
      waitlisted=r["waitlisted"],
      description=r["description"],
      notes=r["notes"],
      syllabus_url=r["syllabus_url"],
      meetings=meetings.get(r["id"], []),
      instructors=teaching.get(r["id"], []),
    )
    for r in rows
  ]


def _meetings(
  conn: sqlite3.Connection, term: int, ids: Sequence[str]
) -> dict[str, list[models.Meeting]]:
  out: dict[str, list[models.Meeting]] = collections.defaultdict(list)
  if not ids:
    return out
  with _query(
    conn,
    f"""SELECT section_id, days, start_minute, end_minute FROM meeting
        WHERE term_code = ? AND section_id IN ({_marks(ids)})
        ORDER BY section_id, position""",
    [term, *ids],
  ) as cur:
    for row in cur:
      out[row[0]].append(
        models.Meeting(
          days=[day for bit, day in _DAYS if row[1] & bit],
          start_minute=row[2],
          end_minute=row[3],
        )
      )
  return out


def _instructors(
  conn: sqlite3.Connection, term: int, ids: Sequence[str]
) -> dict[str, list[models.Instructor]]:
  out: dict[str, list[models.Instructor]] = collections.defaultdict(list)
  if not ids:
    return out
  with _query(
    conn,
    f"""SELECT si.section_id, i.key, i.first_name, i.last_name,
               r.rmp_id, r.rating, r.difficulty, r.num_ratings,
               r.would_take_again
        FROM section_instructor si
        JOIN instructor i ON i.key = si.instructor_key
        LEFT JOIN rmp_profile r ON r.instructor_key = i.key
        WHERE si.term_code = ? AND si.section_id IN ({_marks(ids)})
        ORDER BY si.section_id, si.position""",
    [term, *ids],
  ) as cur:
    for row in cur:
      rating = (
        None
        if row["rmp_id"] is None
        else models.Rating(
          rmp_id=row["rmp_id"],
          rating=row["rating"],
          difficulty=row["difficulty"],
          num_ratings=row["num_ratings"],
          would_take_again=row["would_take_again"],
        )
      )
      out[row["section_id"]].append(
        models.Instructor(
          key=row["key"],
          name=f"{row['first_name']} {row['last_name']}".strip(),
          rmp=rating,
        )
      )
  return out


def known_courses(
  conn: sqlite3.Connection, codes: Sequence[str]
) -> list[models.KnownCourse]:
  """Looks codes up in any spelling; unknown codes are skipped.

  Results follow `codes` order, once per course. Titles come from the
  latest catalogue, else the latest offering.
  """
  spelled = canonical(conn, codes)
  wanted = [
    spelled[k] for k in dict.fromkeys(map(identity, codes)) if k in spelled
  ]
  if not wanted:
    return []
  with _query(
    conn,
    f"""SELECT c.code, COALESCE(
          (SELECT k.title FROM catalogue_course k
           WHERE k.code = c.code
             AND k.catalogue_id = (SELECT MAX(id) FROM catalogue)),
          (SELECT o.title FROM offering o WHERE o.course_code = c.code
           ORDER BY o.term_code DESC LIMIT 1))
        FROM course c WHERE c.code IN ({_marks(wanted)})""",
    wanted,
  ) as cur:
    titles = dict(cur.fetchall())
  return [
    models.KnownCourse(code=code, title=titles[code])
    for code in wanted
    if titles.get(code)
  ]


@functools.lru_cache(maxsize=256)
def _cached_ge_categories(
  conn: sqlite3.Connection,
) -> tuple[models.GeCategory, ...]:
  with _query(
    conn,
    "SELECT code, name, area, required_count FROM ge_category ORDER BY code",
  ) as cur:
    return tuple(models.GeCategory(**dict(r)) for r in cur)


def ge_categories(conn: sqlite3.Connection) -> list[models.GeCategory]:
  """Lists GE categories in code order."""
  return list(_cached_ge_categories(conn))


def ge_of(
  conn: sqlite3.Connection, codes: Iterable[str]
) -> dict[str, list[str]]:
  """Maps identities of courses to the GE categories they count for."""
  known = list(canonical(conn, codes).values())
  return _ge(conn, known) if known else {}


@functools.lru_cache(maxsize=256)
def _cached_programs(
  conn: sqlite3.Connection, kind: str | None = None
) -> tuple[models.ProgramSummary, ...]:
  where = ["catalogue_id = (SELECT MAX(id) FROM catalogue)"]
  params: list[Any] = []
  if kind:
    where.append("kind = ?")
    params.append(kind)
  with _query(
    conn,
    f"""SELECT id, title, name, emphasis, kind, degree_type, school,
               total_units, total_units_stated
        FROM program WHERE {" AND ".join(where)} ORDER BY title""",
    params,
  ) as cur:
    return tuple(models.ProgramSummary(**dict(r)) for r in cur)


def programs(
  conn: sqlite3.Connection, kind: str | None = None
) -> list[models.ProgramSummary]:
  """Lists the latest catalogue's programs, optionally of one kind."""
  return list(_cached_programs(conn, kind))


@functools.lru_cache(maxsize=256)
def program(conn: sqlite3.Connection, program_id: str) -> models.Program | None:
  """Loads a program with its requirement tree, or None if unknown."""
  with _query(
    conn,
    """SELECT p.*, c.name AS catalogue FROM program p
       JOIN catalogue c ON c.id = p.catalogue_id WHERE p.id = ?""",
    [program_id],
  ) as cur:
    head = cur.fetchone()
  if head is None:
    return None
  slots: dict[int, dict[int, list[models.RequirementChoice]]] = (
    collections.defaultdict(lambda: collections.defaultdict(list))
  )
  with _query(
    conn,
    """SELECT c.requirement_position, c.slot, c.listed_code, c.resolved_code,
              c.units_min, c.units_max,
              (SELECT o.title FROM offering o
               WHERE o.course_code = c.resolved_code
               ORDER BY o.term_code DESC LIMIT 1) AS title
       FROM program_requirement_choice c WHERE c.program_id = ?
       ORDER BY c.requirement_position, c.slot, c.position""",
    [program_id],
  ) as cur:
    for row in cur:
      slots[row[0]][row[1]].append(
        models.RequirementChoice(
          course=models.CourseRef(code=row[2], resolved=row[3]),
          title=row[6],
          units=_units(row[4], row[5]),
        )
      )
  with _query(
    conn,
    """SELECT * FROM program_requirement WHERE program_id = ?
       ORDER BY position""",
    [program_id],
  ) as cur:
    requirements = [
      models.Requirement(
        position=r["position"],
        parent=r["parent_position"],
        title=r["title"],
        units=_units(r["units_min"], r["units_max"]),
        notes=r["notes"],
        is_general_education=bool(r["is_general_education"]),
        slots=[choices for _, choices in sorted(slots[r["position"]].items())],
      )
      for r in cur
    ]
  return models.Program(
    **_summary(head),
    catalogue=head["catalogue"],
    description=head["description"],
    requirements=requirements,
  )


def _summary(row: Mapping[str, Any]) -> dict[str, Any]:
  fields = models.ProgramSummary.model_fields
  return {name: row[name] for name in fields}


@functools.lru_cache(maxsize=256)
def _cached_ap_exams(
  conn: sqlite3.Connection,
) -> tuple[models.ApExam, ...]:
  ge: dict[str, list[str]] = collections.defaultdict(list)
  with _query(
    conn, "SELECT exam_id, ge_code FROM ap_exam_ge ORDER BY ge_code"
  ) as cur:
    for exam_id, code in cur:
      ge[exam_id].append(code)
  waives: dict[str, list[models.CourseRef]] = collections.defaultdict(list)
  with _query(
    conn, "SELECT exam_id, waived_code, resolved_code FROM ap_exam_waiver"
  ) as cur:
    for exam_id, code, resolved in cur:
      waives[exam_id].append(models.CourseRef(code=code, resolved=resolved))
  with _query(conn, "SELECT * FROM ap_exam ORDER BY name") as cur:
    return tuple(
      models.ApExam(
        id=r["id"],
        name=r["name"],
        min_score=r["min_score"],
        units=r["units"],
        ge=ge[r["id"]],
        waives=waives[r["id"]],
      )
      for r in cur
    )


def ap_exams(conn: sqlite3.Connection) -> list[models.ApExam]:
  """Lists AP exams with the GE categories and courses they cover."""
  return list(_cached_ap_exams(conn))


def clear_catalog_caches() -> None:
  """Clears all in-memory LRU query caches."""
  _cached_ge_categories.cache_clear()
  _cached_programs.cache_clear()
  program.cache_clear()
  _cached_ap_exams.cache_clear()
