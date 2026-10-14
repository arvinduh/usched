"""The student brief: the facts the advisor answers from, computed up front.

A model asked "what can I take?" invents plausible courses unless
the real answer is already in front of it. Each message therefore carries
a brief built from the catalog in milliseconds: degree progress, courses
the student can take next (offered this term, prerequisites met), open GE
categories, their week with conflicts and missing sections, their other
schedules, and what is on their screen (the page, an open course, a
proposal on the week), so "this course" and "option 2" have referents.
Every course the brief names counts as grounded for the reply check.
"""

import dataclasses
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Literal

from server import config
from server.agent import _tools
from server.db import models, store
from server.db.ingest import codes
from server.engine import audits, schedule


_NEXT = 10  # Courses suggested as next steps.
_LOCKED = 6  # Locked courses named with their blockers.


@dataclasses.dataclass(frozen=True)
class Variant:
  """A named schedule: one the student keeps, or a proposal on the week."""

  name: str
  section_ids: Sequence[str]


@dataclasses.dataclass(frozen=True)
class Screen:
  """What the student is looking at as they ask.

  Attributes:
    page: The planner (week and column) or the degree page.
    open_course: The course whose card is open, if any.
    proposal: The advisor's proposal the week projects, not yet kept.
  """

  page: Literal["planner", "degree"] = "planner"
  open_course: str | None = None
  proposal: Variant | None = None


@dataclasses.dataclass(frozen=True)
class Student:
  """What the client says about the student asking."""

  term: int
  program_id: str | None
  section_ids: Sequence[str]
  shortlisted: Sequence[str]
  completed: Sequence[str]
  ap_credits: Sequence[models.ApCredit]
  ge_counted: Mapping[str, int] = dataclasses.field(default_factory=dict)
  variants: Sequence[Variant] = ()
  screen: Screen = Screen()


@dataclasses.dataclass(frozen=True)
class Brief:
  """The brief and what it established.

  Attributes:
    text: Prompt context, one fact per line.
    grounded: Identities of every course the text names.
  """

  text: str
  grounded: frozenset[str]


def _term_name(conn: sqlite3.Connection, term: int) -> str:
  for t in store.terms(conn):
    if t.code == term:
      return f"{t.season} {t.year}"
  return str(term)


def _listed(codes_: Sequence[str]) -> str:
  return ", ".join(codes_) or "none"


def _program_lines(
  conn: sqlite3.Connection, student: Student, planned: set[str]
) -> list[str]:
  """Progress, next courses, and locked courses."""
  program = (
    store.program(conn, student.program_id) if student.program_id else None
  )
  if program is None:
    return ["Program: not chosen"]
  audit = audits.program(
    conn,
    student.term,
    program,
    student.completed,
    student.ap_credits,
    student.ge_counted,
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
    in (models.RequirementStatus.TODO, models.RequirementStatus.PARTIAL)
  ]
  lines.append(f"Unmet requirements: {_listed(unmet)}")

  titles = {
    c.course.resolved or c.course.code: c.title
    for r in program.requirements
    for slot in r.slots
    for c in slot
  }
  listed = audits.listed_codes(program)
  offered = store.offered(conn, student.term, listed)
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
  return lines


def _week_lines(
  conn: sqlite3.Connection, student: Student
) -> tuple[list[str], set[str]]:
  """The active schedule, its conflicts, missing sections, and units."""
  sections = store.sections(conn, student.term, list(student.section_ids))
  if not sections:
    return ["This week: nothing scheduled"], set()
  lines = ["This week:"]
  lines += [
    f"- {s.course_code} {s.type} {s.id}: {_tools.when(s)}, {_tools.who(s)}"
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
  courses = store.courses(conn, student.term, planned)
  for course in courses:
    chosen = [s for s in sections if s.course_code == course.code]
    if missing := schedule.missing_types(course, chosen):
      lines.append(f"{course.code} still needs a {' and a '.join(missing)}")
  units = sum(c.units.min for c in courses)
  lines.append(
    f"Units: {units:g} of {config.OVERLOAD_UNIT_THRESHOLD} at flat tuition"
  )
  if warning := _tools.overload_warning(units):
    lines.append(warning)
  return lines, {codes.identity(c) for c in planned}


def schedule_line(conn: sqlite3.Connection, term: int, v: Variant) -> str:
  """A schedule in one line: each course with its section numbers."""
  found = {s.id: s for s in store.sections(conn, term, list(v.section_ids))}
  by_course: dict[str, list[str]] = {}
  for sid in v.section_ids:
    if section := found.get(sid):
      by_course.setdefault(section.course_code, []).append(sid)
  courses = [f"{code} ({', '.join(ids)})" for code, ids in by_course.items()]
  return f"{v.name}: {_listed(courses)}"


def _screen_lines(conn: sqlite3.Connection, student: Student) -> list[str]:
  """Other schedules, and what the student is looking at."""
  lines = [
    f"Other schedule {schedule_line(conn, student.term, v)}"
    for v in student.variants
  ]
  screen = student.screen
  page = "degree page" if screen.page == "degree" else "planner"
  lines.append(f"On screen: the {page}")
  if screen.open_course:
    course = store.course(conn, student.term, screen.open_course)
    lines.append(
      f"Open course: {course.code} {course.title}"
      if course
      else f"Open course: {screen.open_course} (not offered this term)"
    )
  if screen.proposal:
    lines.append(
      "The week shows your proposal "
      f"{schedule_line(conn, student.term, screen.proposal)}, not yet kept"
    )
  return lines


def build(conn: sqlite3.Connection, student: Student) -> Brief:
  """Builds the brief for one message."""
  week, planned = _week_lines(conn, student)
  program = _program_lines(conn, student, planned)
  ge = audits.general_education(
    conn, student.completed, student.ap_credits, student.ge_counted
  )
  open_ge = [
    f"{p.code} {p.name} ({p.filled} of {p.required_count})"
    for p in ge
    if p.filled < p.required_count
  ]
  lines = [
    "[Student brief]",
    f"Planning: {_term_name(conn, student.term)}",
    *program,
    f"Open GE categories: {_listed(open_ge)}",
    f"Completed: {_listed(list(student.completed))}",
    *week,
    f"Shortlisted: {_listed(list(student.shortlisted))}",
    *_screen_lines(conn, student),
  ]
  text = "\n".join(lines)
  return Brief(text, frozenset(codes.mentions(text)))
