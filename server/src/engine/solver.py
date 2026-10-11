"""Schedule permutation and constraint solver engine.

This module evaluates combinations of course sections to construct conflict-free
weekly schedules meeting student temporal preferences and instructor ratings.
"""

import itertools
from collections import defaultdict

import pydantic

from server.src.data import models
from server.src.engine import conflicts


class ScheduleOption(pydantic.BaseModel):
  """A conflict-free combination of sections representing a full schedule."""

  sections: list[models.Section] = pydantic.Field(
    description="All scheduled course sections included in candidate."
  )
  course_ids: list[str] = pydantic.Field(
    description="Unique course codes satisfied by schedule option."
  )
  summary: str = pydantic.Field(
    default="",
    description="Human-readable schedule summary with courses and faculty.",
  )
  professors: list[str] = pydantic.Field(
    default_factory=list,
    description="Instructors teaching the enrolled sections.",
  )
  days_used: list[str] = pydantic.Field(
    default_factory=list,
    description="Unique days of week with class meetings.",
  )
  average_rmp: float | None = pydantic.Field(
    default=None, description="Average RateMyProfessors score across faculty."
  )
  earliest_start: str = pydantic.Field(
    default="00:00", description="Earliest section start time (HH:MM)."
  )
  latest_end: str = pydantic.Field(
    default="00:00", description="Latest section end time (HH:MM)."
  )
  score: float = pydantic.Field(
    default=0.0, description="Overall optimization ranking score."
  )


def _format_minute(m: int) -> str:
  """Formats minutes from midnight as HH:MM string."""
  hours = m // 60
  minutes = m % 60
  return f"{hours:02d}:{minutes:02d}"


def parse_time_to_minute(time_str: str) -> int:
  """Parses HH:MM time string to minutes from midnight."""
  if not time_str or ":" not in time_str:
    return 0
  parts = time_str.strip().split(":")
  try:
    return int(parts[0]) * 60 + int(parts[1])
  except (ValueError, IndexError):
    return 0


def _day_matches(day_name: str, pattern: str) -> bool:
  """Checks if meeting day matches target day name or abbreviation."""
  d = day_name.lower().strip()
  p = pattern.lower().strip()
  if not p:
    return False
  return d.startswith(p) or p.startswith(d)


def _section_meets_constraints(
  sec: models.Section,
  excluded_days: list[str],
  min_start_minute: int,
  max_end_minute: int,
  excluded_instructors: list[str],
  min_rmp: float | None,
) -> bool:
  """Checks whether a single section satisfies all student constraints."""
  # Excluded days check
  if excluded_days:
    for ex_day in excluded_days:
      if any(_day_matches(d, ex_day) for d in sec.days):
        return False

  # Earliest start minute check
  if min_start_minute > 0 and sec.start_minute > 0:
    if sec.start_minute < min_start_minute:
      return False

  # Latest end minute check
  if max_end_minute > 0 and sec.end_minute > 0:
    if sec.end_minute > max_end_minute:
      return False

  # Excluded instructor check
  if excluded_instructors and sec.instructor:
    prof_name = sec.instructor.name.lower()
    if any(ex.lower().strip() in prof_name for ex in excluded_instructors):
      return False

  # Minimum RMP rating check
  if min_rmp is not None and sec.instructor:
    rating = sec.instructor.rmp_rating
    if rating is not None and rating < min_rmp:
      return False

  return True


def solve_candidate_schedules(
  sections_by_course: dict[str, list[models.Section]],
  excluded_days: list[str] | None = None,
  earliest_start_time: str = "",
  latest_end_time: str = "",
  preferred_instructors: list[str] | None = None,
  excluded_instructors: list[str] | None = None,
  min_rmp_rating: float | None = None,
  max_results: int = 3,
) -> list[ScheduleOption]:
  """Computes conflict-free combinations of sections for target courses.

  Args:
    sections_by_course: Mapping course_id to candidate sections.
    excluded_days: Days of the week to avoid (e.g. ['Friday', 'Monday']).
    earliest_start_time: Earliest allowed start time (e.g. '10:00').
    latest_end_time: Latest allowed end time (e.g. '17:00').
    preferred_instructors: Preferred faculty surnames (e.g. ['Redekopp']).
    excluded_instructors: Faculty surnames to avoid.
    min_rmp_rating: Minimum acceptable RateMyProfessors rating (e.g. 4.0).
    max_results: Maximum count of ranked schedule candidates to return.

  Returns:
    List of non-conflicting ScheduleOption models ordered by ranking score.
  """
  if not sections_by_course:
    return []

  ex_days = excluded_days or []
  pref_profs = [p.lower().strip() for p in (preferred_instructors or []) if p]
  ex_profs = excluded_instructors or []
  min_start = parse_time_to_minute(earliest_start_time)
  max_end = parse_time_to_minute(latest_end_time)

  # Group sections by (course_id, section_type) to pick one of each type.
  type_groups: list[list[models.Section]] = []
  course_codes: list[str] = []

  for course_id, sec_list in sections_by_course.items():
    if not sec_list:
      continue
    course_codes.append(course_id)
    by_type: dict[str, list[models.Section]] = defaultdict(list)
    for s in sec_list:
      if _section_meets_constraints(
        s, ex_days, min_start, max_end, ex_profs, min_rmp_rating
      ):
        by_type[s.section_type].append(s)

    # If constraint filtering eliminated all sections for a type, fallback.
    for stype in set(s.section_type for s in sec_list):
      if by_type[stype]:
        type_groups.append(by_type[stype])
      else:
        fallback = [s for s in sec_list if s.section_type == stype]
        if fallback:
          type_groups.append(fallback)

  if not type_groups:
    return []

  # Rank sections within group: preferred professors first, then RMP score
  capped_groups: list[list[models.Section]] = []
  for grp in type_groups:
    sorted_grp = sorted(
      grp,
      key=lambda s: (
        any(p in s.instructor.name.lower() for p in pref_profs if s.instructor),
        (s.instructor.rmp_rating or 0.0) if s.instructor else 0.0,
      ),
      reverse=True,
    )
    capped_groups.append(sorted_grp[:4])

  valid_candidates: list[ScheduleOption] = []

  # Evaluate combinations
  for combination in itertools.product(*capped_groups):
    comb_list = list(combination)
    has_conflict = False
    for i in range(len(comb_list)):
      for j in range(i + 1, len(comb_list)):
        if conflicts.detect_conflict_between_sections(
          comb_list[i], comb_list[j]
        ):
          has_conflict = True
          break
      if has_conflict:
        break

    if has_conflict:
      continue

    # Score calculation
    rmp_scores = [
      s.instructor.rmp_rating
      for s in comb_list
      if s.instructor and s.instructor.rmp_rating is not None
    ]
    avg_rmp = sum(rmp_scores) / len(rmp_scores) if rmp_scores else None

    # Preferred professors boost
    pref_match_count = sum(
      1
      for s in comb_list
      if s.instructor
      and any(p in s.instructor.name.lower() for p in pref_profs)
    )

    starts = [s.start_minute for s in comb_list if s.start_minute > 0]
    ends = [s.end_minute for s in comb_list if s.end_minute > 0]
    earliest_min = min(starts) if starts else 0
    latest_min = max(ends) if ends else 0

    all_days: set[str] = set()
    for s in comb_list:
      all_days.update(s.days)

    score = (avg_rmp or 3.0) * 2.0 + (pref_match_count * 5.0)
    for ex_d in ex_days:
      if any(_day_matches(d, ex_d) for d in all_days):
        score -= 10.0

    # Build human-readable summary
    summary_parts: list[str] = []
    profs_list: list[str] = []
    for s in comb_list:
      if s.section_type in ("Lecture", "Lecture-Lab") or len(comb_list) <= 2:
        prof_info = "Staff"
        if s.instructor:
          r_score = s.instructor.rmp_rating
          prof_info = (
            f"{s.instructor.name} ({r_score}/5.0)"
            if r_score is not None
            else s.instructor.name
          )
          profs_list.append(s.instructor.name)
        summary_parts.append(f"{s.course_id}: {prof_info}")

    if not summary_parts:
      summary_parts = [f"{s.course_id}" for s in comb_list]

    valid_candidates.append(
      ScheduleOption(
        sections=comb_list,
        course_ids=sorted(list(set(s.course_id for s in comb_list))),
        summary=" + ".join(summary_parts),
        professors=list(set(profs_list)),
        days_used=sorted(list(all_days)),
        average_rmp=round(avg_rmp, 2) if avg_rmp is not None else None,
        earliest_start=_format_minute(earliest_min),
        latest_end=_format_minute(latest_min),
        score=round(score, 2),
      )
    )

  valid_candidates.sort(key=lambda c: c.score, reverse=True)
  return valid_candidates[:max_results]
