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


def call_ollama_chat(
  messages: list[dict[str, Any]],
  tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
  """Dispatches non-streaming chat request with optional structured tools.

  Args:
    messages: Conversational history turns.
    tools: Tool schemas formatted for Ollama / OpenAI function calling.

  Returns:
    Assistant response dictionary containing content or tool_calls.
  """
  payload: dict[str, Any] = {
    "model": MODEL_NAME,
    "messages": messages,
    "stream": False,
  }
  if tools:
    payload["tools"] = tools

  try:
    with httpx.Client(timeout=90.0) as client:
      resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
      if resp.status_code == HTTPStatus.OK:
        data: dict[str, Any] = resp.json()
        msg: dict[str, Any] = data.get("message", {})
        return msg
  except (httpx.HTTPError, json.JSONDecodeError) as exc:
    logging.warning("Ollama chat execution warning: %s", exc)

  return {
    "role": "assistant",
    "content": (
      "I am your local usched advisor. Ollama service is currently offline, "
      "so I am using direct academic logic engines to assist you."
    ),
  }


def stream_ollama_chat(
  messages: list[dict[str, Any]],
) -> Iterator[str]:
  """Streams text response tokens incrementally from Ollama daemon."""
  payload = {
    "model": MODEL_NAME,
    "messages": messages,
    "stream": True,
  }

  try:
    with httpx.Client(
      timeout=httpx.Timeout(90.0, connect=10.0, read=90.0)
    ) as client:
      with client.stream(
        "POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload
      ) as resp:
        if resp.status_code != HTTPStatus.OK:
          yield (
            "I could not connect to local Ollama. Please ensure `ollama run "
            f"{MODEL_NAME}` is active."
          )
          return
        for line in resp.iter_lines():
          if not line:
            continue
          try:
            chunk = json.loads(line)
            content = chunk.get("message", {}).get("content", "")
            if content:
              yield content
          except json.JSONDecodeError:
            continue
  except httpx.HTTPError as exc:
    logging.warning("Ollama streaming stream error: %s", exc)
    yield f"\n[Advisor note: Model stream interrupted ({exc})]"
