"""Tests how the server hands out the built client."""

import pathlib

from fastapi import testclient
from starlette import applications

from server import main


def test_assets_cache_for_good_and_the_page_rechecks(tmp_path: pathlib.Path):
  (tmp_path / "assets").mkdir()
  (tmp_path / "assets" / "index-abc123.js").write_text("export {};")
  (tmp_path / "index.html").write_text("<!doctype html>")
  app = applications.Starlette()
  app.mount("/", main._Client(directory=tmp_path, html=True))
  client = testclient.TestClient(app)

  asset = client.get("/assets/index-abc123.js")
  page = client.get("/")

  assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
  assert page.headers["cache-control"] == "no-cache"
