"""Runs the audits against the catalog: loads their inputs, calls the engines.

The engine modules are pure; this one is their single composition point,
so the API routes and the advisor's tools audit a student identically.
It reads through store and never writes.
"""

import sqlite3
from collections.abc import Mapping, Sequence

from server.db import models, store
from server.engine import _ge_audit, _program_audit


def listed_codes(program: models.Program) -> list[str]:
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
  ap_credits: Sequence[models.ApCredit],
  ge_counted: Mapping[str, int],
) -> list[models.GeProgress]:
  """Shows how courses, AP exams, and seats counted by hand fill each GE."""
  return _ge_audit.audit(
    store.ge_categories(conn),
    store.ge_of(conn, completed),
    completed,
    store.ap_exams(conn),
    ap_credits,
    ge_counted,
  )


def program(
  conn: sqlite3.Connection,
  term: int,
  audited: models.Program,
  completed: Sequence[str],
  ap_credits: Sequence[models.ApCredit],
  ge_counted: Mapping[str, int],
) -> models.ProgramAudit:
  """Audits a program; prerequisites follow `term`'s listings."""
  exams = store.ap_exams(conn)
  ge = _ge_audit.audit(
    store.ge_categories(conn),
    store.ge_of(conn, completed),
    completed,
    exams,
    ap_credits,
    ge_counted,
  )
  units = store.units_of(conn, completed)
  return _program_audit.audit(
    audited,
    completed,
    units,
    store.requisites_of(conn, term, listed_codes(audited)),
    ge=ge,
    ge_units=_ge_audit.earned_units(ge, units, exams),
    exam_units=sum(e.units for e in _ge_audit.passed(exams, ap_credits)),
  )
