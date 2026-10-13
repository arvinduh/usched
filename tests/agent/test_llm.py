"""Tests for configuring the model, the shared tool loop, and live Gemini.

Live tests talk to the configured Gemini and spend real quota, so they run
only on request: `npm run test:live`.
"""

from collections.abc import Iterable, Iterator, Sequence

import pytest

from server.src.agent import gemini, llm


TOOLS = [
  llm.Tool(
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
  model = llm.from_env(
    {"GEMINI_API_KEY": "k", "GEMINI_MODELS": " lite-a , lite-b ,"}
  )
  assert isinstance(model, gemini.Gemini)
  assert model.name == "lite-a, lite-b"
  assert model.unavailable() is None


def test_missing_configuration_says_what_to_set():
  assert "GEMINI_API_KEY" in (llm.from_env({}).unavailable() or "")
  assert "GEMINI_MODELS" in (
    llm.from_env({"GEMINI_API_KEY": "k"}).unavailable() or ""
  )


def _text(events: Iterable[llm.Event]) -> str:
  """The answer a reply streams, without its thoughts and steps."""
  return "".join(e for e in events if isinstance(e, str))


def _scripted(*turns: Sequence[llm.Call]):
  """A model turn that calls the given tools in order, then answers."""
  seen: list[tuple[int, bool]] = []

  def turn(
    rounds: Sequence[llm.Round], allow_tools: bool
  ) -> Iterator[str | llm.Step]:
    seen.append((len(rounds), allow_tools))
    calls = (
      turns[len(rounds)] if allow_tools and len(rounds) < len(turns) else []
    )
    if not calls:
      yield "Done."
    yield llm.Step(list(calls), None)

  return turn, seen


def test_the_loop_feeds_each_round_its_results_then_answers():
  search = llm.Call("search_courses", {"query": "ai"})
  solve = llm.Call("solve_schedule", {"course_codes": ["CSCI-360"]})
  turn, seen = _scripted([search], [solve])
  ran: list[str] = []

  def execute(name: str, args: object) -> str:
    del args
    ran.append(name)
    return f"{name} result"

  events = list(llm.run(turn, execute))
  assert _text(events) == "Done."
  # Each tool is announced as it starts, before its result feeds the model.
  assert [e.call for e in events if isinstance(e, llm.Acting)] == [
    search,
    solve,
  ]
  assert ran == ["search_courses", "solve_schedule"]
  assert seen == [(0, True), (1, True), (2, False)]


def test_the_loop_forbids_tools_after_its_rounds():
  call = llm.Call("search_courses", {})
  turn, seen = _scripted(*[[call]] * (llm.TOOL_ROUNDS + 2))
  assert _text(llm.run(turn, lambda name, args: "r")) == "Done."
  assert [allowed for _, allowed in seen] == [True] * llm.TOOL_ROUNDS + [False]


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
