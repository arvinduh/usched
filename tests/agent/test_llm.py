"""Tests for choosing a model, and live tests of the real providers.

Live tests talk to the configured Gemini or Ollama and spend real quota,
so they run only on request: `npm run test:live`.
"""

import pytest

from server.src.agent import gemini, llm, ollama


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
  assert "GEMINI_API_KEY" in (
    llm.from_env({"USCHED_LLM_PROVIDER": "gemini"}).unavailable() or ""
  )
  assert "GEMINI_MODELS" in (
    llm.from_env({"GEMINI_API_KEY": "k"}).unavailable() or ""
  )
  local = llm.from_env({})
  assert isinstance(local, ollama.Ollama)
  assert "OLLAMA_MODEL" in (local.unavailable() or "")


def test_the_provider_can_be_forced_but_not_invented():
  forced = llm.from_env(
    {"GEMINI_API_KEY": "k", "USCHED_LLM_PROVIDER": "ollama"}
  )
  assert isinstance(forced, ollama.Ollama)
  with pytest.raises(ValueError, match="gemini or ollama"):
    llm.from_env({"USCHED_LLM_PROVIDER": "openai"})


@pytest.mark.live
def test_live_model_answers_and_calls_tools(live_model):
  """The configured model streams text and uses a tool when it needs one."""
  calls: list[str] = []

  def execute(name: str, args: object) -> str:
    del args
    calls.append(name)
    return "CSCI-467: Introduction to Machine Learning (4 units)"

  text = "".join(
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
