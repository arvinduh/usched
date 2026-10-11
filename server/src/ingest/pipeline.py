"""Master ingestion pipeline for live timetable and degree roadmap storage.

This module coordinates live USC Schedule of Classes retrieval, faculty
RateMyProfessors enrichment, and catalogue degree roadmap extraction into the
SQLite SSOT database. It functions purely as a library without UI/CLI concerns.
"""

import concurrent.futures
import dataclasses
from collections.abc import Callable, Sequence

import httpx
from absl import logging

from server.src.data import database, models
from server.src.ingest import client


@dataclasses.dataclass(frozen=True)
class PipelineResult:
  """Execution summary containing aggregate counts of synchronized records."""

  courses_count: int
  sections_count: int
  instructors_count: int
  degrees_count: int
  failed_departments: tuple[str, ...] = ()
  failed_degrees: tuple[str, ...] = ()


def run_pipeline(
  target_db: database.Database | None = None,
  term: str = client.DEFAULT_TERM,
  reset: bool = False,
  departments: Sequence[str] | None = None,
  skip_departments: bool = False,
  skip_faculty: bool = False,
  skip_degrees: bool = False,
  refresh_degrees: bool = False,
  on_phase_start: Callable[[str, int | None], None] | None = None,
  on_advance: Callable[[int], None] | None = None,
  on_phase_end: Callable[[str], None] | None = None,
) -> PipelineResult:
  """Executes the end-to-end ingestion and atomic sync pipeline."""
  db_inst = target_db or database.Database()
  if reset:
    logging.info("Resetting database schema at %s...", db_inst.db_path)
    if db_inst.db_path.exists():
      db_inst.db_path.unlink()

  db_inst.init()
  conn = db_inst.connect()

  headers = {
    "User-Agent": (
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    ),
    "Accept": "application/json",
  }
  limits = httpx.Limits(max_connections=20, max_keepalive_connections=15)

  failed_departments: list[str] = []
  failed_degrees: list[str] = []

  with httpx.Client(
    timeout=30.0, headers=headers, limits=limits
  ) as shared_client:
    if not skip_departments:
      if departments:
        depts_to_scrape = [d.upper().strip() for d in departments if d.strip()]
      else:
        logging.info("Discovering all active USC departments...")
        depts_to_scrape = client.fetch_all_departments(
          term=term, client=shared_client
        )
      total_depts = len(depts_to_scrape)

      if on_phase_start:
        on_phase_start("Fetching department offerings...", total_depts)

      all_courses: list[models.Course] = []
      all_sections: list[models.Section] = []
      instructors_map: dict[str, models.Instructor] = {}

      def process_department(
        dept_code: str,
      ) -> tuple[str, list[models.Course], str | None]:
        try:
          courses = list(
            client.fetch_department_courses(
              dept_code, term=term, client=shared_client
            )
          )
          return (dept_code, courses, None)
        except Exception as exc:
          logging.warning("Error fetching %s: %s", dept_code, exc)
          return (dept_code, [], str(exc))

      with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_dept = {
          executor.submit(process_department, d): d for d in depts_to_scrape
        }
        for future in concurrent.futures.as_completed(future_to_dept):
          dept_code, dept_res, err = future.result()
          if on_advance:
            on_advance(1)
          if err is not None:
            failed_departments.append(dept_code)
          for c in dept_res:
            all_courses.append(c)
            for s in c.sections:
              all_sections.append(s)
              if s.instructor:
                instructors_map[s.instructor.id] = s.instructor

      if on_phase_end:
        on_phase_end(f"Fetched {total_depts} department offerings.")

      if on_phase_start:
        on_phase_start("Synchronizing database tables...", 1)

      if all_courses:
        db_inst.upsert_courses(conn, all_courses)
      if instructors_map:
        db_inst.upsert_instructors(conn, list(instructors_map.values()))
      if all_sections:
        db_inst.sync_term_sections(
          conn,
          term,
          all_sections,
          department_filter=depts_to_scrape if departments else None,
        )

      if on_advance:
        on_advance(1)
      if on_phase_end:
        on_phase_end("Synchronized database tables.")

    # Incremental faculty enrichment: query uncached instructors
    if not skip_faculty:
      unenriched = db_inst.get_unenriched_instructors(conn)
      if unenriched:
        if on_phase_start:
          on_phase_start("Querying RateMyProfessors...", len(unenriched))
        enriched: list[models.Instructor] = []

        def enrich_one(inst: models.Instructor) -> models.Instructor | None:
          return client.fetch_instructor_rmp(inst.name, client=shared_client)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as rmp_exec:
          for res in rmp_exec.map(enrich_one, unenriched):
            if on_advance:
              on_advance(1)
            if res is not None:
              enriched.append(res)

        if enriched:
          db_inst.upsert_instructors(conn, enriched)
        actual_enriched = sum(1 for i in enriched if i.rmp_rating is not None)
        if on_phase_end:
          msg = (
            f"Added {actual_enriched} faculty profiles "
            f"({len(enriched)} checked)."
          )
          on_phase_end(msg)
      elif on_phase_end:
        on_phase_end("All faculty profiles already cached.")

    # Incremental degree scraping: scrape all uncached catalogue programs
    if not skip_degrees:
      existing_degree_ids = db_inst.get_existing_degree_ids(conn)
      discovered, cookies, user_agent = client.discover_degree_programs(
        catoid=client.DEFAULT_CATOID
      )

      uncached_degrees = (
        discovered
        if refresh_degrees
        else [d for d in discovered if d[0] not in existing_degree_ids]
      )

      if uncached_degrees:
        if on_phase_start:
          on_phase_start("Scraping degree curriculum...", len(uncached_degrees))

        new_degrees: list[models.DegreeProgram] = []

        with httpx.Client(
          cookies=cookies,
          headers={"User-Agent": user_agent},
          timeout=20.0,
          follow_redirects=True,
        ) as cat_client:

          def fetch_degree(
            deg_item: tuple[str, str, str],
          ) -> tuple[str, models.DegreeProgram | None, str | None]:
            slug, title, poid = deg_item
            try:
              deg_obj = client.scrape_degree_program(
                catoid=client.DEFAULT_CATOID,
                poid=poid,
                degree_id=slug,
                client=cat_client,
              )
              return (slug, deg_obj, None)
            except Exception as exc:
              logging.warning("Failed scraping %s: %s", title, exc)
              return (slug, None, str(exc))

          with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for slug, deg_obj, err in pool.map(fetch_degree, uncached_degrees):
              if on_advance:
                on_advance(1)
              if deg_obj is not None:
                new_degrees.append(deg_obj)
              if err is not None:
                failed_degrees.append(slug)

        if new_degrees:
          db_inst.upsert_degrees(conn, new_degrees)
        if on_phase_end:
          on_phase_end(f"Scraped {len(new_degrees)} degree roadmaps.")
      elif on_phase_end:
        on_phase_end("All target degree programs already cached.")

  courses_count = int(
    conn.execute("SELECT count(*) FROM courses").fetchone()[0]
  )
  sections_count = int(
    conn.execute(
      "SELECT count(*) FROM sections WHERE term = ?", (term,)
    ).fetchone()[0]
  )
  instructors_count = int(
    conn.execute("SELECT count(*) FROM instructors").fetchone()[0]
  )
  degrees_count = int(
    conn.execute("SELECT count(*) FROM degrees").fetchone()[0]
  )
  conn.close()
  logging.info("Ingestion complete.")

  return PipelineResult(
    courses_count=courses_count,
    sections_count=sections_count,
    instructors_count=instructors_count,
    degrees_count=degrees_count,
    failed_departments=tuple(failed_departments),
    failed_degrees=tuple(failed_degrees),
  )
