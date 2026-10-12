"""Prints the API's OpenAPI schema, from which the client's types are made.

Usage: uv run python -m server.openapi > client/.openapi.json
"""

import json
import sys

from server.main import app


def main() -> None:
  """Writes the schema to stdout."""
  json.dump(app.openapi(), sys.stdout, indent=1)


if __name__ == "__main__":
  main()
