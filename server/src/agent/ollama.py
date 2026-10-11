"""Local Ollama client communicating with Qwen 3.5 4B.

This module manages HTTP communication with the local Ollama daemon,
including health checks, non-streaming tool calling, and SSE token streaming.
"""

import json
import os
from collections.abc import Iterator
from http import HTTPStatus
from typing import Any

import httpx
from absl import logging


OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("USCHED_LLM_MODEL", "qwen3.5:4b")
# Reasoning models emit hidden "thinking" tokens before any answer; on
# qwen3.5:4b that turns a 3 s reply into 2 minutes of silence.
_THINK = False
# Keeps the model resident between messages so a reply never waits on a
# reload, and caps reply length so a runaway answer cannot take minutes.
_KEEP_ALIVE = "30m"
_OPTIONS = {"num_predict": 400}


def is_ollama_available() -> bool:
  """Checks if local Ollama service is reachable on configured port."""
  try:
    with httpx.Client(timeout=1.5) as client:
      resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
      return resp.status_code == HTTPStatus.OK
  except httpx.HTTPError:
    return False


def is_model_downloaded(model_name: str = MODEL_NAME) -> bool:
  """Checks whether target model tag is downloaded in local Ollama."""
  try:
    with httpx.Client(timeout=2.0) as client:
      resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
      if resp.status_code == HTTPStatus.OK:
        data: dict[str, Any] = resp.json()
        models_list: list[dict[str, Any]] = data.get("models", [])
        m_prefix = model_name.split(":")[0]
        return any(
          m.get("name", "").startswith(model_name)
          or m.get("name", "").startswith(m_prefix)
          for m in models_list
        )
  except (httpx.HTTPError, json.JSONDecodeError):
    return False
  return False


def stream_ollama_chat(
  messages: list[dict[str, Any]],
  tools: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
  """Streams assistant message chunks from the Ollama daemon.

  With `tools`, the model may answer directly (content chunks stream as they
  are generated) or request tools (a chunk carrying `tool_calls`), so callers
  never wait on a full non-streamed pass before showing text.

  Args:
    messages: Conversational history turns.
    tools: Tool schemas in Ollama / OpenAI function-calling format.

  Yields:
    Message dicts with optional "content" and "tool_calls" keys. Connection
    failures are reported as a final content chunk rather than raised.
  """
  payload: dict[str, Any] = {
    "model": MODEL_NAME,
    "messages": messages,
    "stream": True,
    "think": _THINK,
    "keep_alive": _KEEP_ALIVE,
    "options": _OPTIONS,
  }
  if tools:
    payload["tools"] = tools

  try:
    with (
      httpx.Client(
        timeout=httpx.Timeout(90.0, connect=10.0, read=90.0)
      ) as client,
      client.stream(
        "POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload
      ) as resp,
    ):
      if resp.status_code != HTTPStatus.OK:
        yield {
          "content": (
            "I could not connect to local Ollama. Please ensure `ollama run "
            f"{MODEL_NAME}` is active."
          )
        }
        return
      for line in resp.iter_lines():
        if not line:
          continue
        try:
          chunk = json.loads(line)
        except json.JSONDecodeError:
          continue
        message: dict[str, Any] = chunk.get("message", {})
        if message:
          yield message
  except httpx.HTTPError as exc:
    logging.warning("Ollama streaming stream error: %s", exc)
    yield {"content": f"\n[Advisor note: Model stream interrupted ({exc})]"}
