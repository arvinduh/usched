"""Shim delegating to server.db.ingest.cli:cli_main."""

from server.db.ingest import cli


if __name__ == "__main__":
  cli.cli_main()
