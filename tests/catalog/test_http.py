"""Tests for the shared retry policy, against a real local HTTP server."""

import threading
from collections.abc import Iterator
from http import server as http_server

import httpx
import pytest

from server.db.ingest import _http


class _Server(http_server.ThreadingHTTPServer):
  """Answers GETs with a scripted sequence of statuses, counting requests."""

  def __init__(self, statuses: list[int]) -> None:
    self.statuses = statuses
    self.requests = 0
    super().__init__(("127.0.0.1", 0), _Handler)


class _Handler(http_server.BaseHTTPRequestHandler):
  server: _Server

  def do_GET(self) -> None:  # noqa: N802 (the stdlib's handler name)
    status = self.server.statuses[
      min(self.server.requests, len(self.server.statuses) - 1)
    ]
    self.server.requests += 1
    self.send_response(status)
    if status == 429:
      self.send_header("Retry-After", "0")
    self.end_headers()
    self.wfile.write(b"ok" if status == 200 else b"no")

  def log_message(self, format: str, *args: object) -> None:
    del format, args


def _serve(statuses: list[int]) -> Iterator[_Server]:
  server = _Server(statuses)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  yield server
  server.shutdown()


@pytest.fixture
def busy_then_ok() -> Iterator[_Server]:
  yield from _serve([429, 200])


@pytest.fixture
def missing() -> Iterator[_Server]:
  yield from _serve([404])


def _url(server: _Server) -> str:
  return f"http://127.0.0.1:{server.server_address[1]}/"


def test_rate_limits_are_retried(busy_then_ok):
  with httpx.Client() as client:
    response = _http.request(client, "GET", _url(busy_then_ok))
  assert response.text == "ok"
  assert busy_then_ok.requests == 2


def test_client_errors_are_not_retried(missing):
  with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
    _http.request(client, "GET", _url(missing))
  assert missing.requests == 1
