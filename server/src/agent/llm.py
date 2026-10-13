"""The language-model interface the advisor talks to, and its configuration.

A model takes a system prompt, the conversation so far, the student's
message, and tools, and streams reply text. The tool loop (`run`) lives
here, apart from any wire format, so the model module only translates one
turn, and tests fake a whole model behind the `Model` protocol. The model
is Gemini, configured by the environment:

  GEMINI_API_KEY        Google AI Studio key
  GEMINI_MODEL          default gemini-flash-latest
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
  """Builds the model the environment configures (see the module doc)."""
  from server.src.agent import gemini

  return gemini.Gemini(
    os.getenv("GEMINI_API_KEY", ""),
    os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
  )
