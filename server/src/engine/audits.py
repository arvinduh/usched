"""Runs the audits against the catalog: loads their inputs, calls the engines.

The engine modules are pure; this one is their single composition point,
so the API routes and the advisor's tools audit a student identically.
It reads through catalog_db and never writes.
"""

import sqlite3
from collections.abc import Mapping, Sequence

from server.src.data import catalog_db
from server.src.data import catalog_models as m
from server.src.engine import ge_audit, program_audit


def listed_codes(program: m.Program) -> list[str]:
  """Every course a program's requirement slots name, in catalogue order."""
  return [
    c.course.resolved or c.course.code
    for r in program.requirements
    for slot in r.slots
    for c in slot
  ]


def general_education(
  conn: sqlite3.Connection,
  completed: Sequence[str],
  ap_credits: Sequence[m.ApCredit],
  ge_counted: Mapping[str, int],
) -> list[m.GeProgress]:
  """Shows how courses, AP exams, and seats counted by hand fill each GE."""
  return ge_audit.audit(
    catalog_db.ge_categories(conn),
    catalog_db.ge_of(conn, completed),
    completed,
    catalog_db.ap_exams(conn),
    ap_credits,
    ge_counted,
  )


def program(
  conn: sqlite3.Connection,
  term: int,
  audited: m.Program,
  completed: Sequence[str],
  ap_credits: Sequence[m.ApCredit],
  ge_counted: Mapping[str, int],
) -> m.ProgramAudit:
  """Audits a program; prerequisites follow `term`'s listings."""
  exams = catalog_db.ap_exams(conn)
  ge = ge_audit.audit(
    catalog_db.ge_categories(conn),
    catalog_db.ge_of(conn, completed),
    completed,
    exams,
    ap_credits,
    ge_counted,
  )
  units = catalog_db.units_of(conn, completed)
  return program_audit.audit(
    audited,
    completed,
    units,
    catalog_db.requisites_of(conn, term, listed_codes(audited)),
    ge=ge,
    ge_units=ge_audit.earned_units(ge, units, exams),
    exam_units=sum(e.units for e in ge_audit.passed(exams, ap_credits)),
  )
