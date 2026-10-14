"""Catalog endpoints: terms, courses, sections, programs, and GE policy.

Course and section routes are scoped by term so the client can plan any
fetched semester. Every route reads catalog.db through store; when the
catalog has not been built they answer 503 with the command that builds it.
"""

import sqlite3
from http import HTTPStatus
from typing import Annotated

import fastapi

from server.db import models, store
from server.engine import audits


router = fastapi.APIRouter(prefix="/api", tags=["catalog"])
_STATIC_CACHE_CONTROL = "public, max-age=3600, stale-while-revalidate=86400"


def _conn(request: fastapi.Request) -> sqlite3.Connection:
  conn: sqlite3.Connection | None = getattr(request.app.state, "db_conn", None)
  if conn is not None:
    return conn
  db: store.CatalogDb | None = getattr(request.app.state, "catalog", None)
  if db is not None:
    try:
      conn = db.connect()
      request.app.state.db_conn = conn
      return conn
    except FileNotFoundError as e:
      raise fastapi.HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, str(e)) from e
  try:
    conn = store.get_connection()
    request.app.state.db_conn = conn
    return conn
  except FileNotFoundError as e:
    raise fastapi.HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, str(e)) from e


Conn = Annotated[sqlite3.Connection, fastapi.Depends(_conn)]


def _found[T](item: T | None, what: str) -> T:
  if item is None:
    raise fastapi.HTTPException(HTTPStatus.NOT_FOUND, f"No {what}")
  return item


@router.get("/terms")
def list_terms(conn: Conn, response: fastapi.Response) -> list[models.Term]:
  """Lists every term, newest first; plan for the first with courses."""
  response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
  return store.terms(conn)


@router.get("/terms/{term}/courses")
def search_courses(
  conn: Conn,
  term: int,
  q: str | None = None,
  ge: str | None = None,
  min_rating: Annotated[float | None, fastapi.Query(ge=0, le=5)] = None,
  limit: Annotated[int, fastapi.Query(ge=1, le=500)] = 100,
  offset: Annotated[int, fastapi.Query(ge=0)] = 0,
  codes: Annotated[
    str | None,
    fastapi.Query(
      description=(
        "Comma-separated codes to load instead of searching; codes not "
        "offered this term are skipped."
      )
    ),
  ] = None,
) -> list[models.Course]:
  """Searches a term's courses by text, GE category, and instructor rating.

  With `codes`, loads exactly those courses in one request instead.
  """
  if codes is not None:
    wanted = [c for c in (s.strip() for s in codes.split(",")) if c]
    return store.courses(conn, term, wanted[:limit])
  return store.search_courses(
    conn, term, q, ge=ge, min_rating=min_rating, limit=limit, offset=offset
  )


@router.get("/terms/{term}/courses/{code}")
def get_course(conn: Conn, term: int, code: str) -> models.Course:
  """Returns one course as offered in a term."""
  return _found(store.course(conn, term, code), f"{code} in {term}")


@router.get("/terms/{term}/sections")
def get_sections(conn: Conn, term: int, ids: str) -> list[models.Section]:
  """Returns a term's sections by comma-separated section numbers."""
  wanted = [i for i in (s.strip() for s in ids.split(",")) if i]
  return store.sections(conn, term, wanted)


@router.get("/courses")
def lookup_courses(
  conn: Conn, codes: str, response: fastapi.Response
) -> list[models.KnownCourse]:
  """Recognizes comma-separated course codes written any way.

  Answers with the catalog's spelling and title for each known course, in
  request order; codes that name no course are left out.
  """
  response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
  wanted = [c for c in (s.strip() for s in codes.split(",")) if c]
  return store.known_courses(conn, wanted[:200])


@router.get("/programs")
def list_programs(
  conn: Conn, response: fastapi.Response, kind: str | None = None
) -> list[models.ProgramSummary]:
  """Lists the current catalogue's programs, optionally of one kind."""
  response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
  return store.programs(conn, kind)


@router.get("/programs/{program_id}")
def get_program(
  conn: Conn, program_id: str, response: fastapi.Response
) -> models.Program:
  """Returns a program with its requirement tree."""
  result = _found(store.program(conn, program_id), f"program {program_id}")
  response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
  return result


@router.get("/ge-categories")
def list_ge_categories(
  conn: Conn, response: fastapi.Response
) -> list[models.GeCategory]:
  """Lists GE categories and how many courses each needs."""
  response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
  return store.ge_categories(conn)


@router.get("/ap-exams")
def list_ap_exams(
  conn: Conn, response: fastapi.Response
) -> list[models.ApExam]:
  """Lists AP exams with the GE categories and courses they cover."""
  response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
  return store.ap_exams(conn)


@router.post("/ge-audit")
def audit_ge(conn: Conn, body: models.GeAuditRequest) -> models.GeAudit:
  """Shows how completed courses and AP exams fill each GE category."""
  return audits.general_education(
    conn, body.completed, body.ap_credits, body.ge_counted
  )


@router.post("/terms/{term}/programs/{program_id}/audit")
def audit_program(
  conn: Conn, term: int, program_id: str, body: models.ProgramAuditRequest
) -> models.ProgramAudit:
  """Audits a program; prerequisites follow the planning term's listings."""
  program = _found(store.program(conn, program_id), f"program {program_id}")
  return audits.program(
    conn, term, program, body.completed, body.ap_credits, body.ge_counted
  )
