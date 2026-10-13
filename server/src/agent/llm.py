"""The language-model interface the advisor talks to, and its configuration.

A model takes a system prompt, the conversation so far, the student's
message, and tools, and streams reply text. The tool loop (`run`) lives
here, apart from any wire format, so the model module only translates one
turn, and tests fake a whole model behind the `Model` protocol. The model
is Gemini, configured by the environment:

  GEMINI_API_KEY        Google AI Studio key
  GEMINI_MODELS         comma-separated, preferred first; later ones take
                        over while earlier ones are busy or out of quota

Model names are configuration, never code: they change monthly, and the
advisor says which variable to set when one is missing.
"""

import dataclasses
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Literal, Protocol

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


def from_env(env: Mapping[str, str] = os.environ) -> Model:
  """Builds the model `env` configures (see the module doc)."""
  from server.src.agent import gemini

  models = [m.strip() for m in env.get("GEMINI_MODELS", "").split(",")]
  return gemini.Gemini(env.get("GEMINI_API_KEY", ""), [m for m in models if m])
