"""Declarative SQLite persistence and unified query service for usched.

This module provides high-performance relational access, SQLite FTS5 search,
and single-query JSON aggregations for courses, sections, instructors, and
degree roadmaps, adhering to strict YAGNI with zero N+1 overhead.
"""

import json
import os
import pathlib
import sqlite3
from collections.abc import Sequence
from typing import Any

from absl import logging

from server.src.data import models, search


DEFAULT_DB_PATH = (
  pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "usched.db"
)

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent / "schema.sql"

_COURSE_AGGREGATE_SELECT = """
SELECT
  c.id, c.department, c.number, c.title, c.description, c.units,
  c.prerequisites_raw, c.prerequisites_json, c.corequisites_raw,
  c.ge_category,
  COALESCE(
    (
      SELECT json_group_array(g.ge_category)
      FROM course_ge_categories g
      WHERE g.course_id = c.id
    ),
    '[]'
  ) AS ge_categories_json,
  COALESCE(
    (
      SELECT json_group_array(
        json_object(
          'id', s.id,
          'course_id', s.course_id,
          'section_type', s.section_type,
          'term', s.term,
          'days', s.days,
          'start_time', s.start_time,
          'end_time', s.end_time,
          'start_minute', s.start_minute,
          'end_minute', s.end_minute,
          'location', s.location,
          'enrolled', s.enrolled,
          'capacity', s.capacity,
          'waitlist', s.waitlist,
          'instructor', CASE WHEN i.id IS NOT NULL THEN json_object(
            'id', i.id,
            'name', i.name,
            'department', i.department,
            'rmp_id', CASE
              WHEN i.rmp_id = 'NOT_FOUND' THEN NULL
              ELSE i.rmp_id
            END,
            'rmp_rating', i.rmp_rating,
            'rmp_difficulty', i.rmp_difficulty,
            'rmp_num_ratings', i.rmp_num_ratings,
            'rmp_take_again_percent', i.rmp_take_again_percent
          ) ELSE NULL END
        )
      )
      FROM sections s
      LEFT JOIN instructors i ON s.instructor_id = i.id
      WHERE s.course_id = c.id
    ),
    '[]'
  ) AS sections_json
FROM courses c
"""


def _parse_course_row(row: sqlite3.Row) -> models.Course:
  """Builds a Course model from a SQL row containing JSON sections."""
  sec_list_raw: list[dict[str, Any]] = json.loads(row["sections_json"])
  sections: list[models.Section] = []
  for s in sec_list_raw:
    days_val = s.get("days", "")
    if isinstance(days_val, str):
      days_list = [d.strip() for d in days_val.split(",") if d.strip()]
    else:
      days_list = list(days_val or [])

    inst_data = s.get("instructor")
    inst_obj = models.Instructor(**inst_data) if inst_data else None

    sections.append(
      models.Section(
        id=s["id"],
        course_id=s["course_id"],
        section_type=s["section_type"],
        term=s["term"],
        days=days_list,
        start_time=s.get("start_time", "00:00"),
        end_time=s.get("end_time", "00:00"),
        start_minute=int(s.get("start_minute", 0)),
        end_minute=int(s.get("end_minute", 0)),
        location=s.get("location", ""),
        instructor=inst_obj,
        enrolled=int(s.get("enrolled", 0)),
        capacity=int(s.get("capacity", 0)),
        waitlist=int(s.get("waitlist", 0)),
      )
    )

  try:
    prereqs_raw = json.loads(row["prerequisites_json"])
    if isinstance(prereqs_raw, list):
      prereqs_val = [
        [p] if isinstance(p, str) else list(p) for p in prereqs_raw
      ]
    else:
      prereqs_val = []
  except (TypeError, json.JSONDecodeError):
    prereqs_val = []

  try:
    ge_cats_raw = json.loads(row["ge_categories_json"])
    ge_categories = (
      [str(x) for x in ge_cats_raw] if isinstance(ge_cats_raw, list) else []
    )
  except (TypeError, json.JSONDecodeError, KeyError, IndexError):
    ge_categories = []

  return models.Course(
    id=row["id"],
    department=row["department"],
    number=row["number"],
    title=row["title"],
    description=row["description"] or "",
    units=float(row["units"] or 4.0),
    prerequisites_raw=row["prerequisites_raw"] or "",
    prerequisites_json=prereqs_val,
    corequisites_raw=row["corequisites_raw"] or "",
    ge_category=row["ge_category"],
    ge_categories=ge_categories,
    sections=sections,
  )


class Database:
  """Unified SQLite storage service managing connection and queries."""

  def __init__(self, db_path: pathlib.Path | str | None = None) -> None:
    if db_path is not None:
      self.db_path = pathlib.Path(db_path)
    else:
      env_path = os.getenv("USCHED_DB_PATH")
      self.db_path = pathlib.Path(env_path) if env_path else DEFAULT_DB_PATH

  def connect(self) -> sqlite3.Connection:
    """Creates a configured connection with foreign keys and Row factory."""
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(self.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

  def init(self) -> None:
    """Executes declarative DDL schema and ensures virtual tables."""
    conn = self.connect()
    try:
      with conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
      logging.info("Database schema initialized at %s", self.db_path)
    finally:
      conn.close()

  def get_courses(
    self,
    conn: sqlite3.Connection,
    q: str | None = None,
    department: str | None = None,
    ge_category: str | None = None,
    min_rmp: float | None = None,
    limit: int = 60,
    offset: int = 0,
  ) -> list[models.Course]:
    """Retrieves courses using SQL-level filters and FTS5 search.

    With a query, results rank by relevance: an exact course-code prefix
    first, then BM25 weighting code and title matches over descriptions.
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    join_clause = ""
    order_terms = ["c.department", "c.number"]
    order_params: list[Any] = []

    match = search.parse(q) if q else None
    if match is not None:
      join_clause = "JOIN courses_fts fts ON fts.rowid = c.rowid"
      where_clauses.append("courses_fts MATCH ?")
      params.append(match.fts)
      # Column weights follow courses_fts: id, department, number, title,
      # description.
      order_terms.insert(0, "bm25(courses_fts, 10.0, 4.0, 6.0, 8.0, 1.0)")
      if match.code_prefix is not None:
        order_terms.insert(0, "c.id NOT LIKE ?")
        order_params.append(match.code_prefix)

    if department:
      where_clauses.append("c.department = ?")
      params.append(department.upper().strip())

    if ge_category:
      clean_ge = ge_category.strip().upper()
      where_clauses.append(
        """(
          c.ge_category = ?
          OR EXISTS (
            SELECT 1 FROM course_ge_categories cg
            WHERE cg.course_id = c.id AND cg.ge_category = ?
          )
        )"""
      )
      params.extend([clean_ge, clean_ge])

    if min_rmp is not None and min_rmp > 0:
      where_clauses.append(
        """(
          NOT EXISTS (SELECT 1 FROM sections s WHERE s.course_id = c.id)
          OR EXISTS (
            SELECT 1 FROM sections s
            JOIN instructors i ON s.instructor_id = i.id
            WHERE s.course_id = c.id AND i.rmp_rating >= ?
          )
        )"""
      )
      params.append(min_rmp)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"""
      {_COURSE_AGGREGATE_SELECT}
      {join_clause}
      {where_sql}
      ORDER BY {", ".join(order_terms)}
      LIMIT ? OFFSET ?
    """
    params.extend([*order_params, limit, offset])

    cursor = conn.execute(query, params)
    return [_parse_course_row(row) for row in cursor.fetchall()]

  def get_course(
    self, conn: sqlite3.Connection, course_id: str
  ) -> models.Course | None:
    """Retrieves full course detail with all sections and instructors."""
    query = f"{_COURSE_AGGREGATE_SELECT} WHERE c.id = ?"
    cursor = conn.execute(query, (course_id.upper().strip(),))
    row = cursor.fetchone()
    if not row:
      return None
    return _parse_course_row(row)

  def get_departments(self, conn: sqlite3.Connection) -> list[str]:
    """Retrieves sorted unique academic department codes."""
    cursor = conn.execute(
      "SELECT DISTINCT department FROM courses ORDER BY department"
    )
    return [str(row[0]) for row in cursor.fetchall()]

  def get_ge_categories(self, conn: sqlite3.Connection) -> list[str]:
    """Retrieves canonical General Education categories present in catalog."""
    cursor = conn.execute(
      """
      SELECT DISTINCT ge_category FROM course_ge_categories
      WHERE ge_category IS NOT NULL AND ge_category != ''
      ORDER BY ge_category
      """
    )
    cats = [str(row[0]) for row in cursor.fetchall() if row[0]]
    if cats:
      return cats
    return [
      "GE-A",
      "GE-B",
      "GE-C",
      "GE-D",
      "GE-E",
      "GE-F",
      "GE-G",
      "GE-H",
    ]

  def get_sections(
    self, conn: sqlite3.Connection, section_ids: Sequence[str]
  ) -> list[models.Section]:
    """Retrieves sections with enriched instructors in a single query."""
    if not section_ids:
      return []
    placeholders = ",".join("?" for _ in section_ids)
    sql = f"""
      SELECT
        s.id, s.course_id, s.section_type, s.term, s.days, s.start_time,
        s.end_time, s.start_minute, s.end_minute, s.location, s.enrolled,
        s.capacity, s.waitlist,
        i.id AS inst_id, i.name AS inst_name, i.department AS inst_dept,
        i.rmp_id, i.rmp_rating, i.rmp_difficulty, i.rmp_num_ratings,
        i.rmp_take_again_percent
      FROM sections s
      LEFT JOIN instructors i ON s.instructor_id = i.id
      WHERE s.id IN ({placeholders})
    """
    cursor = conn.execute(sql, list(section_ids))
    sections: list[models.Section] = []
    for r in cursor.fetchall():
      days_val = r["days"]
      days_list = [d.strip() for d in days_val.split(",") if d.strip()]
      inst_obj = None
      if r["inst_id"]:
        inst_obj = models.Instructor(
          id=r["inst_id"],
          name=r["inst_name"],
          department=r["inst_dept"] or "",
          rmp_id=r["rmp_id"]
          if r["rmp_id"] and r["rmp_id"] != "NOT_FOUND"
          else None,
          rmp_rating=r["rmp_rating"],
          rmp_difficulty=r["rmp_difficulty"],
          rmp_num_ratings=int(r["rmp_num_ratings"] or 0),
          rmp_take_again_percent=r["rmp_take_again_percent"],
        )
      sections.append(
        models.Section(
          id=r["id"],
          course_id=r["course_id"],
          section_type=r["section_type"],
          term=r["term"],
          days=days_list,
          start_time=r["start_time"],
          end_time=r["end_time"],
          start_minute=int(r["start_minute"]),
          end_minute=int(r["end_minute"]),
          location=r["location"] or "",
          instructor=inst_obj,
          enrolled=int(r["enrolled"]),
          capacity=int(r["capacity"]),
          waitlist=int(r["waitlist"]),
        )
      )
    return sections

  def get_degree(
    self, conn: sqlite3.Connection, degree_id: str
  ) -> models.DegreeProgram | None:
    """Retrieves degree program specification by ID."""
    sql = """
      SELECT id, title, school, total_units, rules_json
      FROM degrees WHERE id = ?
    """
    cursor = conn.execute(sql, (degree_id.lower().strip(),))
    row = cursor.fetchone()
    if not row:
      return None
    cats_data = json.loads(row["rules_json"])
    categories = [models.DegreeCategory(**c) for c in cats_data]
    return models.DegreeProgram(
      id=row["id"],
      title=row["title"],
      school=row["school"],
      total_units=float(row["total_units"]),
      categories=categories,
    )

  def get_all_degrees(
    self, conn: sqlite3.Connection
  ) -> list[models.DegreeProgram]:
    """Retrieves all registered degree roadmaps."""
    sql = """
      SELECT id, title, school, total_units, rules_json
      FROM degrees ORDER BY title
    """
    cursor = conn.execute(sql)
    degrees: list[models.DegreeProgram] = []
    for row in cursor.fetchall():
      cats_data = json.loads(row["rules_json"])
      categories = [models.DegreeCategory(**c) for c in cats_data]
      degrees.append(
        models.DegreeProgram(
          id=row["id"],
          title=row["title"],
          school=row["school"],
          total_units=float(row["total_units"]),
          categories=categories,
        )
      )
    return degrees

  def upsert_courses(
    self, conn: sqlite3.Connection, courses: Sequence[models.Course]
  ) -> None:
    """Atomic batch upsert for courses."""
    sql = """
      INSERT INTO courses (
        id, department, number, title, description, units,
        prerequisites_raw, prerequisites_json, corequisites_raw,
        ge_category
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        description = excluded.description,
        units = excluded.units,
        prerequisites_raw = excluded.prerequisites_raw,
        prerequisites_json = excluded.prerequisites_json,
        corequisites_raw = excluded.corequisites_raw,
        ge_category = excluded.ge_category
    """
    params = [
      (
        c.id,
        c.department,
        c.number,
        c.title,
        c.description,
        c.units,
        c.prerequisites_raw,
        json.dumps(c.prerequisites_json),
        c.corequisites_raw,
        c.ge_category,
      )
      for c in courses
    ]
    with conn:
      conn.executemany(sql, params)

  def upsert_instructors(
    self, conn: sqlite3.Connection, instructors: Sequence[models.Instructor]
  ) -> None:
    """Atomic batch upsert for faculty records."""
    sql = """
      INSERT INTO instructors (
        id, name, department, rmp_id, rmp_rating, rmp_difficulty,
        rmp_num_ratings, rmp_take_again_percent
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        name = excluded.name,
        department = CASE
          WHEN excluded.department != '' THEN excluded.department
          ELSE instructors.department
        END,
        rmp_id = COALESCE(excluded.rmp_id, instructors.rmp_id),
        rmp_rating = COALESCE(
          excluded.rmp_rating, instructors.rmp_rating
        ),
        rmp_difficulty = COALESCE(
          excluded.rmp_difficulty, instructors.rmp_difficulty
        ),
        rmp_num_ratings = CASE
          WHEN excluded.rmp_num_ratings > 0 THEN excluded.rmp_num_ratings
          ELSE instructors.rmp_num_ratings
        END,
        rmp_take_again_percent = COALESCE(
          excluded.rmp_take_again_percent,
          instructors.rmp_take_again_percent
        )
    """
    params = [
      (
        i.id,
        i.name,
        i.department,
        i.rmp_id,
        i.rmp_rating,
        i.rmp_difficulty,
        i.rmp_num_ratings,
        i.rmp_take_again_percent,
      )
      for i in instructors
    ]
    with conn:
      conn.executemany(sql, params)

  def sync_term_sections(
    self,
    conn: sqlite3.Connection,
    term: str,
    sections: Sequence[models.Section],
    department_filter: Sequence[str] | None = None,
  ) -> None:
    """Atomically reconciles sections for a specific academic semester."""
    if department_filter:
      placeholders = ",".join("?" for _ in department_filter)
      delete_sql = f"""
        DELETE FROM sections
        WHERE term = ?
          AND course_id IN (
            SELECT id FROM courses WHERE department IN ({placeholders})
          )
      """
      delete_params: list[Any] = [
        term,
        *[d.upper().strip() for d in department_filter],
      ]
    else:
      delete_sql = "DELETE FROM sections WHERE term = ?"
      delete_params = [term]

    insert_sql = """
      INSERT INTO sections (
        id, course_id, section_type, term, days, start_time, end_time,
        start_minute, end_minute, location, instructor_id, enrolled,
        capacity, waitlist
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        course_id = excluded.course_id,
        section_type = excluded.section_type,
        days = excluded.days,
        start_time = excluded.start_time,
        end_time = excluded.end_time,
        start_minute = excluded.start_minute,
        end_minute = excluded.end_minute,
        location = excluded.location,
        instructor_id = excluded.instructor_id,
        enrolled = excluded.enrolled,
        capacity = excluded.capacity,
        waitlist = excluded.waitlist
    """
    params = [
      (
        s.id,
        s.course_id,
        s.section_type,
        s.term,
        ",".join(s.days),
        s.start_time,
        s.end_time,
        s.start_minute,
        s.end_minute,
        s.location,
        s.instructor.id if (s.instructor and s.instructor.id.strip()) else None,
        s.enrolled,
        s.capacity,
        s.waitlist,
      )
      for s in sections
    ]
    with conn:
      conn.execute(delete_sql, delete_params)
      conn.executemany(insert_sql, params)

  def upsert_degrees(
    self, conn: sqlite3.Connection, degrees: Sequence[models.DegreeProgram]
  ) -> None:
    """Atomic batch upsert for degree curriculum specifications."""
    sql = """
      INSERT INTO degrees (id, title, school, total_units, rules_json)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        school = excluded.school,
        total_units = excluded.total_units,
        rules_json = excluded.rules_json
    """
    params = [
      (
        d.id,
        d.title,
        d.school,
        d.total_units,
        json.dumps([c.model_dump() for c in d.categories]),
      )
      for d in degrees
    ]
    with conn:
      conn.executemany(sql, params)

  def get_unenriched_instructors(
    self, conn: sqlite3.Connection, limit: int | None = None
  ) -> list[models.Instructor]:
    """Retrieves instructors that do not yet have RateMyProfessors data."""
    sql = (
      "SELECT id, name, department FROM instructors "
      "WHERE rmp_rating IS NULL AND (rmp_id IS NULL OR rmp_id = '')"
    )
    if limit is not None and limit > 0:
      sql += f" LIMIT {int(limit)}"
    cursor = conn.execute(sql)
    return [
      models.Instructor(
        id=str(row["id"]),
        name=str(row["name"]),
        department=str(row["department"]),
      )
      for row in cursor.fetchall()
    ]

  def get_existing_degree_ids(self, conn: sqlite3.Connection) -> set[str]:
    """Retrieves all currently stored degree program identifiers."""
    cursor = conn.execute("SELECT id FROM degrees")
    return {str(row["id"]) for row in cursor.fetchall()}

  def get_course_ge_map(
    self, conn: sqlite3.Connection, course_ids: Sequence[str] | None = None
  ) -> dict[str, list[str]]:
    """Retrieves map of course IDs to their satisfied GE categories."""
    if course_ids is not None:
      if not course_ids:
        return {}
      placeholders = ",".join("?" for _ in course_ids)
      sql = f"""
        SELECT course_id, ge_category FROM course_ge_categories
        WHERE course_id IN ({placeholders})
        ORDER BY course_id, ge_category
      """
      cursor = conn.execute(sql, list(course_ids))
    else:
      sql = """
        SELECT course_id, ge_category FROM course_ge_categories
        ORDER BY course_id, ge_category
      """
      cursor = conn.execute(sql)

    result: dict[str, list[str]] = {}
    for r in cursor.fetchall():
      cid = str(r["course_id"])
      cat = str(r["ge_category"])
      result.setdefault(cid, []).append(cat)
    return result

  def get_ap_definitions(
    self, conn: sqlite3.Connection
  ) -> list[models.ApExamDefinition]:
    """Retrieves all standard AP examination equivalency definitions."""
    sql = """
      SELECT id, name, fulfills_ge_category, waives_courses_json, units
      FROM ap_exam_definitions ORDER BY id
    """
    cursor = conn.execute(sql)
    defs: list[models.ApExamDefinition] = []
    for r in cursor.fetchall():
      try:
        waives = json.loads(r["waives_courses_json"])
        waives_list = (
          [str(c) for c in waives] if isinstance(waives, list) else []
        )
      except (TypeError, json.JSONDecodeError):
        waives_list = []
      defs.append(
        models.ApExamDefinition(
          id=str(r["id"]),
          name=str(r["name"]),
          fulfills_ge_category=str(r["fulfills_ge_category"])
          if r["fulfills_ge_category"]
          else None,
          waives_courses=waives_list,
          units=float(r["units"] or 4.0),
        )
      )
    return defs

  def upsert_ap_exam_definitions(
    self, conn: sqlite3.Connection, defs: Sequence[models.ApExamDefinition]
  ) -> None:
    """Inserts or updates standard AP exam definition records."""
    sql = """
      INSERT INTO ap_exam_definitions (
        id, name, fulfills_ge_category, waives_courses_json, units
      ) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        name = excluded.name,
        fulfills_ge_category = excluded.fulfills_ge_category,
        waives_courses_json = excluded.waives_courses_json,
        units = excluded.units
    """
    params = [
      (
        d.id,
        d.name,
        d.fulfills_ge_category,
        json.dumps(d.waives_courses),
        d.units,
      )
      for d in defs
    ]
    with conn:
      conn.executemany(sql, params)
