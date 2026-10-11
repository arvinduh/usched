"""Interval time collision detection engine for academic course schedules.

This module detects minute-level overlaps between meeting times of enrolled
and candidate sections across days of the week using bitmask day operations
and minute-interval arithmetic.
"""

import pydantic

from server.src.data import models


class ScheduleConflict(pydantic.BaseModel):
  """Time overlap collision between two scheduled course sections."""

  course_a_id: str = pydantic.Field(description="First colliding course code.")
  section_a_id: str = pydantic.Field(description="First colliding section ID.")
  course_b_id: str = pydantic.Field(description="Second colliding course code.")
  section_b_id: str = pydantic.Field(description="Second colliding section ID.")
  day: str = pydantic.Field(description="Day of week with time overlap.")
  overlap_start: int = pydantic.Field(
    description="Collision start minute from midnight."
  )
  overlap_end: int = pydantic.Field(
    description="Collision end minute from midnight."
  )
  message: str = pydantic.Field(
    default="",
    description="Human-readable warning explaining collision interval.",
  )


class ValidateScheduleResponse(pydantic.BaseModel):
  """Verification result detailing conflicts and aggregate workload."""

  is_valid: bool = pydantic.Field(
    description="True if zero hard conflicts exist among enrolled sections."
  )
  conflicts: list[ScheduleConflict] = pydantic.Field(
    default_factory=list, description="Detected overlapping meeting blocks."
  )
  total_enrolled_units: float = pydantic.Field(
    default=0.0, description="Aggregate credit units for enrolled sections."
  )
  total_wishlist_units: float = pydantic.Field(
    default=0.0, description="Aggregate credit units for wishlist sections."
  )


def detect_conflict_between_sections(
  sec_a: models.Section, sec_b: models.Section
) -> list[ScheduleConflict]:
  """Identifies day and time interval collisions between two sections.

  Classes can meet on the same day without conflict as long as their
  meeting time intervals do not overlap.
  """
  if sec_a.id == sec_b.id:
    return []

  if sec_a.start_minute == 0 and sec_a.end_minute == 0:
    return []
  if sec_b.start_minute == 0 and sec_b.end_minute == 0:
    return []

  mask_a = models.parse_days_mask(sec_a.days)
  mask_b = models.parse_days_mask(sec_b.days)
  common_days = mask_a & mask_b
  if not common_days:
    return []

  if (
    sec_a.start_minute >= sec_b.end_minute
    or sec_b.start_minute >= sec_a.end_minute
  ):
    return []

  overlap_start = max(sec_a.start_minute, sec_b.start_minute)
  overlap_end = min(sec_a.end_minute, sec_b.end_minute)
  conflicts: list[ScheduleConflict] = []
  for flag, day_name in models.DAY_FLAG_TO_NAME:
    if not (common_days & flag):
      continue
    conflicts.append(
      ScheduleConflict(
        course_a_id=sec_a.course_id,
        section_a_id=sec_a.id,
        course_b_id=sec_b.course_id,
        section_b_id=sec_b.id,
        day=day_name,
        overlap_start=overlap_start,
        overlap_end=overlap_end,
      )
    )

  return conflicts


def evaluate_schedule(
  enrolled: list[models.Section],
  wishlist: list[models.Section],
  units_map: dict[str, float],
) -> ValidateScheduleResponse:
  """Validates entire schedule for intra-enrolled and candidate collisions."""
  conflicts: list[ScheduleConflict] = []
  seen_pairs: set[frozenset[str]] = set()

  for i in range(len(enrolled)):
    for j in range(i + 1, len(enrolled)):
      pair = frozenset({enrolled[i].id, enrolled[j].id})
      if pair in seen_pairs:
        continue
      seen_pairs.add(pair)
      conflicts.extend(
        detect_conflict_between_sections(enrolled[i], enrolled[j])
      )

  for w in wishlist:
    for e in enrolled:
      pair = frozenset({w.id, e.id})
      if pair in seen_pairs:
        continue
      seen_pairs.add(pair)
      conflicts.extend(detect_conflict_between_sections(w, e))

  enrolled_courses = {s.course_id for s in enrolled}
  wishlist_courses = {
    s.course_id for s in wishlist if s.course_id not in enrolled_courses
  }

  total_enrolled = sum(units_map.get(cid, 4.0) for cid in enrolled_courses)
  total_wishlist = sum(units_map.get(cid, 4.0) for cid in wishlist_courses)

  has_hard_conflict = any(
    c.section_a_id in {e.id for e in enrolled}
    and c.section_b_id in {e.id for e in enrolled}
    for c in conflicts
  )

  return ValidateScheduleResponse(
    is_valid=not has_hard_conflict,
    conflicts=conflicts,
    total_enrolled_units=total_enrolled,
    total_wishlist_units=total_wishlist,
  )
