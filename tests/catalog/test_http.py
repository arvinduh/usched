"""Tests for the shared retry policy."""

import httpx
import pytest

from server.src.catalog import http


def test_rate_limits_wait_as_long_as_the_server_asks(monkeypatch):
  waits: list[float] = []
  monkeypatch.setattr(http.time, "sleep", waits.append)
  replies = iter(
    [
      httpx.Response(429, headers={"Retry-After": "7"}),
      httpx.Response(429),
      httpx.Response(200, text="ok"),
    ]
  )
  transport = httpx.MockTransport(lambda _: next(replies))
  with httpx.Client(transport=transport) as client:
    assert http.request(client, "GET", "https://x.test").text == "ok"
  assert waits == [7.0, 2.0]


def test_client_errors_are_not_retried(monkeypatch):
  monkeypatch.setattr(http.time, "sleep", pytest.fail)
  transport = httpx.MockTransport(lambda _: httpx.Response(404))
  with httpx.Client(transport=transport) as client:
    with pytest.raises(httpx.HTTPStatusError):
      http.request(client, "GET", "https://x.test")
