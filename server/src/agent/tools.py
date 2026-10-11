"""Structured tool schemas and execution dispatchers for AI advisor.

This module provides tools for searching courses with faculty RMP ratings,
evaluating schedule permutations, and calculating degree DAG bottlenecks.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from server.src.data import database, models
from server.src.engine import audit, solver


@dataclass
class ToolResult:
  """Execution output from an advisor tool with contextual UI actions."""

  content: str
  actions: list[dict[str, Any]] = field(default_factory=list)


OLLAMA_TOOLS = [
  {
    "type": "function",
    "function": {
      "name": "search_courses",
      "description": (
        "Searches USC course catalogue by title, department, or keyword."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Course search term or subject.",
          },
          "department": {
            "type": "string",
            "description": "Optional department prefix, e.g. CSCI or MATH.",
          },
          "ge_category": {
            "type": "string",
            "description": "Optional General Education code, e.g. GE-A.",
          },
        },
        "required": ["query"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "solve_schedule",
      "description": (
        "Constructs optimal, conflict-free weekly timetable combinations "
        "given target course codes and student temporal/faculty preferences."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "course_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
              "Target course codes, e.g. ['CSCI-104L', 'MATH-226']."
            ),
          },
          "excluded_days": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
              "Days of week to avoid entirely, e.g. ['Friday', 'Monday']."
            ),
          },
          "earliest_start_time": {
            "type": "string",
            "description": "Earliest allowable start time in HH:MM format.",
          },
          "latest_end_time": {
            "type": "string",
            "description": "Latest allowable end time in HH:MM format.",
          },
          "preferred_instructors": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
              "Preferred faculty surnames, e.g. ['Redekopp', 'Cote']."
            ),
          },
          "excluded_instructors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Faculty surnames to avoid.",
          },
          "min_rmp_rating": {
            "type": "number",
            "description": "Minimum acceptable RateMyProfessors score (0-5).",
          },
        },
        "required": ["course_codes"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "get_course_details",
      "description": (
        "Retrieves detailed section offerings, meeting schedules, and "
        "RateMyProfessors ratings for a specific course code."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "course_id": {
            "type": "string",
            "description": "Unique course code, e.g. 'CSCI-104L'.",
          },
        },
        "required": ["course_id"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "audit_degree_bottlenecks",
      "description": (
        "Evaluates student progress toward degree graduation and identifies "
        "prerequisite DAG bottleneck courses that unblock future milestones."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "completed_courses": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Completed course codes, e.g. ['CSCI-103L'].",
          },
          "degree_id": {
            "type": "string",
            "description": "Target degree ID, e.g. 'csci-bs'.",
          },
        },
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "record_completed_courses",
      "description": (
        "Records that a student has already taken/completed one or "
        "more courses or passed AP exams (e.g. 'I took CSCI 102')."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "course_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
              "List of completed course codes, e.g. ['CSCI-102L', 'MATH-125']."
            ),
          },
        },
        "required": ["course_codes"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "watch_course",
      "description": (
        "Adds a course to the student's watched classes zoning area "
        "for easy consideration across schedules."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "course_code": {
            "type": "string",
            "description": "Course code to watch, e.g. 'CSCI-201L'.",
          },
        },
        "required": ["course_code"],
      },
    },
  },
]


def tool_search_courses(
  conn: sqlite3.Connection,
  db: database.Database,
  query: str,
  department: str = "",
  ge_category: str = "",
) -> ToolResult:
  """Searches courses and returns token-compact cards with action chips."""
  courses = db.get_courses(
    conn,
    q=query,
    department=department or None,
    ge_category=ge_category or None,
    limit=5,
  )
  if not courses:
    return ToolResult(content=f"No courses found matching '{query}'.")

  lines: list[str] = [f"Found {len(courses)} courses matching '{query}':\n"]
  actions: list[dict[str, Any]] = []

  for c in courses:
    prereq_info = (
      f" | Prereqs: {c.prerequisites_raw}" if c.prerequisites_raw else ""
    )
    lines.append(f"**{c.id}**: {c.title} ({c.units}u){prereq_info}")
    if c.description:
      lines.append(f"  Summary: {c.description[:120]}...")

    if c.sections:
      sec = c.sections[0]
      prof_str = "Staff"
      if sec.instructor:
        r_score = sec.instructor.rmp_rating
        prof_str = (
          f"{sec.instructor.name} (★{r_score})"
          if r_score is not None
          else sec.instructor.name
        )
      days_str = ",".join(sec.days) if sec.days else "TBA"
      lines.append(
        f"  Primary Sec: {sec.id} [{sec.section_type}] {days_str} "
        f"{sec.start_time}-{sec.end_time} ({prof_str})"
      )
      actions.append(
        {
          "label": f"Add {c.id} to Calendar",
          "action": "ENROLL_SECTION",
          "payload": {"course_id": c.id, "section_id": sec.id},
        }
      )
    lines.append("")

  return ToolResult(content="\n".join(lines), actions=actions[:3])


def tool_get_course_details(
  conn: sqlite3.Connection,
  db: database.Database,
  course_id: str,
) -> ToolResult:
  """Retrieves all active sections and instructor evaluations for a course."""
  course = db.get_course(conn, course_id)
  if not course:
    return ToolResult(content=f"Course '{course_id}' was not found in catalog.")

  lines: list[str] = [
    f"## {course.id}: {course.title} ({course.units} units)",
    f"- Prerequisites: {course.prerequisites_raw or 'None'}",
    f"- Description: {course.description}",
    "\n**Available Sections**:",
  ]
  actions: list[dict[str, Any]] = []

  for s in course.sections:
    prof_info = "Staff"
    if s.instructor:
      r_score = s.instructor.rmp_rating
      r_diff = s.instructor.rmp_difficulty
      prof_info = (
        f"{s.instructor.name} (★{r_score}/5.0, Diff: {r_diff}/5.0)"
        if r_score is not None
        else s.instructor.name
      )
    days_str = ",".join(s.days) if s.days else "TBA"
    seats_str = f"{s.enrolled}/{s.capacity} seats"
    lines.append(
      f"- [{s.section_type}] {days_str} {s.start_time}-{s.end_time} "
      f"| {prof_info} | {seats_str} (Sec ID: {s.id})"
    )
    if len(actions) < 2:
      actions.append(
        {
          "label": f"Add Sec {s.id} ({s.section_type})",
          "action": "ENROLL_SECTION",
          "payload": {"course_id": course.id, "section_id": s.id},
        }
      )

  return ToolResult(content="\n".join(lines), actions=actions)


def tool_solve_schedule(
  conn: sqlite3.Connection,
  db: database.Database,
  course_codes: list[str],
  excluded_days: list[str] | None = None,
  earliest_start_time: str = "",
  latest_end_time: str = "",
  preferred_instructors: list[str] | None = None,
  excluded_instructors: list[str] | None = None,
  min_rmp_rating: float | None = None,
) -> ToolResult:
  """Computes conflict-free section combinations for target course codes."""
  sections_by_course: dict[str, list[models.Section]] = {}
  for cid in course_codes:
    c = db.get_course(conn, cid.strip().upper())
    if c and c.sections:
      sections_by_course[c.id] = c.sections

  if not sections_by_course:
    courses_str = ", ".join(course_codes)
    return ToolResult(
      content=f"No scheduled sections found for courses: {courses_str}."
    )

  candidates = solver.solve_candidate_schedules(
    sections_by_course,
    excluded_days=excluded_days,
    earliest_start_time=earliest_start_time,
    latest_end_time=latest_end_time,
    preferred_instructors=preferred_instructors,
    excluded_instructors=excluded_instructors,
    min_rmp_rating=min_rmp_rating,
    max_results=3,
  )

  if not candidates:
    return ToolResult(
      content=(
        f"Could not find a conflict-free combination for courses: "
        f"{', '.join(course_codes)} with the specified preferences. "
        "Try relaxing day/time constraints or choosing alternate courses."
      )
    )

  lines: list[str] = [
    f"Found {len(candidates)} conflict-free schedule options:\n"
  ]
  actions: list[dict[str, Any]] = []

  for idx, opt in enumerate(candidates, 1):
    rmp_str = f"Avg RMP ★{opt.average_rmp}" if opt.average_rmp else "RMP: N/A"
    days_str = ",".join(opt.days_used) if opt.days_used else "Custom Days"
    header = (
      f"### Option {idx}: {opt.summary}\n"
      f"- **Metrics**: {rmp_str} | Days: {days_str} | "
      f"Time Window: {opt.earliest_start}-{opt.latest_end}"
    )
    lines.append(header)
    for s in opt.sections:
      prof_name = s.instructor.name if s.instructor else "Staff"
      lines.append(
        f"  - {s.course_id} [{s.section_type}]: {','.join(s.days)} "
        f"{s.start_time}-{s.end_time} ({prof_name}, Sec: {s.id})"
      )
    lines.append("")

    sec_ids = [s.id for s in opt.sections]
    short_summary = opt.summary[:24] if opt.summary else f"Option {idx}"
    actions.append(
      {
        "label": f"+ Add '{short_summary}' as New Schedule",
        "action": "CREATE_CONFIGURATION",
        "payload": {
          "name": f"Option {idx}: {short_summary}",
          "section_ids": sec_ids,
        },
      }
    )
    actions.append(
      {
        "label": f"↺ Overwrite Active with Option {idx}",
        "action": "OVERWRITE_CONFIGURATION",
        "payload": {
          "section_ids": sec_ids,
        },
      }
    )

  return ToolResult(content="\n".join(lines), actions=actions)


def tool_audit_degree_bottlenecks(
  conn: sqlite3.Connection,
  db: database.Database,
  completed_courses: list[str],
  degree_id: str = "csci-bs",
) -> ToolResult:
  """Computes degree progress and prerequisite DAG bottleneck rankings."""
  deg = db.get_degree(conn, degree_id)
  if not deg:
    return ToolResult(
      content=f"Degree specification '{degree_id}' was not found in catalogue."
    )

  courses = db.get_courses(conn, limit=2000)
  course_map = {c.id: c for c in courses}
  audit_res = audit.audit_degree_progress(deg, completed_courses, course_map)

  pct = audit_res.percent_complete
  done_u = audit_res.total_completed_units
  tot_u = deg.total_units

  lines = [
    f"## Degree Audit: {deg.title}",
    f"- **Progress**: {pct}% ({done_u}/{tot_u} units fulfilled)",
  ]

  eligible = [
    node.course_id
    for node in audit_res.prereq_graph
    if node.status == models.CourseStatus.ELIGIBLE
    and node.course_id not in completed_courses
  ]

  actions: list[dict[str, Any]] = [
    {
      "label": "Open Degree DAG Tab",
      "action": "NAVIGATE_TAB",
      "payload": {"tab": "audit"},
    }
  ]

  if eligible:
    courses_str = ", ".join(eligible[:6])
    lines.append(f"\n⭐ **High-Value Eligible Courses**: {courses_str}")
    for cid in eligible[:2]:
      actions.append(
        {
          "label": f"Explore {cid} Sections",
          "action": "FILTER_EXPLORER",
          "payload": {"query": cid},
        }
      )

  if audit_res.unfulfilled_prerequisites:
    locked = ", ".join(audit_res.unfulfilled_prerequisites[:6])
    lines.append(f"\n⚠️ **Locked Milestones (Missing Prereqs)**: {locked}")

  return ToolResult(content="\n".join(lines), actions=actions)


def tool_record_completed_courses(
  course_codes: list[str],
) -> ToolResult:
  """Acknowledges completed courses and produces chips to mark them in state."""
  normalized = [c.strip().upper() for c in course_codes if c.strip()]
  actions: list[dict[str, Any]] = []
  for cid in normalized:
    actions.append(
      {
        "label": f"Mark Taken: {cid}",
        "action": "MARK_TAKEN",
        "payload": {"course_id": cid},
      }
    )
  courses_str = ", ".join(normalized)
  content = (
    f"Recorded {len(normalized)} completed courses: {courses_str}. "
    f"Your degree audit and prerequisite progress will reflect these."
  )
  return ToolResult(content=content, actions=actions)


def tool_watch_course(
  conn: sqlite3.Connection,
  db: database.Database,
  course_code: str,
) -> ToolResult:
  """Adds a course to the student's watched classes zoning area."""
  clean_cid = course_code.strip().upper()
  course = db.get_course(conn, clean_cid)
  title = course.title if course else clean_cid
  action = {
    "label": f"Watch {clean_cid}",
    "action": "WATCH_COURSE",
    "payload": {"course_id": clean_cid},
  }
  content = (
    f"Added {clean_cid} ({title}) to your watched classes zoning area. "
    f"You can view its sections and add it to any calendar configuration."
  )
  return ToolResult(content=content, actions=[action])


def execute_tool(
  name: str,
  arguments: dict[str, Any],
  conn: sqlite3.Connection,
  db: database.Database,
) -> ToolResult:
  """Dispatches tool execution dynamically by name."""
  if name == "search_courses":
    return tool_search_courses(
      conn,
      db,
      query=arguments.get("query", ""),
      department=arguments.get("department", ""),
      ge_category=arguments.get("ge_category", ""),
    )
  if name == "solve_schedule":
    return tool_solve_schedule(
      conn,
      db,
      course_codes=arguments.get("course_codes", []),
      excluded_days=arguments.get("excluded_days"),
      earliest_start_time=arguments.get("earliest_start_time", ""),
      latest_end_time=arguments.get("latest_end_time", ""),
      preferred_instructors=arguments.get("preferred_instructors"),
      excluded_instructors=arguments.get("excluded_instructors"),
      min_rmp_rating=arguments.get("min_rmp_rating"),
    )
  if name == "get_course_details":
    return tool_get_course_details(
      conn,
      db,
      course_id=arguments.get("course_id", ""),
    )
  if name == "audit_degree_bottlenecks":
    return tool_audit_degree_bottlenecks(
      conn,
      db,
      completed_courses=arguments.get("completed_courses", []),
      degree_id=arguments.get("degree_id", "csci-bs"),
    )
  if name == "record_completed_courses":
    return tool_record_completed_courses(
      course_codes=arguments.get("course_codes", []),
    )
  if name == "watch_course":
    return tool_watch_course(
      conn,
      db,
      course_code=arguments.get("course_code", ""),
    )
  return ToolResult(content=f"Unknown tool '{name}'.")
