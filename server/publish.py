"""Uploads the built catalog to the GitHub release the Docker image downloads.

    npm run publish:catalog

Verifies server/data/catalog.db, creates this repo's "catalog" release on
first use, and replaces its catalog.db asset. Needs the GitHub CLI (`gh`)
signed in with push access. Redeploy afterwards to serve the new data.
"""

import contextlib
import shutil
import sqlite3
import subprocess
import sys

from server.src.catalog import build, verify


RELEASE = "catalog"


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["gh", *args], check=check, capture_output=True, text=True
  )


def main() -> None:
  """Verifies the local catalog and uploads it."""
  if shutil.which("gh") is None:
    sys.exit(
      "Install the GitHub CLI (https://cli.github.com) and run gh auth login."
    )
  db = build.DEFAULT_DB
  if not db.is_file():
    sys.exit(f"No catalog at {db}; build it with `npm run catalog` first.")
  with contextlib.closing(sqlite3.connect(db)) as conn:
    problems = verify.verify(conn).problems
  if problems:
    sys.exit(f"The catalog failed verification: {'; '.join(problems)}")
  if _gh("release", "view", RELEASE, check=False).returncode != 0:
    _gh(
      "release",
      "create",
      RELEASE,
      "--title",
      "Catalog database",
      "--notes",
      "Built by `npm run catalog`, uploaded by `npm run publish:catalog`; "
      "the Docker image downloads catalog.db from here.",
      "--latest=false",
    )
  _gh("release", "upload", RELEASE, str(db), "--clobber")
  size = db.stat().st_size / 1e6
  print(f"Uploaded catalog.db ({size:.1f} MB) to the {RELEASE} release.")
  print("Redeploy (Render: Manual Deploy > Deploy latest commit) to serve it.")


if __name__ == "__main__":
  main()
