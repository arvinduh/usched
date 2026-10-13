"""Publishes a built catalog where deployments download it from.

Uploads the database to a GitHub release of the current repository (the
`gh` CLI decides which, from the checkout's remote), creating the release
on first use. The database never enters a commit; the Docker image fetches
it from the printed URL at build time.
"""

import contextlib
import pathlib
import shutil
import sqlite3
import subprocess

from server.src.catalog import verify


RELEASE = "catalog"


class PublishError(Exception):
  """The catalog could not be published; the message says why."""


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["gh", *args], check=check, capture_output=True, text=True
  )


def publish(db: pathlib.Path) -> str:
  """Verifies and uploads `db`; returns the URL deployments download.

  Raises:
    PublishError: gh is missing, there is no catalog, or it fails
      verification.
  """
  if shutil.which("gh") is None:
    raise PublishError(
      "Install the GitHub CLI (https://cli.github.com), then gh auth login."
    )
  if not db.is_file():
    raise PublishError(f"No catalog at {db}; build it first.")
  with contextlib.closing(sqlite3.connect(db)) as conn:
    problems = verify.verify(conn).problems
  if problems:
    raise PublishError(
      f"The catalog failed verification: {'; '.join(problems)}"
    )
  if _gh("release", "view", RELEASE, check=False).returncode != 0:
    _gh(
      "release",
      "create",
      RELEASE,
      "--title",
      "Catalog database",
      "--notes",
      "Built and uploaded by `npm run catalog -- publish`; deployments "
      "download catalog.db from here.",
      "--latest=false",
    )
  _gh("release", "upload", RELEASE, str(db), "--clobber")
  repo = _gh("repo", "view", "--json", "url", "--jq", ".url").stdout.strip()
  return f"{repo}/releases/download/{RELEASE}/{db.name}"
