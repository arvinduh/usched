"""Tests for configuring the model, the shared tool loop, and live Gemini.

Live tests talk to the configured Gemini and spend real quota, so they run
only on request: `npm run test:live`.
"""

from collections.abc import Iterable, Iterator, Sequence

import pytest

from server.agent import _llm


TOOLS = [
  _llm.Tool(
    "search_courses",
    "Searches this term's courses by code, title, or topic.",
    {
      "type": "object",
      "properties": {"query": {"type": "string"}},
      "required": ["query"],
    },
  )
]


def test_a_gemini_key_selects_gemini_with_the_configured_models():
  model = _llm.from_env(
    {"GEMINI_API_KEY": "k", "GEMINI_MODELS": " lite-a , lite-b ,"}
  )
  assert isinstance(model, _llm.Gemini)
  assert model.name == "lite-a, lite-b"
  assert model.unavailable() is None


@pytest.mark.parametrize(
  ("env", "missing_key"),
  [
    ({}, "GEMINI_API_KEY"),
    ({"GEMINI_API_KEY": "k"}, "GEMINI_MODELS"),
  ],
)
def test_missing_configuration_says_what_to_set(
  env: dict[str, str], missing_key: str
):
  assert missing_key in (_llm.from_env(env).unavailable() or "")


def _text(events: Iterable[_llm.Event]) -> str:
  """The answer a reply streams, without its thoughts and steps."""
  return "".join(e for e in events if isinstance(e, str))


def _scripted(*turns: Sequence[_llm.Call]):
  """A model turn that calls the given tools in order, then answers."""
  seen: list[tuple[int, bool]] = []

  def turn(
    rounds: Sequence[_llm.Round], allow_tools: bool
  ) -> Iterator[str | _llm.Step]:
    seen.append((len(rounds), allow_tools))
    calls = (
      turns[len(rounds)] if allow_tools and len(rounds) < len(turns) else []
    )
    if not calls:
      yield "Done."
    yield _llm.Step(list(calls), None)

  return turn, seen


def test_the_loop_feeds_each_round_its_results_then_answers():
  search = _llm.Call("search_courses", {"query": "ai"})
  solve = _llm.Call("solve_schedule", {"course_codes": ["CSCI-360"]})
  turn, seen = _scripted([search], [solve])
  ran: list[str] = []

  def execute(name: str, args: object) -> str:
    del args
    ran.append(name)
    return f"{name} result"

  events = list(_llm.run(turn, execute))
  assert _text(events) == "Done."
  # Each tool is announced as it starts, before its result feeds the model.
  assert [e.call for e in events if isinstance(e, _llm.Acting)] == [
    search,
    solve,
  ]
  assert ran == ["search_courses", "solve_schedule"]
  assert seen == [(0, True), (1, True), (2, False)]


def test_the_loop_forbids_tools_after_its_rounds():
  call = _llm.Call("search_courses", {})
  turn, seen = _scripted(*[[call]] * (_llm.TOOL_ROUNDS + 2))
  assert _text(_llm.run(turn, lambda name, args: "r")) == "Done."
  assert [allowed for _, allowed in seen] == [True] * _llm.TOOL_ROUNDS + [False]


def test_an_empty_turn_is_retried_once_without_tools():
  seen: list[bool] = []

  def turn(
    rounds: Sequence[_llm.Round], allow_tools: bool
  ) -> Iterator[str | _llm.Thought | _llm.Step]:
    del rounds
    seen.append(allow_tools)
    yield _llm.Thought("Weighing the options.")
    if len(seen) > 1:
      yield "Here it is."
    yield _llm.Step([], None)

  assert _text(_llm.run(turn, lambda name, args: "r")) == "Here it is."
  assert seen == [True, False]


def test_a_turn_empty_twice_gives_up():
  seen: list[bool] = []

  def turn(
    rounds: Sequence[_llm.Round], allow_tools: bool
  ) -> Iterator[_llm.Step]:
    del rounds
    seen.append(allow_tools)
    yield _llm.Step([], None)

  assert _text(_llm.run(turn, lambda name, args: "r")) == ""
  assert seen == [True, False]


@pytest.mark.live
def test_live_model_answers_and_calls_tools(live_model):
  """The configured model streams text and uses a tool when it needs one."""
  calls: list[str] = []

  def execute(name: str, args: object) -> str:
    del args
    calls.append(name)
    return "CSCI-467: Introduction to Machine Learning (4 units)"

  text = _text(
    live_model.reply(
      "You help USC students. Use search_courses to find courses.",
      [],
      "Which course covers machine learning? Search, then name it.",
      TOOLS,
      execute,
    )
  )
  assert calls == ["search_courses"]
  assert "467" in text
