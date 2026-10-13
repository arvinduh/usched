"""A local Ollama daemon as the advisor's model, for development.

The first pass streams with tools, so a direct answer appears token by
token; only a tool request costs a second pass, which runs without tools.
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
      return f"The advisor is offline: start Ollama (`ollama run {self.name}`)."
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
      calls: list[dict[str, Any]] = []
      for chunk in self._stream(client, messages, specs):
        calls.extend(chunk.get("tool_calls") or [])
        if chunk.get("content"):
          yield chunk["content"]
      if not calls:
        return
      messages.append({"role": "assistant", "content": "", "tool_calls": calls})
      for call in calls:
        fn = call.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):
          args = json.loads(args)
        messages.append(
          {
            "role": "tool",
            "name": fn.get("name", ""),
            "content": execute(fn.get("name", ""), args),
          }
        )
      for chunk in self._stream(client, messages, []):
        if chunk.get("content"):
          yield chunk["content"]

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
