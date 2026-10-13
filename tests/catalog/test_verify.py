"""Tests for build verification."""

import shutil
import sqlite3

import pytest

from server.db.ingest import _cache, _classes_api, _verify, build


def test_the_fixture_catalog_passes(catalog_path):
  report = _verify.verify(sqlite3.connect(catalog_path))
  assert report.problems == []
  assert set(report.rates) >= {"requisites resolved", "GE courses resolved"}


def test_violations_are_named(catalog_path, tmp_path):
  copy = tmp_path / "broken.db"
  shutil.copy(catalog_path, copy)
  conn = sqlite3.connect(copy)
  conn.execute("UPDATE meeting SET start_minute = 900, end_minute = 800")
  conn.execute("UPDATE offering SET units_min = 9, units_max = 1")
  problems = _verify.verify(conn).problems
  assert any("impossible times" in p for p in problems)
  assert any("unit ranges" in p for p in problems)


def test_a_failed_build_keeps_the_live_catalog(catalog_raw, tmp_path):
  # A real listing with a meeting that ends before it starts.
  raw = _cache.RawCache(tmp_path / "raw")
  shutil.copytree(catalog_raw.root, raw.root)
  key = _classes_api.listing_key(20271, "ENGV", "CSCI")
  listing = raw.read_json(key)
  listing["courses"][0]["sections"][0]["schedule"][0]["endTime"] = "07:00"
  raw.write_json(key, listing)
  live = tmp_path / "live.db"
  live.write_text("the live catalog")
  with pytest.raises(build.VerificationError, match="impossible times"):
    build.build(raw, live)
  assert live.read_text() == "the live catalog"
  assert not live.with_name("live.db.building").exists()
