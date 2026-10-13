"""Google Gemini as the advisor's model, over the REST API.

Streams `streamGenerateContent` as server-sent events. A reply that calls
tools is answered by echoing the model's parts back unchanged (they carry
the thought signatures Gemini requires), adding the tool results under the
calls' ids, and asking again, for a bounded number of rounds; the last
round forbids tools so the model must answer in words. Models are an
ordered list: while one is overloaded or out of free-tier quota, a request
is retried once and then sent to the next, so a busy moment costs a pause
rather than an error (each model has its own quota).
"""

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from http import HTTPStatus
from typing import Any

import httpx
from absl import logging

from server.src.agent import llm


_API = "https://generativelanguage.googleapis.com/v1beta/models"
_ROUNDS = 3  # Tool rounds before the model must answer.
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_CONFIG = {"maxOutputTokens": 2048, "temperature": 0.4}
_RETRY_AFTER_S = 1.5
# Overloaded (503) and rate-limited (429) requests are worth another try.
_TRANSIENT = frozenset(
  {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}
)


class _Transient(llm.ModelError):
  """A failure another attempt or model may not hit."""


class Gemini:
  """A Gemini model reached with an API key.

  Attributes:
    name: The preferred model, for logs.
  """

  def __init__(self, api_key: str, models: Sequence[str]) -> None:
    self._key = api_key
    self._models = list(models)
    self.name = ", ".join(self._models) or "Gemini (no model set)"

  def unavailable(self) -> str | None:
    """Explains missing configuration; otherwise None."""
    if not self._key:
      return (
        "The advisor needs a Gemini API key: set GEMINI_API_KEY "
        "(free at aistudio.google.com)."
      )
    if not self._models:
      return (
        "The advisor needs a model: set GEMINI_MODELS to one or more model "
        "names, comma-separated (see .env.example)."
      )
    return None

  def reply(
    self,
    system: str,
    history: Sequence[llm.Turn],
    message: str,
    tools: Sequence[llm.Tool],
    execute: llm.Execute,
  ) -> Iterator[str]:
    """Streams the reply; see llm.Model.reply."""
    contents: list[dict[str, Any]] = [
      {
        "role": "model" if turn.role == "assistant" else "user",
        "parts": [{"text": turn.content}],
      }
      for turn in history
    ]
    contents.append({"role": "user", "parts": [{"text": message}]})
    body: dict[str, Any] = {
      "systemInstruction": {"parts": [{"text": system}]},
      "generationConfig": _CONFIG,
    }
    if tools:
      body["tools"] = [
        {
          "functionDeclarations": [
            {
              "name": t.name,
              "description": t.description,
              "parametersJsonSchema": t.parameters,
            }
            for t in tools
          ]
        }
      ]
    answered = False
    with httpx.Client(timeout=_TIMEOUT) as client:
      for round_ in range(_ROUNDS):
        if tools:
          mode = "AUTO" if round_ < _ROUNDS - 1 else "NONE"
          body["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
        parts: list[dict[str, Any]] = []
        for part in self._attempts(client, {**body, "contents": contents}):
          parts.append(part)
          if part.get("text") and not part.get("thought"):
            answered = True
            yield part["text"]
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
          break
        contents.append({"role": "model", "parts": parts})
        contents.append(
          {
            "role": "user",
            "parts": [_result(call, execute) for call in calls],
          }
        )
    if not answered:
      raise llm.ModelError("The advisor came back empty; try asking again.")

  def _attempts(
    self, client: httpx.Client, body: Mapping[str, Any]
  ) -> Iterator[dict[str, Any]]:
    """Streams one request, retrying then falling back while overloaded.

    Overload is reported before any part arrives, so a retry never repeats
    text already shown.
    """
    plan = [self._models[0], *self._models]
    for attempt, model in enumerate(plan):
      try:
        yield from self._stream(client, model, body)
        return
      except _Transient:
        if attempt == len(plan) - 1:
          raise
        logging.warning(
          "Gemini %s is busy; trying %s", model, plan[attempt + 1]
        )
        time.sleep(_RETRY_AFTER_S)

  def _stream(
    self, client: httpx.Client, model: str, body: Mapping[str, Any]
  ) -> Iterator[dict[str, Any]]:
    """Yields each content part of a streamed response, in order."""
    url = f"{_API}/{model}:streamGenerateContent"
    try:
      with client.stream(
        "POST",
        url,
        params={"alt": "sse"},
        headers={"x-goog-api-key": self._key},
        json=body,
      ) as response:
        if response.status_code != HTTPStatus.OK:
          response.read()
          error = (
            _Transient if response.status_code in _TRANSIENT else llm.ModelError
          )
          raise error(_explain(response))
        for line in response.iter_lines():
          if not line.startswith("data:"):
            continue
          chunk = json.loads(line.removeprefix("data:"))
          for candidate in chunk.get("candidates") or []:
            yield from (candidate.get("content") or {}).get("parts") or []
    except httpx.HTTPError as e:
      logging.warning("Gemini request failed: %s", e)
      raise llm.ModelError(f"Couldn't reach Gemini ({e}).") from e


def _result(call: Mapping[str, Any], execute: llm.Execute) -> dict[str, Any]:
  """Runs one function call and answers it under the call's id."""
  response: dict[str, Any] = {
    "name": call["name"],
    "response": {"result": execute(call["name"], call.get("args") or {})},
  }
  if "id" in call:
    response["id"] = call["id"]
  return {"functionResponse": response}


def _explain(response: httpx.Response) -> str:
  """Turns a Gemini error response into a sentence for a student."""
  try:
    detail = response.json()["error"]["message"]
  except (ValueError, KeyError, TypeError):
    detail = response.text[:200]
  logging.warning("Gemini answered %d: %s", response.status_code, detail)
  if response.status_code in _TRANSIENT:
    return "The advisor is busy right now. Try again in a minute."
  return f"Gemini couldn't answer ({response.status_code}: {detail})."
