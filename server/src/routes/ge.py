"""General Education audit and AP exam endpoints.

This module exposes canonical USC General Education categories, official
AP exam definition listings, and live GE requirement evaluation against
completed courses and exam scores.
"""

import fastapi
import pydantic

from server.src.data import database, models
from server.src.engine import ge as ge_engine


router = fastapi.APIRouter(prefix="/api/ge", tags=["ge"])


def get_db(request: fastapi.Request) -> database.Database:
  """Retrieves database service instance from application state."""
  return request.app.state.db


class GeAuditRequest(pydantic.BaseModel):
  """Request payload for evaluating General Education fulfillment."""

  completed_courses: list[str] = pydantic.Field(
    default_factory=list, description="Course identifiers completed by student."
  )
  ap_credits: list[models.UserApCredit] = pydantic.Field(
    default_factory=list, description="AP exam scores recorded by student."
  )


@router.get("/categories", response_model=list[str])
def list_ge_categories(request: fastapi.Request) -> list[str]:
  """Lists canonical General Education categories present in catalog."""
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_ge_categories(conn)
  finally:
    conn.close()


@router.get("/ap-exams", response_model=list[models.ApExamDefinition])
def list_ap_exams(request: fastapi.Request) -> list[models.ApExamDefinition]:
  """Lists official USC Advanced Placement exam equivalency definitions."""
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_ap_definitions(conn)
  finally:
    conn.close()


@router.post("/audit", response_model=models.GeAuditSummary)
def audit_ge_requirements(
  payload: GeAuditRequest, request: fastapi.Request
) -> models.GeAuditSummary:
  """Audits completed courses and AP exams against USC GE rules."""
  db = get_db(request)
  conn = db.connect()
  try:
    ap_defs = db.get_ap_definitions(conn)
    clean_completed = [
      c.strip().upper() for c in payload.completed_courses if c.strip()
    ]
    course_ge_map = db.get_course_ge_map(conn)
    # Also index with uppercase keys for case-insensitive lookup
    upper_ge_map: dict[str, list[str]] = {
      cid.upper(): cats for cid, cats in course_ge_map.items()
    }
    return ge_engine.evaluate_ge_audit(
      clean_completed, upper_ge_map, payload.ap_credits, ap_defs
    )
  finally:
    conn.close()
