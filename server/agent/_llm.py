"""The language-model interface the advisor talks to, and its configuration.

A model takes a system prompt, the conversation so far, the student's
message, and tools, and streams reply text. The tool loop (`run`) lives
here, apart from any wire format, so the model only translates one turn,
and tests fake a whole model behind the `Model` protocol.

Integrates Google Gemini over REST as the default model provider.
"""

import dataclasses
import json
import os
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from http import HTTPStatus
from typing import Any, Literal, Protocol

import httpx
from absl import logging

from server import config


@dataclasses.dataclass(frozen=True)
class Tool:
  """A function the model may call; `parameters` is a JSON Schema object."""

  name: str
  description: str
  parameters: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class Turn:
  """A prior message in the conversation."""

  role: Literal["user", "assistant"]
  content: str


# Runs a tool by name with the model's arguments and returns text for it.
Execute = Callable[[str, Mapping[str, Any]], str]

# Rounds of tool calls a reply may make before it must answer in words.
TOOL_ROUNDS = config.MAX_TOOL_ROUNDS


@dataclasses.dataclass(frozen=True)
class Call:
  """A tool the model asked to run."""

  name: str
  arguments: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class Step:
  """How a model turn ended: the tools it called, if any.

  Attributes:
    calls: Tools to run before the next turn; empty when it answered.
    raw: The provider's own record of the turn, echoed back verbatim on
      later turns (Gemini's carry thought signatures it requires).
  """

  calls: Sequence[Call]
  raw: Any


@dataclasses.dataclass(frozen=True)
class Thought:
  """A summary of the model's reasoning, streamed while it thinks."""

  text: str


@dataclasses.dataclass(frozen=True)
class Acting:
  """A tool the model is about to run, so the student can see it work."""

  call: Call


# What a reply streams: answer text, reasoning, and tools as they start.
Event = str | Thought | Acting


@dataclasses.dataclass(frozen=True)
class Round:
  """A finished tool round: the turn that called tools, and their results."""

  step: Step
  results: Sequence[str]


# One model turn: given the rounds so far and whether tools are allowed,
# streams reply text and thoughts, then yields the Step that ended it.
ModelTurn = Callable[[Sequence[Round], bool], Iterator[str | Thought | Step]]


def run(turn: ModelTurn, execute: Execute) -> Iterator[Event]:
  """Runs the tool loop every provider shares, streaming what happens.

  Each turn may call tools, whose results feed the next; after
  `TOOL_ROUNDS` rounds, one more turn forbids tools, so a reply always
  ends in words.
  """
  rounds: list[Round] = []
  for n in range(TOOL_ROUNDS + 1):
    step: Step | None = None
    for event in turn(rounds, n < TOOL_ROUNDS):
      if isinstance(event, Step):
        step = event
      else:
        yield event
    if step is None or not step.calls:
      return
    results: list[str] = []
    for call in step.calls:
      yield Acting(call)
      results.append(execute(call.name, call.arguments))
    rounds.append(Round(step, results))


class ModelError(Exception):
  """The model could not answer; the message is fit to show a student."""


class Model(Protocol):
  """A configured language model."""

  name: str

  def unavailable(self) -> str | None:
    """Why the model cannot answer right now, or None when it can."""
    ...

  def reply(
    self,
    system: str,
    history: Sequence[Turn],
    message: str,
    tools: Sequence[Tool],
    execute: Execute,
  ) -> Iterator[Event]:
    """Streams the reply, its reasoning, and each tool as it runs.

    Raises:
      ModelError: The provider failed; its message explains why.
    """
    ...


# =============================================================================
# Google Gemini Provider Implementation
# =============================================================================

_API = config.GEMINI_API_URL
_TIMEOUT = httpx.Timeout(
  config.GEMINI_TIMEOUT_SECONDS, connect=config.GEMINI_CONNECT_TIMEOUT_SECONDS
)
_CONFIG = {
  "maxOutputTokens": config.GEMINI_MAX_OUTPUT_TOKENS,
  "temperature": config.GEMINI_TEMPERATURE,
  "thinkingConfig": {"includeThoughts": True},
}
_RETRY_AFTER_S = config.GEMINI_RETRY_DELAY_SECONDS
_TRANSIENT = frozenset(
  {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}
)


class _Transient(ModelError):
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
    history: Sequence[Turn],
    message: str,
    tools: Sequence[Tool],
    execute: Execute,
  ) -> Iterator[Event]:
    """Streams the reply; see Model.reply."""
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
        rounds: Sequence[Round], allow_tools: bool
      ) -> Iterator[str | Thought | Step]:
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
            yield Thought(part["text"])
          else:
            answered = True
            yield part["text"]
        yield Step(
          [
            Call(p["functionCall"]["name"], p["functionCall"].get("args") or {})
            for p in parts
            if "functionCall" in p
          ],
          parts,
        )

      yield from run(turn, execute)
    if not answered:
      raise ModelError("The advisor came back empty; try asking again.")

  def _attempts(
    self, client: httpx.Client, body: Mapping[str, Any]
  ) -> Iterator[dict[str, Any]]:
    """Streams one request, retrying then falling back while overloaded."""
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
    """Yields each content part of a streamed response, in order."""
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
            _Transient if response.status_code in _TRANSIENT else ModelError
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
      raise ModelError(
        "The advisor stopped mid-reply; try asking again."
      ) from e
    except httpx.HTTPError as e:
      logging.warning("Gemini request failed: %s", e)
      raise ModelError(f"Couldn't reach Gemini ({e}).") from e


def _replay(rounds: Sequence[Round]) -> list[dict[str, Any]]:
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


def from_env(env: Mapping[str, str] = os.environ) -> Model:
  """Builds the model `env` configures."""
  models_list = [m.strip() for m in env.get("GEMINI_MODELS", "").split(",")]
  return Gemini(env.get("GEMINI_API_KEY", ""), [m for m in models_list if m])


__all__ = [
  "Acting",
  "Call",
  "Event",
  "Execute",
  "Gemini",
  "Model",
  "ModelError",
  "ModelTurn",
  "Round",
  "Step",
  "TOOL_ROUNDS",
  "Thought",
  "Tool",
  "Turn",
  "from_env",
  "run",
]
