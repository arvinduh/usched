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

from server import config
from server.agent import _chips, _llm
from server.db import models, store
from server.db.ingest import codes
from server.engine import schedule


@dataclasses.dataclass
class ToolResult:
  """A tool's answer: text for the model, chips for the student."""

  content: str
  chips: list[_chips.Chip] = dataclasses.field(default_factory=list)


_CODES = {
  "type": "array",
  "items": {"type": "string"},
  "description": "Course codes, e.g. ['CSCI-104L', 'MATH-226'].",
}
TOOLS = [
  _llm.Tool(
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
  _llm.Tool(
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
  _llm.Tool(
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
  _llm.Tool(
    "mark_taken",
    "Records courses the student says they have already taken, so audits "
    "and suggestions count them.",
    {
      "type": "object",
      "properties": {"course_codes": _CODES},
      "required": ["course_codes"],
    },
  ),
  _llm.Tool(
    "solve_schedule",
    "Builds conflict-free schedules that add every listed course to the "
    "student's week, keeping the sections already on it. Filters are hard "
    "(a week breaking one is never offered); goals rank the weeks that "
    "remain, first goal first. Map wishes onto them: 'no Fridays' is "
    "excluded_days; 'nothing after 6' is latest_end_time 18:00; 'mornings "
    "free' is earliest_start_time; 'keep lunch free' is keep_free; 'only "
    "three days on campus' is max_days; 'best professors' is the rating "
    "goal; 'no breaks' or 'back to back' is compact; 'easy' is easy. List a "
    "course already on the week to re-pick its sections.",
    {
      "type": "object",
      "properties": {
        "course_codes": _CODES,
        "goals": {
          "type": "array",
          "items": {"type": "string", "enum": [g.value for g in schedule.Goal]},
          "description": "What to maximize, most important first. Default "
          "['rating', 'compact'].",
        },
        "excluded_days": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Days with no class, e.g. ['Friday'].",
        },
        "earliest_start_time": {"type": "string", "description": "HH:MM."},
        "latest_end_time": {"type": "string", "description": "HH:MM."},
        "keep_free": {
          "type": "array",
          "description": "Times with no class, e.g. lunch.",
          "items": {
            "type": "object",
            "properties": {
              "days": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Default every weekday.",
              },
              "start": {"type": "string", "description": "HH:MM."},
              "end": {"type": "string", "description": "HH:MM."},
            },
            "required": ["start", "end"],
          },
        },
        "max_days": {
          "type": "integer",
          "description": "Most days on campus, counting the current week.",
        },
        "open_seats_only": {"type": "boolean"},
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
        "allow_overload": {
          "type": "boolean",
          "description": "Allow a week past "
          f"{config.OVERLOAD_UNIT_THRESHOLD} units, the flat-tuition "
          "maximum. Only when the student asked for more and accepts that "
          "each extra unit costs extra tuition.",
        },
      },
      "required": ["course_codes"],
    },
  ),
]


def _clock(minute: int) -> str:
  return f"{minute // 60}:{minute % 60:02d}"


def when(section: models.Section) -> str:
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


def who(section: models.Section) -> str:
  """A section's instructors with ratings, or Staff."""
  names = [
    f"{i.name} (★{i.rmp.rating}, difficulty {i.rmp.difficulty})"
    if i.rmp is not None and i.rmp.rating is not None
    else i.name
    for i in section.instructors
  ]
  return ", ".join(names) or "Staff"


def _units(units: models.Units) -> str:
  low, high = f"{units.min:g}", f"{units.max:g}"
  return low if low == high else f"{low}-{high}"


def _requisite_text(groups: Sequence[models.RequisiteGroup]) -> str:
  def option(refs: Sequence[models.CourseRef]) -> str:
    return " and ".join(r.resolved or r.code for r in refs)

  def group(g: models.RequisiteGroup) -> str:
    joined = " or ".join(option(o) for o in g.options)
    if g.required_count > 1:
      return f"{g.required_count} of ({joined})"
    return f"({joined})" if len(g.options) > 1 else joined

  return "; ".join(group(g) for g in groups) or "none"


def search_courses(
  conn: sqlite3.Connection, term: int, query: str, ge_category: str = ""
) -> ToolResult:
  """Lists the best few matches with their first section."""
  found = store.search_courses(
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
  actions: list[_chips.Chip] = [
    _chips.Search(label=f"Show {c.code}", query=c.code) for c in found[:3]
  ]
  return ToolResult("\n".join(lines), actions)


def get_course_details(
  conn: sqlite3.Connection, term: int, course_code: str
) -> ToolResult:
  """Describes one course and up to a dozen of its sections."""
  course = store.course(conn, term, course_code.strip())
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
  actions: list[_chips.Chip] = [
    _chips.WatchCourse(
      label=f"Shortlist {course.code}", course_code=course.code
    )
  ]
  if open_section is not None:
    actions.append(
      _chips.EnrollSection(
        label=f"Add {course.code} {open_section.id}",
        section_id=open_section.id,
      )
    )
  return ToolResult("\n".join(lines), actions)


_DAYS: Mapping[str, models.Weekday] = {
  day.value.lower(): day for day in models.Weekday
}


def _weekday(name: str) -> models.Weekday | None:
  return _DAYS.get(name.strip().lower()[:3])


def _minute(clock: str) -> int | None:
  hours, _, minutes = clock.strip().partition(":")
  if not (hours.isdigit() and (minutes.isdigit() or not minutes)):
    return None
  return int(hours) * 60 + int(minutes or 0)


def _window(spec: Mapping[str, Any]) -> schedule.Window | None:
  start, end = _minute(spec.get("start", "")), _minute(spec.get("end", ""))
  if start is None or end is None:
    return None
  days = frozenset(
    d for d in map(_weekday, spec.get("days") or []) if d is not None
  ) or frozenset(models.Weekday) - {models.Weekday.SAT, models.Weekday.SUN}
  return schedule.Window(days, start, end)


def _span(minutes: int | None) -> str:
  return _clock(minutes) if minutes is not None else "TBA"


def term_units(conn: sqlite3.Connection, course_codes: Sequence[str]) -> float:
  """Units of the distinct courses, a variable-unit course at its least.

  Counts as the client's week header does, so both name one total.
  """
  return sum(u.min for u in store.units_of(conn, course_codes).values())


def overload_warning(units: float) -> str:
  """Says plainly what a term past the flat-tuition maximum costs, or ""."""
  over = schedule.overload(units)
  if over == 0:
    return ""
  cap = config.OVERLOAD_UNIT_THRESHOLD
  return (
    f"Overload: {units:g} units is {over:g} past the {cap}-unit flat-tuition "
    f"maximum, and each unit past {cap} costs extra tuition."
  )


# What a week that ranks each goal first is best at, as a student reads it.
_GOAL_TITLES: Mapping[schedule.Goal, str] = {
  schedule.Goal.RATING: "Best professors",
  schedule.Goal.EASY: "Easiest professors",
  schedule.Goal.COMPACT: "Fewest breaks",
  schedule.Goal.FEWER_DAYS: "Fewest days",
  schedule.Goal.LATE_START: "Latest start",
  schedule.Goal.EARLY_END: "Earliest finish",
  schedule.Goal.SEATS: "Most open seats",
}


def _title(lens: schedule.Lens) -> str:
  if lens.day_off is not None:
    return f"No class on {lens.day_off}"
  return _GOAL_TITLES[lens.goal]


def _profs(week: schedule.Schedule) -> str:
  rating = week.average_rating
  return f"avg prof {rating:.1f}" if rating is not None else "profs unrated"


def _tradeoff(option: schedule.Alternative) -> str:
  """What an option wins and what it costs, in one line.

  For example "No class on Fri, avg prof 3.4" beside "Best professors
  (avg prof 4.5), class on Fri".
  """
  lens, week = option.lens, option.schedule
  measures = {
    schedule.Goal.RATING: _profs(week),
    schedule.Goal.EASY: f"difficulty {week.average_difficulty or 'n/a'}",
    schedule.Goal.COMPACT: f"{week.gap_minutes} min of breaks",
    schedule.Goal.FEWER_DAYS: f"{len(week.days)} days on campus",
    schedule.Goal.LATE_START: f"first class {_span(week.first_start)}",
    schedule.Goal.EARLY_END: f"done by {_span(week.last_end)}",
    schedule.Goal.SEATS: "most seats left",
  }
  if lens.day_off is not None:
    facts = [_title(lens), _profs(week)]
  else:
    facts = [f"{_title(lens)} ({measures[lens.goal]})"]
    if lens.goal != schedule.Goal.RATING:
      facts.append(_profs(week))
  if models.Weekday.FRI in week.days:
    facts.append("class on Fri")
  return ", ".join(facts)


def _offer(
  options: Sequence[schedule.Alternative], kept: Sequence[models.Section]
) -> ToolResult:
  """Lists each option's trade-off and sections; proposes each one."""
  lines = (
    [f"Keeps your week: {', '.join(f'{s.course_code} {s.id}' for s in kept)}"]
    if kept
    else []
  )
  actions: list[_chips.Chip] = []
  for n, option in enumerate(options, 1):
    week = option.schedule
    facts = [
      f"rating {week.average_rating or 'n/a'}",
      f"difficulty {week.average_difficulty or 'n/a'}",
      f"{len(week.days)} days",
      f"{week.gap_minutes} min between classes",
      f"{_span(week.first_start)}-{_span(week.last_end)}",
    ]
    tradeoff = _tradeoff(option)
    lines.append(f"Option {n}, {tradeoff}: {', '.join(facts)}")
    lines += [
      f"  {s.course_code} {s.id} {s.type}: {when(s)} | {who(s)}"
      for s in week.sections
    ]
    actions.append(
      _chips.ProposeSchedule(
        label=f"Preview option {n}",
        name=_title(option.lens),
        section_ids=[s.id for s in kept] + [s.id for s in week.sections],
        tradeoff=tradeoff if len(options) > 1 else "",
      )
    )
  if len(options) == 1:
    lines.append(
      "No other week is a real alternative: each moves at most one course "
      "or is no better at what it trades for."
    )
  return ToolResult("\n".join(lines), actions)


def solve_schedule(
  conn: sqlite3.Connection,
  term: int,
  week: Sequence[str],
  course_codes: Sequence[str],
  goals: Sequence[str] = (),
  excluded_days: Sequence[str] = (),
  earliest_start_time: str = "",
  latest_end_time: str = "",
  keep_free: Sequence[Mapping[str, Any]] = (),
  max_days: int | None = None,
  open_seats_only: bool = False,
  preferred_instructors: Sequence[str] = (),
  excluded_instructors: Sequence[str] = (),
  min_rating: float | None = None,
  allow_overload: bool = False,
) -> ToolResult:
  """Finds up to three ways to add courses to the week; offers each.

  Each way wins a different trade-off (see `schedule.alternatives`).

  Sections already on the week (`week`, by number) stay fixed unless
  their course is listed, so each proposal is the whole resulting week.
  When no week meets every filter, says which filters block it. A week
  past the flat-tuition unit maximum is refused unless `allow_overload`,
  and then offered with the overload warning.
  """
  courses = store.courses(conn, term, list(course_codes))
  found_codes = {codes.identity(c.code) for c in courses}
  missing = [c for c in course_codes if codes.identity(c) not in found_codes]
  if missing:
    return ToolResult(f"Not offered this term: {', '.join(missing)}.")
  known = {g.value for g in schedule.Goal}
  if unknown := [g for g in goals if g not in known]:
    return ToolResult(f"Unknown goals: {', '.join(unknown)}.")
  kept = [
    s
    for s in store.sections(conn, term, list(week))
    if codes.identity(s.course_code) not in found_codes
  ]
  units = term_units(
    conn, [*{s.course_code for s in kept}, *(c.code for c in courses)]
  )
  warning = overload_warning(units)
  if warning and not allow_overload:
    return ToolResult(
      f"{warning} Offer no week past {config.OVERLOAD_UNIT_THRESHOLD} units: "
      "suggest a course to drop, and call again with allow_overload only "
      "once the student says they accept the extra tuition."
    )
  prefs = schedule.Preferences(
    filters=schedule.Filters(
      excluded_days=frozenset(
        d for d in map(_weekday, excluded_days) if d is not None
      ),
      earliest_start=_minute(earliest_start_time),
      latest_end=_minute(latest_end_time),
      keep_free=tuple(w for w in map(_window, keep_free) if w is not None),
      max_days=max_days,
      excluded=tuple(p.lower() for p in excluded_instructors if p),
      min_rating=min_rating,
      open_seats_only=open_seats_only,
    ),
    goals=tuple(schedule.Goal(g) for g in goals)
    or schedule.NO_PREFERENCES.goals,
    preferred=tuple(p.lower() for p in preferred_instructors if p),
  )
  options = schedule.alternatives(courses, prefs, around=kept)
  if not options:
    return ToolResult(_why_none(courses, prefs, kept))
  offered = _offer(options, kept)
  if warning:
    offered.content = f"{warning} Say so plainly.\n{offered.content}"
  return offered


def _why_none(
  courses: Sequence[models.Course],
  prefs: schedule.Preferences,
  kept: Sequence[models.Section],
) -> str:
  """Why no week adds the courses, and what to suggest instead."""
  listed = ", ".join(c.code for c in courses)
  if blocking := schedule.blockers(courses, prefs, around=kept):
    return (
      f"No week adds {listed} and meets every filter. Dropping "
      f"{' or '.join(blocking)} would allow one; ask which to give up."
    )
  if prefs.filters != schedule.Filters():
    return (
      f"No week adds {listed} and meets these filters together, and no "
      "single filter is to blame: suggest relaxing several, or dropping a "
      "course."
    )
  return (
    f"No conflict-free week adds all of {listed}; suggest dropping one, "
    "or listing a course already on the week to re-pick it."
  )


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
  adding = store.sections(conn, term, list(add_sections))
  found = {s.id for s in adding}
  if unknown := [sid for sid in add_sections if sid not in found]:
    return ToolResult(f"Not sections this term: {', '.join(unknown)}.")
  current = {s.id: s for s in store.sections(conn, term, list(week))}
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
  courses = store.courses(
    conn, term, list(dict.fromkeys(s.course_code for s in result))
  )
  for course in courses:
    chosen = [s for s in result if s.course_code == course.code]
    if missing := schedule.missing_types(course, chosen):
      lines.append(f"{course.code} still needs a {' and a '.join(missing)}")
  if warning := overload_warning(sum(c.units.min for c in courses)):
    lines.append(f"{warning} Say so plainly before they keep it.")
  return ToolResult(
    "\n".join(lines),
    [
      _chips.ProposeSchedule(
        label="Preview the edit", name="Edited week", section_ids=ids
      )
    ],
  )


def mark_taken(
  conn: sqlite3.Connection, term: int, course_codes: Sequence[str]
) -> ToolResult:
  """Records courses the student says they took, once the catalog knows them."""
  del term  # Taken courses span terms.
  known = store.canonical(conn, course_codes)
  spelled = [
    known[k]
    for k in dict.fromkeys(map(codes.identity, course_codes))
    if k in known
  ]
  unknown = [c for c in course_codes if codes.identity(c) not in known]
  lines = [f"Marked taken: {', '.join(spelled)}." if spelled else ""]
  if unknown:
    lines.append(f"Not USC courses: {', '.join(unknown)}.")
  actions: list[_chips.Chip] = (
    [
      _chips.MarkTaken(
        label=f"Marked {', '.join(spelled)} taken", course_codes=spelled
      )
    ]
    if spelled
    else []
  )
  return ToolResult(" ".join(filter(None, lines)), actions)


def describe(name: str, arguments: Mapping[str, Any]) -> str:
  """What a tool call is doing, in words a student reads while it runs."""
  listed = ", ".join(arguments.get("course_codes") or [])
  match name:
    case "search_courses":
      return f"Searching courses for “{arguments.get('query', '')}”"
    case "get_course_details":
      return f"Reading {arguments.get('course_code', 'a course')}"
    case "solve_schedule":
      return (
        f"Building schedules with {listed}" if listed else "Building schedules"
      )
    case "edit_week":
      return "Editing your week"
    case "mark_taken":
      return f"Recording {listed} as taken" if listed else "Recording courses"
    case _:
      return "Working"


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
