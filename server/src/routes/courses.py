"""Course catalog and instructor evaluation endpoints.

This module exposes course discovery with SQL-level keyword search,
department/GE filtering, and single-query aggregated sections.
"""

from http import HTTPStatus

import fastapi

from server.src.data import database, models


router = fastapi.APIRouter(prefix="/api/courses", tags=["courses"])


def get_db(request: fastapi.Request) -> database.Database:
  """Retrieves database service instance from application state."""
  return request.app.state.db


@router.get("", response_model=list[models.Course])
def list_courses(
  request: fastapi.Request,
  q: str | None = None,
  dept: str | None = None,
  ge: str | None = None,
  min_rmp: float | None = None,
  limit: int = 100,
  offset: int = 0,
) -> list[models.Course]:
  """Retrieves courses filtered by keyword query, department, or GE code."""
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_courses(
      conn,
      q=q,
      department=dept,
      ge_category=ge,
      min_rmp=min_rmp,
      limit=limit,
      offset=offset,
    )
  finally:
    conn.close()


@router.get("/departments", response_model=list[str])
def get_departments(request: fastapi.Request) -> list[str]:
  """Lists unique academic department prefixes present in catalogue."""
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_departments(conn)
  finally:
    conn.close()


@router.get("/ge-categories", response_model=list[str])
def get_ge_categories(request: fastapi.Request) -> list[str]:
  """Lists unique General Education categories present in course catalogue."""
  db = get_db(request)
  conn = db.connect()
  try:
    return db.get_ge_categories(conn)
  finally:
    conn.close()


@router.get("/{course_id}", response_model=models.Course)
def get_course_detail(
  course_id: str, request: fastapi.Request
) -> models.Course:
  """Retrieves course details and scheduled sections by unique course code."""
  db = get_db(request)
  conn = db.connect()
  try:
    course = db.get_course(conn, course_id)
    if not course:
      raise fastapi.HTTPException(
        status_code=HTTPStatus.NOT_FOUND,
        detail=f"Course '{course_id}' was not found in the catalogue.",
      )
    return course
  finally:
    conn.close()
