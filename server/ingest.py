"""CLI executable host for live USC timetable and degree curriculum ingestion.

This binary provides terminal command-line interface arguments, interactive
status spinners, and minimalist completion reporting, delegating orchestration
to the granular `pipeline` library module.
"""

from collections.abc import Sequence

from absl import app, flags, logging
from rich.console import Console
from rich.progress import (
  BarColumn,
  MofNCompleteColumn,
  Progress,
  TaskID,
  TextColumn,
  TimeElapsedColumn,
)

from server.src.ingest import client, pipeline


FLAGS = flags.FLAGS

flags.DEFINE_string(
  "term", client.DEFAULT_TERM, "Target academic semester code."
)
flags.DEFINE_boolean(
  "reset",
  False,
  "If True, wipes and reinitializes database schema from scratch.",
)
flags.DEFINE_string(
  "departments",
  "",
  "Comma-separated department codes (e.g. DSO,CSCI). Ingests all if empty.",
)
flags.DEFINE_boolean(
  "skip_departments",
  False,
  "If True, skips fetching department offerings and section synchronization.",
)
flags.DEFINE_boolean(
  "skip_faculty",
  False,
  "If True, skips RateMyProfessors faculty enrichment.",
)
flags.DEFINE_boolean(
  "skip_degrees",
  False,
  "If True, skips catalogue degree curriculum scraping.",
)
flags.DEFINE_boolean(
  "refresh_degrees",
  False,
  "If True, re-scrapes and overwrites existing degree curriculum in db.",
)


def main(argv: Sequence[str]) -> None:
  """CLI process host running ingestion with minimalist progress reporting."""
  del argv
  is_verbose = FLAGS.verbosity > 0
  console = Console(legacy_windows=False)

  depts_arg = [
    d.strip().upper() for d in FLAGS.departments.split(",") if d.strip()
  ] or None

  if is_verbose:
    logging.set_verbosity(logging.INFO)
    result = pipeline.run_pipeline(
      term=FLAGS.term,
      reset=FLAGS.reset,
      departments=depts_arg,
      skip_departments=FLAGS.skip_departments,
      skip_faculty=FLAGS.skip_faculty,
      skip_degrees=FLAGS.skip_degrees,
      refresh_degrees=FLAGS.refresh_degrees,
    )
  else:
    # Clean TUI mode: suppress raw log noise from disrupting terminal
    logging.set_verbosity(logging.ERROR)

    progress = Progress(
      TextColumn("[cyan]{task.description:<42}"),
      BarColumn(bar_width=32),
      MofNCompleteColumn(),
      TimeElapsedColumn(),
      console=console,
    )

    active_task: TaskID | None = None

    def on_phase_start(description: str, total: int | None = None) -> None:
      nonlocal active_task
      active_task = progress.add_task(description, total=total)

    def on_advance(step: int = 1) -> None:
      if active_task is not None:
        progress.advance(active_task, step)

    def on_phase_end(summary: str) -> None:
      nonlocal active_task
      del summary  # Description remains clean without mutating to loud green.
      if active_task is not None:
        task = progress.tasks[active_task]
        total = task.total or 1
        progress.update(active_task, completed=total)
        active_task = None

    with progress:
      result = pipeline.run_pipeline(
        term=FLAGS.term,
        reset=FLAGS.reset,
        departments=depts_arg,
        skip_departments=FLAGS.skip_departments,
        skip_faculty=FLAGS.skip_faculty,
        skip_degrees=FLAGS.skip_degrees,
        refresh_degrees=FLAGS.refresh_degrees,
        on_phase_start=on_phase_start,
        on_advance=on_advance,
        on_phase_end=on_phase_end,
      )

  console.print()
  console.print(
    f"[bold green][OK] Ingestion complete:[/] "
    f"[bold cyan]{result.courses_count:,}[/] courses, "
    f"[bold cyan]{result.sections_count:,}[/] sections, "
    f"[bold cyan]{result.instructors_count:,}[/] instructors, "
    f"[bold cyan]{result.degrees_count}[/] degrees "
    f"in [yellow]usched.db[/]."
  )

  if result.failed_departments or result.failed_degrees:
    console.print()
    console.print(
      "[bold yellow][!] Ingestion completed with non-fatal errors:[/]"
    )
    if result.failed_departments:
      count = len(result.failed_departments)
      depts = ", ".join(result.failed_departments)
      console.print(f"  [yellow]- Failed departments ({count}):[/] {depts}")
    if result.failed_degrees:
      count = len(result.failed_degrees)
      degs = ", ".join(result.failed_degrees)
      console.print(f"  [yellow]- Failed degree programs ({count}):[/] {degs}")

    console.print()
    console.print("[dim]To retry failed items, run:[/]")
    if result.failed_departments:
      retry_depts = ",".join(result.failed_departments)
      console.print(
        f"  [bold green]uv run ingest --departments={retry_depts}[/]"
      )
    elif result.failed_degrees:
      console.print(
        "  [bold green]uv run ingest --skip_departments --skip_faculty[/]"
      )


def cli_main() -> None:
  """Console script entrypoint wrapping absl process runner."""
  app.run(main)


if __name__ == "__main__":
  cli_main()
