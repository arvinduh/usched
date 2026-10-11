"""Timetable scheduling and collision verification endpoints.

This module validates student schedules, detects day/minute interval overlaps,
and aggregates credit units for enrolled and wishlist selections.
"""

import fastapi
import pydantic

from server.src.data import database, models
from server.src.engine import conflicts


class ValidateScheduleRequest(pydantic.BaseModel):
  """Payload submitted to validate schedule collisions and units."""

  enrolled_section_ids: list[str] = pydantic.Field(
    default_factory=list,
    description="Section IDs for confirmed enrolled courses.",
  )
  wishlist_section_ids: list[str] = pydantic.Field(
    default_factory=list,
    description="Section IDs for candidate wishlist courses.",
  )


router = fastapi.APIRouter(prefix="/api/schedule", tags=["schedule"])


def get_db(request: fastapi.Request) -> database.Database:
  """Retrieves database service instance from application state."""
  return request.app.state.db


@router.post("/validate", response_model=conflicts.ValidateScheduleResponse)
def validate_schedule(
  payload: ValidateScheduleRequest, request: fastapi.Request
) -> conflicts.ValidateScheduleResponse:
  """Checks enrolled and wishlist course sections for meeting collisions."""
  db = get_db(request)
  conn = db.connect()
  try:
    enrolled_secs = db.get_sections(conn, payload.enrolled_section_ids)
    wishlist_secs = db.get_sections(conn, payload.wishlist_section_ids)

    for s in wishlist_secs:
      s.is_wishlist = True

    courses = db.get_courses(conn, limit=2000)
    units_map = {c.id: c.units for c in courses}

    return conflicts.evaluate_schedule(enrolled_secs, wishlist_secs, units_map)
  finally:
    conn.close()


@router.get("/sections", response_model=list[models.Section])
def get_sections(ids: str, request: fastapi.Request) -> list[models.Section]:
  """Retrieves detailed section objects for a comma-separated list of IDs."""
  section_ids = [s.strip() for s in ids.split(",") if s.strip()]
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_sections(conn, section_ids)
  finally:
    conn.close()
