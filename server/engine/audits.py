"""Runs the audits against the catalog: loads their inputs, calls the engines.

The engine modules are pure; this one is their single composition point,
so the API routes and the advisor's tools audit a student identically.
It reads through store and never writes.
"""

import re
import sqlite3
from collections.abc import Mapping, Sequence

from server.db import models, store
from server.engine import _ge_audit, _program_audit


# Master's (MS, MBA, LLM) and doctoral (PhD, DPT, MD, JD) degree types.
_GRADUATE = re.compile(r"^(?:M|LLM|D)|D$")


def listed_codes(program: models.Program) -> list[str]:
  """Every course a program's requirement slots name, in catalogue order."""
  return [
    c.course.resolved or c.course.code
    for r in program.requirements
    for slot in r.slots
    for c in slot
  ]


def needs_general_education(program: models.ProgramSummary | None) -> bool:
  """Whether a student in `program` owes USC's GE requirement.

  GE is an undergraduate requirement: master's and doctoral degrees (MS,
  MBA, LLM, PhD, MD, JD, DPT) owe none. No program, a bachelor's, or a
  minor keeps it.
  """
  if program is None or program.kind != "degree":
    return True
  degree = program.degree_type or ""
  return degree.startswith("B") or _GRADUATE.search(degree) is None


left_to_take = _program_audit.left_to_take


def general_education(
  conn: sqlite3.Connection,
  completed: Sequence[str],
  ap_credits: Sequence[models.ApCredit],
  ge_counted: Mapping[str, int],
) -> models.GeAudit:
  """Shows how courses, AP exams, and seats counted by hand fill each GE."""
  exams = store.ap_exams(conn)
  progress = _ge_audit.audit(
    store.ge_categories(conn),
    store.ge_of(conn, completed),
    completed,
    exams,
    ap_credits,
    ge_counted,
  )
  earned = _ge_audit.earned_units(
    progress, store.units_of(conn, completed), exams
  )
  return models.GeAudit(
    categories=progress,
    units=earned,
    required_units=_ge_audit.required_units(progress, earned),
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
  ge = general_education(conn, completed, ap_credits, ge_counted)
  exams = store.ap_exams(conn)
  passed = _ge_audit.passed(exams, ap_credits)
  return _program_audit.audit(
    audited,
    completed,
    store.units_of(conn, completed),
    store.requisites_of(conn, term, listed_codes(audited)),
    ge=ge.categories,
    ge_units=ge.units,
    credit_units=sum(e.units for e in passed)
    + _ge_audit.counted_units(ge.categories),
    waived=[w.resolved or w.code for e in passed for w in e.waives],
  )
