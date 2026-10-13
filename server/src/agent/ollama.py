"""A local Ollama daemon as the advisor's model, for development.

Streams `/api/chat`, one model turn of the shared tool loop (`llm.run`) at
a time, so a direct answer appears token by token. Later turns replay the
model's tool calls and their results; a turn without tools omits them.
"""

import json
from collections.abc import Iterator, Mapping, Sequence
from http import HTTPStatus
from typing import Any

import httpx
from absl import logging

from server.src.agent import llm


# Reasoning models emit hidden "thinking" tokens before any answer; on
# qwen3.5:4b that turns a 3 s reply into 2 minutes of silence.
_THINK = False
# Keeps the model resident between messages so a reply never waits on a
# reload, and caps reply length so a runaway answer cannot take minutes.
_KEEP_ALIVE = "30m"
_OPTIONS = {"num_predict": 400}
_TIMEOUT = httpx.Timeout(90.0, connect=10.0)


class Ollama:
  """A model served by a local Ollama daemon.

  Attributes:
    name: The model tag, e.g. qwen3.5:4b.
  """

  def __init__(
    self, host: str, name: str, transport: httpx.BaseTransport | None = None
  ) -> None:
    self._host = host.rstrip("/")
    self.name = name
    self._transport = transport

  def _tags(self) -> list[str] | None:
    try:
      with httpx.Client(timeout=2.0, transport=self._transport) as client:
        response = client.get(f"{self._host}/api/tags")
        response.raise_for_status()
        return [m.get("name", "") for m in response.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
      return None

  def unavailable(self) -> str | None:
    """Explains a stopped daemon or a missing model; otherwise None."""
    tags = self._tags()
    if tags is None:
      return "The advisor is offline: open Ollama or run `ollama serve`."
    family = self.name.split(":")[0]
    if not any(t.startswith(self.name) or t.startswith(family) for t in tags):
      return (
        f"Ollama is running but `{self.name}` is not downloaded. "
        f"Run `ollama pull {self.name}`."
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
    messages: list[dict[str, Any]] = [
      {"role": "system", "content": system},
      *({"role": t.role, "content": t.content} for t in history),
      {"role": "user", "content": message},
    ]
    specs = [
      {
        "type": "function",
        "function": {
          "name": t.name,
          "description": t.description,
          "parameters": t.parameters,
        },
      }
      for t in tools
    ]
    with httpx.Client(timeout=_TIMEOUT, transport=self._transport) as client:

      def turn(
        rounds: Sequence[llm.Round], allow_tools: bool
      ) -> Iterator[str | llm.Step]:
        replay: list[dict[str, Any]] = []
        for r in rounds:
          replay.append(
            {"role": "assistant", "content": "", "tool_calls": r.step.raw}
          )
          replay += [
            {"role": "tool", "name": c.name, "content": out}
            for c, out in zip(r.step.calls, r.results, strict=True)
          ]
        calls: list[dict[str, Any]] = []
        for chunk in self._stream(
          client, messages + replay, specs if allow_tools else []
        ):
          calls.extend(chunk.get("tool_calls") or [])
          if chunk.get("content"):
            yield chunk["content"]
        yield llm.Step([_call(c) for c in calls], calls)

      yield from llm.run(turn, execute)

  def _stream(
    self,
    client: httpx.Client,
    messages: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
  ) -> Iterator[dict[str, Any]]:
    """Yields the message of each streamed chunk."""
    payload: dict[str, Any] = {
      "model": self.name,
      "messages": list(messages),
      "stream": True,
      "think": _THINK,
      "keep_alive": _KEEP_ALIVE,
      "options": _OPTIONS,
    }
    if specs:
      payload["tools"] = list(specs)
    try:
      with client.stream(
        "POST", f"{self._host}/api/chat", json=payload
      ) as response:
        if response.status_code != HTTPStatus.OK:
          response.read()
          raise llm.ModelError(
            f"Ollama couldn't answer ({response.status_code}): "
            f"{response.text[:200]}"
          )
        for line in response.iter_lines():
          if line:
            yield json.loads(line).get("message") or {}
    except (httpx.HTTPError, json.JSONDecodeError) as e:
      logging.warning("Ollama request failed: %s", e)
      raise llm.ModelError(f"The local model stopped responding ({e}).") from e


def _call(raw: Mapping[str, Any]) -> llm.Call:
  """Reads a tool call; some models send arguments as a JSON string."""
  fn = raw.get("function", {})
  args = fn.get("arguments") or {}
  return llm.Call(
    fn.get("name", ""), json.loads(args) if isinstance(args, str) else args
  )
