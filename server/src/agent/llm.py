"""The language-model interface the advisor talks to, and its configuration.

A provider takes a system prompt, the conversation so far, the student's
message, and tools, and streams reply text. Each provider runs its own
tool loop, since their wire formats differ, calling back into the advisor
to execute a tool. Which provider runs is configuration:

  USCHED_LLM_PROVIDER   gemini | ollama; default gemini when GEMINI_API_KEY
                        is set, else ollama
  GEMINI_API_KEY        Google AI Studio key (hosted deployments)
  GEMINI_MODEL          default gemini-flash-latest
  OLLAMA_HOST           default http://127.0.0.1:11434 (local development)
  OLLAMA_MODEL          default qwen3.5:4b
"""

import dataclasses
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Literal, Protocol


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
  ) -> Iterator[str]:
    """Streams reply text, running any tools the model calls in between.

    Raises:
      ModelError: The provider failed; its message explains why.
    """
    ...


def from_env() -> Model:
  """Builds the provider the environment selects (see the module doc)."""
  from server.src.agent import gemini, ollama

  key = os.getenv("GEMINI_API_KEY", "")
  provider = os.getenv("USCHED_LLM_PROVIDER") or ("gemini" if key else "ollama")
  if provider == "gemini":
    return gemini.Gemini(key, os.getenv("GEMINI_MODEL", "gemini-flash-latest"))
  if provider == "ollama":
    return ollama.Ollama(
      os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
      os.getenv("OLLAMA_MODEL", "qwen3.5:4b"),
    )
  raise ValueError(f"USCHED_LLM_PROVIDER must be gemini or ollama: {provider}")
