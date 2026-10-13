"""The language-model interface the advisor talks to, and its configuration.

A provider takes a system prompt, the conversation so far, the student's
message, and tools, and streams reply text. Providers are drop-in
replacements: the tools, prompt, and tool loop (`run`) are shared, and a
provider only translates one model turn to and from its wire format.
Which provider runs is configuration:

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

_ROUNDS = 3  # Model turns per reply; the last must answer in words.


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
class Round:
  """A finished tool round: the turn that called tools, and their results."""

  step: Step
  results: Sequence[str]


# One model turn: given the rounds so far and whether tools are allowed,
# streams reply text, then yields the Step that ended the turn.
ModelTurn = Callable[[Sequence[Round], bool], Iterator[str | Step]]


def run(turn: ModelTurn, execute: Execute) -> Iterator[str]:
  """Runs the tool loop every provider shares, streaming reply text.

  Each turn may call tools, whose results feed the next; the last of
  `_ROUNDS` turns forbids tools, so a reply always ends in words.
  """
  rounds: list[Round] = []
  for n in range(_ROUNDS):
    step: Step | None = None
    for event in turn(rounds, n < _ROUNDS - 1):
      if isinstance(event, Step):
        step = event
      else:
        yield event
    if step is None or not step.calls:
      return
    results = [execute(c.name, c.arguments) for c in step.calls]
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
