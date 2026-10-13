"""Google Gemini as the advisor's model, over the REST API.

Streams `streamGenerateContent` as server-sent events, one model turn of
the shared tool loop (`llm.run`) at a time. Later turns echo the model's
earlier parts back unchanged (they carry the thought signatures Gemini
requires) followed by the tool results under the calls' ids; a turn
without tools keeps their declarations but sets the calling mode to NONE.
Models are an
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

from server import config
from server.src.agent import llm


_API = config.GEMINI_API_URL
# A minute of silence means a stuck request; another attempt is faster.
_TIMEOUT = httpx.Timeout(
  config.GEMINI_TIMEOUT_SECONDS, connect=config.GEMINI_CONNECT_TIMEOUT_SECONDS
)
# Thought summaries stream ahead of the answer, so the student sees the
# advisor reason instead of waiting on silence.
_CONFIG = {
  "maxOutputTokens": config.GEMINI_MAX_OUTPUT_TOKENS,
  "temperature": config.GEMINI_TEMPERATURE,
  "thinkingConfig": {"includeThoughts": True},
}
_RETRY_AFTER_S = config.GEMINI_RETRY_DELAY_SECONDS
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
  ) -> Iterator[llm.Event]:
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

      def turn(
        rounds: Sequence[llm.Round], allow_tools: bool
      ) -> Iterator[str | llm.Thought | llm.Step]:
        nonlocal answered
        request = {**body, "contents": contents + _replay(rounds)}
        if tools:
          mode = "AUTO" if allow_tools else "NONE"
          request["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
        parts: list[dict[str, Any]] = []
        for part in self._attempts(client, request):
          parts.append(part)
          if not part.get("text"):
            continue
          if part.get("thought"):
            yield llm.Thought(part["text"])
          else:
            answered = True
            yield part["text"]
        yield llm.Step(
          [
            llm.Call(
              p["functionCall"]["name"], p["functionCall"].get("args") or {}
            )
            for p in parts
            if "functionCall" in p
          ],
          parts,
        )

      yield from llm.run(turn, execute)
    if not answered:
      raise llm.ModelError("The advisor came back empty; try asking again.")

  def _attempts(
    self, client: httpx.Client, body: Mapping[str, Any]
  ) -> Iterator[dict[str, Any]]:
    """Streams one request, retrying then falling back while overloaded.

    Overload, timeouts, and dropped connections that come before any part
    retry; none repeats text already shown.
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
          "Gemini %s is busy or slow; trying %s", model, plan[attempt + 1]
        )
        time.sleep(_RETRY_AFTER_S)

  def _stream(
    self, client: httpx.Client, model: str, body: Mapping[str, Any]
  ) -> Iterator[dict[str, Any]]:
    """Yields each content part of a streamed response, in order.

    A timeout or dropped connection before the first part is transient: no
    text was shown, so another attempt or model can take over. After it,
    a retry would repeat text, so the reply ends with an explanation.
    """
    url = f"{_API}/{model}:streamGenerateContent"
    started = False
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
            for part in (candidate.get("content") or {}).get("parts") or []:
              started = True
              yield part
    except httpx.TransportError as e:
      logging.warning("Gemini %s failed: %s", model, e)
      if not started:
        raise _Transient("The advisor took too long to answer.") from e
      raise llm.ModelError(
        "The advisor stopped mid-reply; try asking again."
      ) from e
    except httpx.HTTPError as e:
      logging.warning("Gemini request failed: %s", e)
      raise llm.ModelError(f"Couldn't reach Gemini ({e}).") from e


def _replay(rounds: Sequence[llm.Round]) -> list[dict[str, Any]]:
  """Each round as contents: the model's parts, then results under ids."""
  contents: list[dict[str, Any]] = []
  for r in rounds:
    contents.append({"role": "model", "parts": r.step.raw})
    calls = [p["functionCall"] for p in r.step.raw if "functionCall" in p]
    contents.append(
      {
        "role": "user",
        "parts": [
          _response(call, out)
          for call, out in zip(calls, r.results, strict=True)
        ],
      }
    )
  return contents


def _response(call: Mapping[str, Any], result: str) -> dict[str, Any]:
  """Answers one function call under its id, which Gemini 3 requires."""
  response: dict[str, Any] = {
    "name": call["name"],
    "response": {"result": result},
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
