"""Google Gemini as the advisor's model, over the REST API.

Streams `streamGenerateContent` as server-sent events. A reply that calls
tools is answered by echoing the model's parts back unchanged (they carry
the thought signatures Gemini requires), adding the tool results, and
asking again, for a bounded number of rounds; the last round forbids
tools so the model must answer in words.
"""

import json
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


class Gemini:
  """A Gemini model reached with an API key.

  Attributes:
    name: The model, e.g. gemini-flash-latest.
  """

  def __init__(
    self,
    api_key: str,
    name: str,
    transport: httpx.BaseTransport | None = None,
  ) -> None:
    self._key = api_key
    self.name = name
    self._transport = transport

  def unavailable(self) -> str | None:
    """Explains a missing key; otherwise None (requests surface errors)."""
    if not self._key:
      return (
        "The advisor needs a Gemini API key: set GEMINI_API_KEY "
        "(free at aistudio.google.com)."
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
    with httpx.Client(timeout=_TIMEOUT, transport=self._transport) as client:
      for round_ in range(_ROUNDS):
        if tools:
          mode = "AUTO" if round_ < _ROUNDS - 1 else "NONE"
          body["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
        parts: list[dict[str, Any]] = []
        for part in self._stream(client, {**body, "contents": contents}):
          parts.append(part)
          if part.get("text") and not part.get("thought"):
            yield part["text"]
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
          return
        contents.append({"role": "model", "parts": parts})
        contents.append(
          {
            "role": "user",
            "parts": [
              {
                "functionResponse": {
                  "name": call["name"],
                  "response": {
                    "result": execute(call["name"], call.get("args") or {})
                  },
                }
              }
              for call in calls
            ],
          }
        )

  def _stream(
    self, client: httpx.Client, body: Mapping[str, Any]
  ) -> Iterator[dict[str, Any]]:
    """Yields each content part of a streamed response, in order."""
    url = f"{_API}/{self.name}:streamGenerateContent"
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
          raise llm.ModelError(_explain(response))
        for line in response.iter_lines():
          if not line.startswith("data:"):
            continue
          chunk = json.loads(line.removeprefix("data:"))
          for candidate in chunk.get("candidates") or []:
            yield from (candidate.get("content") or {}).get("parts") or []
    except httpx.HTTPError as e:
      logging.warning("Gemini request failed: %s", e)
      raise llm.ModelError(f"Couldn't reach Gemini ({e}).") from e


def _explain(response: httpx.Response) -> str:
  """Turns a Gemini error response into a sentence for a student."""
  try:
    detail = response.json()["error"]["message"]
  except (ValueError, KeyError, TypeError):
    detail = response.text[:200]
  logging.warning("Gemini answered %d: %s", response.status_code, detail)
  if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
    return "The advisor is busy (free-tier limit). Try again in a minute."
  return f"Gemini couldn't answer ({response.status_code}: {detail})."
