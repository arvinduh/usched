"""Fixtures for the advisor's tests: a connection to the fixture catalog."""

import sqlite3
from collections.abc import Iterator

import pytest

from server.db import store


@pytest.fixture(scope="module")
def conn(catalog_path) -> Iterator[sqlite3.Connection]:
  """The fixture catalog, opened once per test module."""
  conn = store.CatalogDb(catalog_path).connect()
  yield conn
  conn.close()
