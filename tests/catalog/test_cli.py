"""Tests for the catalog command's exit status."""

import pytest

from server import catalog


def test_failed_fetches_exit_nonzero(monkeypatch, capsys):
  monkeypatch.setattr(catalog, "fetch", lambda raw: 3)
  with pytest.raises(SystemExit) as exited:
    catalog.main(["catalog", "fetch"])
  assert exited.value.code == 1
  assert "3 fetches failed" in capsys.readouterr().out


def test_a_clean_fetch_returns_normally(monkeypatch):
  monkeypatch.setattr(catalog, "fetch", lambda raw: 0)
  catalog.main(["catalog", "fetch"])
