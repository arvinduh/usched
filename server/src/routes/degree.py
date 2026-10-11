"""Degree roadmap and prerequisite DAG audit endpoints.

This module exposes major programs, graduation category checklists, and
interactive prerequisite graph DAG structures.
"""

from http import HTTPStatus

import fastapi

from server.src.data import database, models
from server.src.engine import audit


router = fastapi.APIRouter(prefix="/api/degrees", tags=["degrees"])


def get_db(request: fastapi.Request) -> database.Database:
  """Retrieves database service instance from application state."""
  return request.app.state.db


@router.get("", response_model=list[models.DegreeProgram])
def list_degrees(request: fastapi.Request) -> list[models.DegreeProgram]:
  """Retrieves all available USC degree programs registered in catalogue."""
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_all_degrees(conn)
  finally:
    conn.close()


@router.get("/{degree_id}", response_model=models.DegreeProgram)
def get_degree(
  degree_id: str, request: fastapi.Request
) -> models.DegreeProgram:
  """Retrieves curricular details for a specific degree program."""
  db = get_db(request)
  conn = db.connect()
  try:
    degree = db.get_degree(conn, degree_id.lower().strip())
    if not degree:
      raise fastapi.HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        detail=f"Degree program '{degree_id}' was not found in the catalogue.",
      )
    return degree
  finally:
    conn.close()


@router.get("/{degree_id}/audit", response_model=audit.DegreeAuditResponse)
def audit_degree(
  degree_id: str,
  request: fastapi.Request,
  completed: str = "",
) -> audit.DegreeAuditResponse:
  """Computes degree progress and prerequisite DAG against completed courses."""
  db = get_db(request)
  conn = db.connect()
  try:
    deg = db.get_degree(conn, degree_id.lower().strip())
    if not deg:
      raise fastapi.HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        detail=f"Degree program '{degree_id}' was not found in the catalogue.",
      )

    completed_list = [
      c.strip().upper() for c in completed.split(",") if c.strip()
    ]
    req_course_ids = {
      cid.upper().strip()
      for cat in deg.categories
      for cid in cat.required_courses
    }

    all_courses = db.get_courses(conn, limit=2000)
    course_map: dict[str, models.Course] = {
      c.id.upper().strip(): c for c in all_courses
    }

    for cid in req_course_ids:
      if cid not in course_map:
        c_detail = db.get_course(conn, cid)
        if c_detail:
          course_map[cid] = c_detail

    return audit.audit_degree_progress(deg, completed_list, course_map)
  finally:
    conn.close()
