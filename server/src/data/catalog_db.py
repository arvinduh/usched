"""Read-only, term-scoped access to the catalog database.

The only module that queries catalog.db at runtime. Pages of courses load
in batches (one query per child table for the whole page) and are
assembled into API models, so a 100-course search costs about ten queries
rather than one per course. Codes from callers may be spelled any way a
source spells them (MATH-118xg, math 118); they are matched by identity
(codes.identity) and results are keyed the same way. Building the
database belongs to the catalog package; this module never writes.
"""

import collections
import pathlib
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from server.src.catalog import codes as course_codes
from server.src.data import catalog_models as m
from server.src.data import search


DEFAULT_PATH = (
  pathlib.Path(__file__).resolve().parents[2] / "data" / "catalog.db"
)
_DAYS: Sequence[tuple[int, m.Weekday]] = (
  (1, m.Weekday.MON),
  (2, m.Weekday.TUE),
  (4, m.Weekday.WED),
  (8, m.Weekday.THU),
  (16, m.Weekday.FRI),
  (32, m.Weekday.SAT),
  (64, m.Weekday.SUN),
)
_LATEST_CATALOGUE = "(SELECT MAX(id) FROM catalogue)"


def _marks(values: Sequence[Any]) -> str:
  return ", ".join("?" * len(values))


def _units(low: float | None, high: float | None) -> m.Units | None:
  return None if low is None or high is None else m.Units(min=low, max=high)


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
    if not self.path.is_file():
      raise FileNotFoundError(
        f"No catalog at {self.path}; build it with `npm run catalog`"
      )
    conn = sqlite3.connect(
      f"{self.path.as_uri()}?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def terms(conn: sqlite3.Connection) -> list[m.Term]:
  """Lists every known term, newest first."""
  rows = conn.execute(
    """
    SELECT t.code, t.season, t.year, t.status,
           EXISTS (SELECT 1 FROM offering o WHERE o.term_code = t.code)
             AS has_courses
    FROM term t ORDER BY t.code DESC
    """
  )
  return [m.Term(**dict(r)) for r in rows]


def default_term(conn: sqlite3.Connection) -> int | None:
  """Returns the newest term with courses, the one students plan for."""
  row = conn.execute("SELECT MAX(term_code) FROM offering").fetchone()
  return row[0]


def search_courses(
  conn: sqlite3.Connection,
  term: int,
  q: str | None,
  ge: str | None = None,
  min_rating: float | None = None,
  limit: int = 100,
  offset: int = 0,
) -> list[m.Course]:
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
      f"""EXISTS (SELECT 1 FROM ge_course g
          WHERE g.catalogue_id = {_LATEST_CATALOGUE}
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
  codes = [
    row[0]
    for row in conn.execute(
      f"""SELECT o.course_code FROM offering o {join}
          WHERE {" AND ".join(where)}
          ORDER BY {", ".join(order)} LIMIT ? OFFSET ?""",
      [*params, *order_params, limit, offset],
    )
  ]
  return courses(conn, term, codes)


def canonical(conn: sqlite3.Connection, codes: Iterable[str]) -> dict[str, str]:
  """Maps each code's identity to the catalog's spelling, for known courses."""
  keys = list(dict.fromkeys(map(course_codes.identity, codes)))
  if not keys:
    return {}
  return dict(
    conn.execute(
      f"SELECT key, code FROM course WHERE key IN ({_marks(keys)})", keys
    ).fetchall()
  )


def course(conn: sqlite3.Connection, term: int, code: str) -> m.Course | None:
  """Loads one course in a term, or None if it is not offered then."""
  found = courses(conn, term, [code])
  return found[0] if found else None


def courses(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> list[m.Course]:
  """Loads full courses in `codes` order; codes not offered are skipped.

  Two spellings of one course load it once.
  """
  known = list(canonical(conn, codes).values())
  if not known:
    return []
  rows = {
    r["key"]: r
    for r in conn.execute(
      f"""SELECT o.*, c.key, c.department_code, c.number, c.suffix
          FROM offering o JOIN course c ON c.code = o.course_code
          WHERE o.term_code = ? AND o.course_code IN ({_marks(known)})""",
      [term, *known],
    )
  }
  wanted = dict.fromkeys(map(course_codes.identity, codes))
  found = [rows[k] for k in wanted if k in rows]
  offered = [r["course_code"] for r in found]
  ge = _ge(conn, offered)
  requisites = _requisites(conn, term, offered)
  restrictions = _restrictions(conn, term, offered)
  sections_by_course = collections.defaultdict(list)
  for s in _sections_where(conn, term, "s.course_code", offered):
    sections_by_course[course_codes.identity(s.course_code)].append(s)
  return [
    m.Course(
      term=term,
      code=r["course_code"],
      department=r["department_code"],
      number=r["number"],
      suffix=r["suffix"],
      title=r["title"],
      description=r["description"],
      units=m.Units(min=r["units_min"], max=r["units_max"]),
      recommended_prep=r["recommended_prep"],
      duplicate_credit=r["duplicate_credit"],
      course_notes=r["course_notes"],
      term_notes=r["term_notes"],
      is_cross_listed=bool(r["is_cross_listed"]),
      ge=ge.get(r["key"], []),
      requisites=requisites.get(
        r["key"],
        m.Requisites(prerequisite=[], corequisite=[], concurrent=[]),
      ),
      restrictions=restrictions.get(r["key"], []),
      sections=sections_by_course.get(r["key"], []),
    )
    for r in found
  ]


def sections(
  conn: sqlite3.Connection, term: int, ids: Sequence[str]
) -> list[m.Section]:
  """Loads sections by number in one term, in no particular order."""
  return _sections_where(conn, term, "s.id", ids) if ids else []


def offered(
  conn: sqlite3.Connection, term: int, codes: Iterable[str]
) -> set[str]:
  """Identities of the given courses that `term` offers."""
  known = list(canonical(conn, codes).values())
  if not known:
    return set()
  return {
    course_codes.identity(row[0])
    for row in conn.execute(
      f"""SELECT course_code FROM offering
          WHERE term_code = ? AND course_code IN ({_marks(known)})""",
      [term, *known],
    )
  }


def requisites_of(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> dict[str, m.Requisites]:
  """Maps identities of courses offered in `term` to their requisites."""
  known = list(canonical(conn, codes).values())
  return _requisites(conn, term, known) if known else {}


def units_of(
  conn: sqlite3.Connection, codes: Sequence[str]
) -> dict[str, m.Units]:
  """Maps identities to units: the latest offering's, else the catalogue's.

  Courses with neither are absent.
  """
  out: dict[str, m.Units] = {}
  known = list(canonical(conn, codes).values())
  if known:
    for code, low, high in conn.execute(
      f"""SELECT course_code, units_min, units_max FROM offering
          WHERE course_code IN ({_marks(known)}) ORDER BY term_code DESC""",
      known,
    ):
      out.setdefault(course_codes.identity(code), m.Units(min=low, max=high))
    for code, low, high in conn.execute(
      f"""SELECT code, units_min, units_max FROM catalogue_course
          WHERE catalogue_id = {_LATEST_CATALOGUE}
            AND units_min IS NOT NULL AND code IN ({_marks(known)})""",
      known,
    ):
      out.setdefault(course_codes.identity(code), m.Units(min=low, max=high))
  return out


def _ge(conn: sqlite3.Connection, codes: Sequence[str]) -> dict[str, list[str]]:
  out: dict[str, list[str]] = collections.defaultdict(list)
  for row in conn.execute(
    f"""SELECT resolved_code, ge_code FROM ge_course
        WHERE catalogue_id = {_LATEST_CATALOGUE}
          AND resolved_code IN ({_marks(codes)})
        ORDER BY ge_code""",
    list(codes),
  ):
    out[course_codes.identity(row[0])].append(row[1])
  return out


def _requisites(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> dict[str, m.Requisites]:
  groups: dict[tuple[str, str, int], m.RequisiteGroup] = {}
  for row in conn.execute(
    f"""SELECT course_code, kind, position, required_count
        FROM requisite_group
        WHERE term_code = ? AND course_code IN ({_marks(codes)})
        ORDER BY course_code, kind, position""",
    [term, *codes],
  ):
    groups[(course_codes.identity(row[0]), row[1], row[2])] = m.RequisiteGroup(
      required_count=row[3], options=[]
    )
  for row in conn.execute(
    f"""SELECT course_code, kind, group_position, option_position,
               required_code, resolved_code
        FROM requisite_course
        WHERE term_code = ? AND course_code IN ({_marks(codes)})
        ORDER BY course_code, kind, group_position, option_position,
          position""",
    [term, *codes],
  ):
    options = groups[(course_codes.identity(row[0]), row[1], row[2])].options
    while len(options) <= row[3]:
      options.append([])
    options[row[3]].append(m.CourseRef(code=row[4], resolved=row[5]))
  out: dict[str, m.Requisites] = {}
  for (code, kind, _), group in groups.items():
    req = out.setdefault(
      code, m.Requisites(prerequisite=[], corequisite=[], concurrent=[])
    )
    getattr(req, kind).append(group)
  return out


def _restrictions(
  conn: sqlite3.Connection, term: int, codes: Sequence[str]
) -> dict[str, list[m.Restriction]]:
  out: dict[str, list[m.Restriction]] = collections.defaultdict(list)
  for row in conn.execute(
    f"""SELECT course_code, kind, code, description, inclusive
        FROM restriction
        WHERE term_code = ? AND course_code IN ({_marks(codes)})
        ORDER BY course_code, kind, position""",
    [term, *codes],
  ):
    out[course_codes.identity(row[0])].append(
      m.Restriction(
        kind=row[1], code=row[2], description=row[3], inclusive=bool(row[4])
      )
    )
  return out


def _sections_where(
  conn: sqlite3.Connection, term: int, column: str, values: Sequence[str]
) -> list[m.Section]:
  rows = conn.execute(
    f"""SELECT * FROM section s
        WHERE s.term_code = ? AND {column} IN ({_marks(values)})
        ORDER BY s.course_code, s.id""",
    [term, *values],
  ).fetchall()
  ids = [r["id"] for r in rows]
  meetings = _meetings(conn, term, ids) if ids else {}
  teaching = _instructors(conn, term, ids) if ids else {}
  return [
    m.Section(
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
) -> dict[str, list[m.Meeting]]:
  out: dict[str, list[m.Meeting]] = collections.defaultdict(list)
  for row in conn.execute(
    f"""SELECT section_id, days, start_minute, end_minute FROM meeting
        WHERE term_code = ? AND section_id IN ({_marks(ids)})
        ORDER BY section_id, position""",
    [term, *ids],
  ):
    out[row[0]].append(
      m.Meeting(
        days=[day for bit, day in _DAYS if row[1] & bit],
        start_minute=row[2],
        end_minute=row[3],
      )
    )
  return out


def _instructors(
  conn: sqlite3.Connection, term: int, ids: Sequence[str]
) -> dict[str, list[m.Instructor]]:
  out: dict[str, list[m.Instructor]] = collections.defaultdict(list)
  for row in conn.execute(
    f"""SELECT si.section_id, i.key, i.first_name, i.last_name,
               r.rmp_id, r.rating, r.difficulty, r.num_ratings,
               r.would_take_again
        FROM section_instructor si
        JOIN instructor i ON i.key = si.instructor_key
        LEFT JOIN rmp_profile r ON r.instructor_key = i.key
        WHERE si.term_code = ? AND si.section_id IN ({_marks(ids)})
        ORDER BY si.section_id, si.position""",
    [term, *ids],
  ):
    rating = (
      None
      if row["rmp_id"] is None
      else m.Rating(
        rmp_id=row["rmp_id"],
        rating=row["rating"],
        difficulty=row["difficulty"],
        num_ratings=row["num_ratings"],
        would_take_again=row["would_take_again"],
      )
    )
    out[row["section_id"]].append(
      m.Instructor(
        key=row["key"],
        name=f"{row['first_name']} {row['last_name']}".strip(),
        rmp=rating,
      )
    )
  return out


def departments(conn: sqlite3.Connection) -> list[str]:
  """Lists every department code, e.g. CSCI."""
  return [r[0] for r in conn.execute("SELECT code FROM department ORDER BY 1")]


def ge_categories(conn: sqlite3.Connection) -> list[m.GeCategory]:
  """Lists GE categories in code order."""
  return [
    m.GeCategory(**dict(r))
    for r in conn.execute(
      "SELECT code, name, area, required_count FROM ge_category ORDER BY code"
    )
  ]


def ge_of(
  conn: sqlite3.Connection, codes: Iterable[str]
) -> dict[str, list[str]]:
  """Maps identities of courses to the GE categories they count for."""
  known = list(canonical(conn, codes).values())
  return _ge(conn, known) if known else {}


def programs(
  conn: sqlite3.Connection, kind: str | None = None
) -> list[m.ProgramSummary]:
  """Lists the latest catalogue's programs, optionally of one kind."""
  where = f"catalogue_id = {_LATEST_CATALOGUE}"
  params: list[Any] = []
  if kind:
    where += " AND kind = ?"
    params.append(kind)
  return [
    m.ProgramSummary(**dict(r))
    for r in conn.execute(
      f"""SELECT id, title, name, emphasis, kind, degree_type, school,
                 total_units, total_units_stated
          FROM program WHERE {where} ORDER BY title""",
      params,
    )
  ]


def program(conn: sqlite3.Connection, program_id: str) -> m.Program | None:
  """Loads a program with its requirement tree, or None if unknown."""
  head = conn.execute(
    """SELECT p.*, c.name AS catalogue FROM program p
       JOIN catalogue c ON c.id = p.catalogue_id WHERE p.id = ?""",
    [program_id],
  ).fetchone()
  if head is None:
    return None
  slots: dict[int, dict[int, list[m.RequirementChoice]]] = (
    collections.defaultdict(lambda: collections.defaultdict(list))
  )
  for row in conn.execute(
    """SELECT c.requirement_position, c.slot, c.listed_code, c.resolved_code,
              c.units_min, c.units_max,
              (SELECT o.title FROM offering o
               WHERE o.course_code = c.resolved_code
               ORDER BY o.term_code DESC LIMIT 1) AS title
       FROM program_requirement_choice c WHERE c.program_id = ?
       ORDER BY c.requirement_position, c.slot, c.position""",
    [program_id],
  ):
    slots[row[0]][row[1]].append(
      m.RequirementChoice(
        course=m.CourseRef(code=row[2], resolved=row[3]),
        title=row[6],
        units=_units(row[4], row[5]),
      )
    )
  requirements = [
    m.Requirement(
      position=r["position"],
      parent=r["parent_position"],
      title=r["title"],
      units=_units(r["units_min"], r["units_max"]),
      notes=r["notes"],
      is_general_education=bool(r["is_general_education"]),
      slots=[choices for _, choices in sorted(slots[r["position"]].items())],
    )
    for r in conn.execute(
      """SELECT * FROM program_requirement WHERE program_id = ?
         ORDER BY position""",
      [program_id],
    )
  ]
  return m.Program(
    **_summary(head),
    catalogue=head["catalogue"],
    description=head["description"],
    requirements=requirements,
  )


def _summary(row: Mapping[str, Any]) -> dict[str, Any]:
  fields = m.ProgramSummary.model_fields
  return {name: row[name] for name in fields}


def ap_exams(conn: sqlite3.Connection) -> list[m.ApExam]:
  """Lists AP exams with the GE categories and courses they cover."""
  ge: dict[str, list[str]] = collections.defaultdict(list)
  for exam_id, code in conn.execute(
    "SELECT exam_id, ge_code FROM ap_exam_ge ORDER BY ge_code"
  ):
    ge[exam_id].append(code)
  waives: dict[str, list[m.CourseRef]] = collections.defaultdict(list)
  for exam_id, code, resolved in conn.execute(
    "SELECT exam_id, waived_code, resolved_code FROM ap_exam_waiver"
  ):
    waives[exam_id].append(m.CourseRef(code=code, resolved=resolved))
  return [
    m.ApExam(
      id=r["id"],
      name=r["name"],
      min_score=r["min_score"],
      units=r["units"],
      ge=ge[r["id"]],
      waives=waives[r["id"]],
    )
    for r in conn.execute("SELECT * FROM ap_exam ORDER BY name")
  ]
