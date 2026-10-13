"""Shared HTTP plumbing for catalog fetchers: one client, bounded retries.

Sources build their requests; this module owns transport concerns only:
browser-like headers, connection pooling, and retrying transient failures
with backoff. Permanent failures (4xx) are not retried.
"""

import time
from http import HTTPStatus
from typing import Any

import httpx
from absl import logging


_ATTEMPTS = 5
_BACKOFF_S = 1.0
_MAX_WAIT_S = 60.0
_USER_AGENT = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def client(**kwargs: Any) -> httpx.Client:
  """Creates a pooled client with browser-like defaults.

  Args:
    **kwargs: Overrides passed to `httpx.Client` (cookies, headers, ...).
  """
  options: dict[str, Any] = {
    # The largest program listings take over 30 s to generate server-side.
    "timeout": httpx.Timeout(120.0, connect=10.0),
    "headers": {"User-Agent": _USER_AGENT, "Accept": "application/json"},
    "limits": httpx.Limits(max_connections=16, max_keepalive_connections=16),
    "follow_redirects": True,
  }
  options.update(kwargs)
  return httpx.Client(**options)


def _retryable(status: int) -> bool:
  return status == HTTPStatus.TOO_MANY_REQUESTS or status >= 500


def _wait_s(response: httpx.Response | None, attempt: int) -> float:
  """Honors a numeric Retry-After, else backs off exponentially."""
  backoff = _BACKOFF_S * 2 ** (attempt - 1)
  after = response.headers.get("Retry-After", "") if response else ""
  if after.isdigit():
    return min(max(float(after), backoff), _MAX_WAIT_S)
  return backoff


def request(
  http: httpx.Client, method: str, url: str, **kwargs: Any
) -> httpx.Response:
  """Sends a request, retrying network errors, 429s, and 5xx responses.

  Raises:
    httpx.HTTPError: The request failed on every attempt, or the server
      answered with a non-retryable error status.
  """
  for attempt in range(1, _ATTEMPTS + 1):
    response = None
    try:
      response = http.request(method, url, **kwargs)
    except httpx.TransportError as e:
      if attempt == _ATTEMPTS:
        raise
      logging.warning("Retrying %s after %s (attempt %d)", url, e, attempt)
    else:
      if not _retryable(response.status_code) or attempt == _ATTEMPTS:
        response.raise_for_status()
        return response
      logging.warning(
        "Retrying %s after HTTP %d (attempt %d)",
        url,
        response.status_code,
        attempt,
      )
    time.sleep(_wait_s(response, attempt))
  raise AssertionError("unreachable: the final attempt returns or raises")


__all__ = [
  "client",
  "request",
]
