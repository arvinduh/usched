"""The student brief: the facts the advisor answers from, computed up front.

A small model asked "what can I take?" invents plausible courses unless
the real answer is already in front of it. Each message therefore carries
a brief built from the catalog in milliseconds: degree progress, courses
the student can take next (offered this term, prerequisites met), open GE
categories, and their week with conflicts and missing sections. Every
course the brief names counts as grounded for the reply check.
"""

import dataclasses
import sqlite3
from collections.abc import Sequence

from server.src.agent import tools
from server.src.catalog import codes
from server.src.data import catalog_db
from server.src.data import catalog_models as m
from server.src.engine import audits, schedule


_NEXT = 10  # Courses suggested as next steps.
_LOCKED = 6  # Locked courses named with their blockers.


@dataclasses.dataclass(frozen=True)
class Student:
  """What the client says about the student asking."""

  term: int
  program_id: str | None
  section_ids: Sequence[str]
  shortlisted: Sequence[str]
  completed: Sequence[str]
  ap_credits: Sequence[m.ApCredit]


@dataclasses.dataclass(frozen=True)
class Brief:
  """The brief and what it established.

  Attributes:
    text: Prompt context, one fact per line.
    grounded: Identities of every course the text names.
    next_codes: Program courses the student can take next, best first.
  """

  text: str
  grounded: frozenset[str]
  next_codes: list[str]


def _term_name(conn: sqlite3.Connection, term: int) -> str:
  for t in catalog_db.terms(conn):
    if t.code == term:
      return f"{t.season} {t.year}"
  return str(term)


def _listed(codes_: Sequence[str]) -> str:
  return ", ".join(codes_) or "none"


def _program_lines(
  conn: sqlite3.Connection, student: Student, planned: set[str]
) -> tuple[list[str], list[str]]:
  """Progress, next courses, and locked courses; also the next codes."""
  program = (
    catalog_db.program(conn, student.program_id) if student.program_id else None
  )
  if program is None:
    return ["Program: not chosen"], []
  audit = audits.program(
    conn, student.term, program, student.completed, student.ap_credits
  )
  total = f"/{program.total_units:g}" if program.total_units else ""
  lines = [f"Program: {program.title}, {audit.units:g}{total} units done"]
  progress = {p.position: p for p in audit.requirements}
  unmet = [
    f"{r.title} ({progress[r.position].units:g}/{r.units.min:g} units)"
    if r.units
    else r.title
    for r in program.requirements
    if r.parent is None
    and progress[r.position].status
    in (m.RequirementStatus.TODO, m.RequirementStatus.PARTIAL)
  ]
  lines.append(f"Unmet requirements: {_listed(unmet)}")

  titles = {
    c.course.resolved or c.course.code: c.title
    for r in program.requirements
    for slot in r.slots
    for c in slot
  }
  listed = audits.listed_codes(program)
  offered = catalog_db.offered(conn, student.term, listed)
  done = {codes.identity(c) for c in student.completed}
  locked = {codes.identity(c) for c in audit.locked}
  ready = [
    code
    for code in dict.fromkeys(listed)
    if codes.identity(code) in offered
    and codes.identity(code) not in done | locked | planned
  ][:_NEXT]
  lines.append(
    "Can take next (offered this term, prerequisites met): "
    + _listed([f"{c} {titles.get(c) or ''}".strip() for c in ready])
  )
  blocked = [
    f"{code} (needs {' or '.join(needs)})"
    for code, needs in list(audit.locked.items())[:_LOCKED]
  ]
  lines.append(f"Locked by prerequisites: {_listed(blocked)}")
  return lines, ready


def _week_lines(
  conn: sqlite3.Connection, student: Student
) -> tuple[list[str], set[str]]:
  """The active schedule, its conflicts, and missing sections."""
  sections = catalog_db.sections(conn, student.term, list(student.section_ids))
  if not sections:
    return ["This week: nothing scheduled"], set()
  lines = ["This week:"]
  lines += [
    f"- {s.course_code} {s.type} {s.id}: {tools.when(s)}, {tools.who(s)}"
    for s in sections
  ]
  clashes = [
    f"{a.course_code} {a.id} with {b.course_code} {b.id}"
    for i, a in enumerate(sections)
    for b in sections[i + 1 :]
    if schedule.overlaps(a, b)
  ]
  if clashes:
    lines.append(f"Conflicts: {'; '.join(clashes)}")
  planned = list(dict.fromkeys(s.course_code for s in sections))
  for course in catalog_db.courses(conn, student.term, planned):
    chosen = [s for s in sections if s.course_code == course.code]
    if missing := schedule.missing_types(course, chosen):
      lines.append(f"{course.code} still needs a {' and a '.join(missing)}")
  return lines, {codes.identity(c) for c in planned}


def build(conn: sqlite3.Connection, student: Student) -> Brief:
  """Builds the brief for one message."""
  week, planned = _week_lines(conn, student)
  program, ready = _program_lines(conn, student, planned)
  ge = audits.general_education(conn, student.completed, student.ap_credits)
  open_ge = [
    f"{p.code} {p.name} ({len(p.courses) + len(p.exams)} of {p.required_count})"
    for p in ge
    if len(p.courses) + len(p.exams) < p.required_count
  ]
  lines = [
    "[Student brief]",
    f"Planning: {_term_name(conn, student.term)}",
    *program,
    f"Open GE categories: {_listed(open_ge)}",
    f"Completed: {_listed(list(student.completed))}",
    *week,
    f"Shortlisted: {_listed(list(student.shortlisted))}",
  ]
  text = "\n".join(lines)
  return Brief(text, frozenset(codes.mentions(text)), ready)
