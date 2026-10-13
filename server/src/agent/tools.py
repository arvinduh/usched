"""Tools the advisor model can call, and compact text renderings of sections.

Tools cover what the student brief cannot carry and what the student asks
the advisor to do: searching the catalog, one course's full detail,
building schedules, editing the week, and recording courses taken. Edits
to the week come back as a proposal the student keeps or discards. Each
tool reads the planning term through catalog_db, runs an engine where
needed, and returns text for the model plus chips for the student. Text is
terse on purpose: it is prompt context, not UI.
"""

import dataclasses
import inspect
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from server.src.agent import chips, llm
from server.src.catalog import codes
from server.src.data import catalog_db
from server.src.data import catalog_models as m
from server.src.engine import schedule


@dataclasses.dataclass
class ToolResult:
  """A tool's answer: text for the model, chips for the student."""

  content: str
  chips: list[chips.Chip] = dataclasses.field(default_factory=list)


_CODES = {
  "type": "array",
  "items": {"type": "string"},
  "description": "Course codes, e.g. ['CSCI-104L', 'MATH-226'].",
}
TOOLS = [
  llm.Tool(
    "search_courses",
    "Searches this term's courses by code, title, or topic. Use it for any "
    "course the student brief does not already list.",
    {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "e.g. 'machine learning'."},
        "ge_category": {
          "type": "string",
          "description": "Optional, e.g. GE-A.",
        },
      },
      "required": ["query"],
    },
  ),
  llm.Tool(
    "get_course_details",
    "Shows one course's prerequisites, restrictions, description, and "
    "sections with times, instructors, ratings, and seats.",
    {
      "type": "object",
      "properties": {
        "course_code": {"type": "string", "description": "e.g. 'CSCI-104L'."}
      },
      "required": ["course_code"],
    },
  ),
  llm.Tool(
    "edit_week",
    "Edits the student's week: adds sections by number (each swaps out its "
    "course's section of the same type), removes sections, or drops whole "
    "courses. The student sees the edited week and keeps or discards it.",
    {
      "type": "object",
      "properties": {
        "add_sections": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Section numbers to add, e.g. ['29905'].",
        },
        "remove_sections": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Section numbers to remove.",
        },
        "remove_courses": _CODES,
      },
    },
  ),
  llm.Tool(
    "mark_taken",
    "Records courses the student says they have already taken, so audits "
    "and suggestions count them.",
    {
      "type": "object",
      "properties": {"course_codes": _CODES},
      "required": ["course_codes"],
    },
  ),
  llm.Tool(
    "solve_schedule",
    "Builds conflict-free schedules that add every listed course to the "
    "student's week, keeping the sections already on it and honoring day, "
    "time, and instructor preferences. List a course already on the week "
    "to re-pick its sections.",
    {
      "type": "object",
      "properties": {
        "course_codes": _CODES,
        "excluded_days": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Days to keep free, e.g. ['Friday'].",
        },
        "earliest_start_time": {"type": "string", "description": "HH:MM."},
        "latest_end_time": {"type": "string", "description": "HH:MM."},
        "preferred_instructors": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Surnames to favor.",
        },
        "excluded_instructors": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Surnames to avoid.",
        },
        "min_rating": {
          "type": "number",
          "description": "Lowest acceptable RateMyProfessors rating, 1-5.",
        },
      },
      "required": ["course_codes"],
    },
  ),
]


def _clock(minute: int) -> str:
  return f"{minute // 60}:{minute % 60:02d}"


def when(section: m.Section) -> str:
  """A section's meeting times, e.g. "Mon,Wed 14:00-15:20", or TBA."""
  parts = [
    f"{','.join(meeting.days)} {_clock(meeting.start_minute)}-"
    f"{_clock(meeting.end_minute)}"
    for meeting in section.meetings
    if meeting.days
    and meeting.start_minute is not None
    and meeting.end_minute is not None
  ]
  return "; ".join(parts) or "TBA"


def who(section: m.Section) -> str:
  """A section's instructors with ratings, or Staff."""
  names = [
    f"{i.name} (★{i.rmp.rating}, difficulty {i.rmp.difficulty})"
    if i.rmp is not None and i.rmp.rating is not None
    else i.name
    for i in section.instructors
  ]
  return ", ".join(names) or "Staff"


def _units(units: m.Units) -> str:
  low, high = f"{units.min:g}", f"{units.max:g}"
  return low if low == high else f"{low}-{high}"


def _requisite_text(groups: Sequence[m.RequisiteGroup]) -> str:
  def option(refs: Sequence[m.CourseRef]) -> str:
    return " and ".join(r.resolved or r.code for r in refs)

  def group(g: m.RequisiteGroup) -> str:
    joined = " or ".join(option(o) for o in g.options)
    if g.required_count > 1:
      return f"{g.required_count} of ({joined})"
    return f"({joined})" if len(g.options) > 1 else joined

  return "; ".join(group(g) for g in groups) or "none"


def search_courses(
  conn: sqlite3.Connection, term: int, query: str, ge_category: str = ""
) -> ToolResult:
  """Lists the best few matches with their first section."""
  found = catalog_db.search_courses(
    conn, term, query, ge=ge_category or None, limit=5
  )
  if not found:
    return ToolResult(f"No courses match '{query}' this term.")
  lines = []
  for c in found:
    lines.append(f"{c.code}: {c.title} ({_units(c.units)} units)")
    if c.requisites.prerequisite:
      lines.append(
        f"  Prerequisites: {_requisite_text(c.requisites.prerequisite)}"
      )
    if c.sections:
      first = c.sections[0]
      lines.append(f"  e.g. {first.id} {first.type} {when(first)} {who(first)}")
  actions: list[chips.Chip] = [
    chips.Search(label=f"Show {c.code}", query=c.code) for c in found[:3]
  ]
  return ToolResult("\n".join(lines), actions)


def get_course_details(
  conn: sqlite3.Connection, term: int, course_code: str
) -> ToolResult:
  """Describes one course and up to a dozen of its sections."""
  course = catalog_db.course(conn, term, course_code.strip())
  if course is None:
    return ToolResult(f"{course_code} is not offered this term.")
  req = course.requisites
  lines = [
    f"{course.code}: {course.title} ({_units(course.units)} units)",
    f"Prerequisites: {_requisite_text(req.prerequisite)}",
  ]
  if req.corequisite:
    lines.append(f"Corequisites: {_requisite_text(req.corequisite)}")
  if course.recommended_prep:
    lines.append(f"Recommended preparation: {course.recommended_prep}")
  if course.restrictions:
    lines.append(
      "Restrictions: "
      + "; ".join(
        f"{'only' if r.inclusive else 'not'} {r.description}"
        for r in course.restrictions
      )
    )
  lines.append(f"Description: {course.description}")
  for s in course.sections[:12]:
    flags = " D-clearance" if s.requires_d_clearance else ""
    flags += " cancelled" if s.is_cancelled else ""
    lines.append(
      f"- {s.id} {s.type}{f' [{s.link_code}]' if s.link_code else ''}: "
      f"{when(s)} | {who(s)} | {s.registered}/{s.capacity} seats{flags}"
    )
  if len(course.sections) > 12:
    lines.append(f"(+{len(course.sections) - 12} more sections)")
  open_section = next(
    (s for s in course.sections if not s.is_cancelled and s.type == "Lecture"),
    None,
  )
  actions: list[chips.Chip] = [
    chips.WatchCourse(label=f"Shortlist {course.code}", course_code=course.code)
  ]
  if open_section is not None:
    actions.append(
      chips.EnrollSection(
        label=f"Add {course.code} {open_section.id}",
        section_id=open_section.id,
      )
    )
  return ToolResult("\n".join(lines), actions)


_DAYS: Mapping[str, m.Weekday] = {day.value.lower(): day for day in m.Weekday}


def _weekday(name: str) -> m.Weekday | None:
  return _DAYS.get(name.strip().lower()[:3])


def _minute(clock: str) -> int | None:
  hours, _, minutes = clock.strip().partition(":")
  if not (hours.isdigit() and (minutes.isdigit() or not minutes)):
    return None
  return int(hours) * 60 + int(minutes or 0)


def solve_schedule(
  conn: sqlite3.Connection,
  term: int,
  week: Sequence[str],
  course_codes: Sequence[str],
  excluded_days: Sequence[str] = (),
  earliest_start_time: str = "",
  latest_end_time: str = "",
  preferred_instructors: Sequence[str] = (),
  excluded_instructors: Sequence[str] = (),
  min_rating: float | None = None,
) -> ToolResult:
  """Finds the three best ways to add courses to the week; offers each.

  Sections already on the week (`week`, by number) stay fixed unless
  their course is listed, so each proposal is the whole resulting week.
  """
  courses = catalog_db.courses(conn, term, list(course_codes))
  found_codes = {codes.identity(c.code) for c in courses}
  missing = [c for c in course_codes if codes.identity(c) not in found_codes]
  if missing:
    return ToolResult(f"Not offered this term: {', '.join(missing)}.")
  kept = [
    s
    for s in catalog_db.sections(conn, term, list(week))
    if codes.identity(s.course_code) not in found_codes
  ]
  prefs = schedule.Preferences(
    excluded_days=frozenset(
      d for d in map(_weekday, excluded_days) if d is not None
    ),
    earliest_start=_minute(earliest_start_time),
    latest_end=_minute(latest_end_time),
    preferred=tuple(p.lower() for p in preferred_instructors if p),
    excluded=tuple(p.lower() for p in excluded_instructors if p),
    min_rating=min_rating,
  )
  options = schedule.solve(courses, prefs, around=kept)
  if not options:
    return ToolResult(
      "No conflict-free schedule adds all of "
      f"{', '.join(c.code for c in courses)} to the week; suggest dropping "
      "one, or listing a course already on the week to re-pick it."
    )
  lines = (
    [f"Keeps your week: {', '.join(f'{s.course_code} {s.id}' for s in kept)}"]
    if kept
    else []
  )
  actions: list[chips.Chip] = []
  for n, option in enumerate(options, 1):
    rating = option.average_rating
    lines.append(
      f"Option {n}: average rating {rating if rating is not None else 'n/a'}"
      + (
        f", {option.violations} preference misses" if option.violations else ""
      )
    )
    lines += [
      f"  {s.course_code} {s.id} {s.type}: {when(s)} | {who(s)}"
      for s in option.sections
    ]
    actions.append(
      chips.ProposeSchedule(
        label=f"Preview option {n}",
        name=f"Option {n}",
        section_ids=[s.id for s in kept] + [s.id for s in option.sections],
      )
    )
  return ToolResult("\n".join(lines), actions)


def edit_week(
  conn: sqlite3.Connection,
  term: int,
  week: Sequence[str],
  add_sections: Sequence[str] = (),
  remove_sections: Sequence[str] = (),
  remove_courses: Sequence[str] = (),
) -> ToolResult:
  """Previews the week with sections added and removed; offers it to keep.

  An added section swaps out its course's section of the same type (or of
  an incompatible link group), as picking it by hand would.
  """
  adding = catalog_db.sections(conn, term, list(add_sections))
  found = {s.id for s in adding}
  if unknown := [sid for sid in add_sections if sid not in found]:
    return ToolResult(f"Not sections this term: {', '.join(unknown)}.")
  current = {s.id: s for s in catalog_db.sections(conn, term, list(week))}
  dropped_courses = {codes.identity(c) for c in remove_courses}
  result = [
    current[sid]
    for sid in week
    if sid in current
    and sid not in remove_sections
    and codes.identity(current[sid].course_code) not in dropped_courses
  ]
  for section in sorted(adding, key=lambda s: list(add_sections).index(s.id)):
    result = [o for o in result if not schedule.displaces(section, o)]
    result.append(section)
  ids = [s.id for s in result]
  if ids == list(week):
    return ToolResult("That leaves the week unchanged.")
  lines = ["Edited week (shown to the student to keep or discard):"]
  lines += [
    f"- {s.course_code} {s.type} {s.id}: {when(s)} | {who(s)}" for s in result
  ]
  clashes = [
    f"{a.course_code} {a.id} with {b.course_code} {b.id}"
    for i, a in enumerate(result)
    for b in result[i + 1 :]
    if schedule.overlaps(a, b)
  ]
  if clashes:
    lines.append(f"Conflicts: {'; '.join(clashes)}")
  courses = list(dict.fromkeys(s.course_code for s in result))
  for course in catalog_db.courses(conn, term, courses):
    chosen = [s for s in result if s.course_code == course.code]
    if missing := schedule.missing_types(course, chosen):
      lines.append(f"{course.code} still needs a {' and a '.join(missing)}")
  return ToolResult(
    "\n".join(lines),
    [
      chips.ProposeSchedule(
        label="Preview the edit", name="Edited week", section_ids=ids
      )
    ],
  )


def mark_taken(
  conn: sqlite3.Connection, term: int, course_codes: Sequence[str]
) -> ToolResult:
  """Records courses the student says they took, once the catalog knows them."""
  del term  # Taken courses span terms.
  known = catalog_db.canonical(conn, course_codes)
  spelled = [
    known[k]
    for k in dict.fromkeys(map(codes.identity, course_codes))
    if k in known
  ]
  unknown = [c for c in course_codes if codes.identity(c) not in known]
  lines = [f"Marked taken: {', '.join(spelled)}." if spelled else ""]
  if unknown:
    lines.append(f"Not USC courses: {', '.join(unknown)}.")
  actions: list[chips.Chip] = (
    [
      chips.MarkTaken(
        label=f"Marked {', '.join(spelled)} taken", course_codes=spelled
      )
    ]
    if spelled
    else []
  )
  return ToolResult(" ".join(filter(None, lines)), actions)


_TOOLS: Mapping[str, Callable[..., ToolResult]] = {
  "search_courses": search_courses,
  "get_course_details": get_course_details,
  "solve_schedule": solve_schedule,
  "edit_week": edit_week,
  "mark_taken": mark_taken,
}


def execute(
  name: str,
  arguments: Mapping[str, Any],
  conn: sqlite3.Connection,
  term: int,
  week: Sequence[str],
) -> ToolResult:
  """Runs a tool by name; bad names or arguments become text for the model.

  A tool that declares a `week` parameter receives the student's week
  (section numbers) from the request, never from the model.
  """
  tool = _TOOLS.get(name)
  if tool is None:
    return ToolResult(f"Unknown tool '{name}'.")
  signature = inspect.signature(tool)
  context = {"week": week} if "week" in signature.parameters else {}
  try:
    bound = signature.bind(conn, term, **context, **arguments)
  except TypeError as e:
    return ToolResult(f"Bad arguments for {name}: {e}")
  return tool(*bound.args, **bound.kwargs)
