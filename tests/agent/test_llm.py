"""Tests for the model providers against faked HTTP, and their configuration."""

import json
from typing import Any

import httpx
import pytest

from server.src.agent import gemini, llm, ollama


TOOLS = [
  llm.Tool(
    "search_courses",
    "Searches courses.",
    {"type": "object", "properties": {"query": {"type": "string"}}},
  )
]


def _sse(*chunks: dict[str, Any]) -> bytes:
  return b"".join(f"data: {json.dumps(c)}\r\n\r\n".encode() for c in chunks)


def _parts(*parts: dict[str, Any]) -> dict[str, Any]:
  return {"candidates": [{"content": {"role": "model", "parts": list(parts)}}]}


def test_gemini_streams_text_and_runs_a_tool_round():
  bodies: list[dict[str, Any]] = []

  def handle(request: httpx.Request) -> httpx.Response:
    bodies.append(json.loads(request.content))
    assert request.headers["x-goog-api-key"] == "key"
    assert request.url.params["alt"] == "sse"
    if len(bodies) == 1:
      call = {
        "functionCall": {"name": "search_courses", "args": {"query": "ai"}},
        "thoughtSignature": "sig",
      }
      return httpx.Response(200, content=_sse(_parts(call)))
    return httpx.Response(
      200,
      content=_sse(
        _parts({"text": "plan", "thought": True}),
        _parts({"text": "Try "}),
        _parts({"text": "CSCI 360."}),
      ),
    )

  calls: list[tuple[str, Any]] = []

  def execute(name: str, args: Any) -> str:
    calls.append((name, args))
    return "CSCI-360: Introduction to AI"

  model = gemini.Gemini("key", "gemini-test", httpx.MockTransport(handle))
  history = [llm.Turn("user", "hi"), llm.Turn("assistant", "hello")]
  text = "".join(model.reply("system", history, "ai?", TOOLS, execute))
  assert text == "Try CSCI 360."
  assert calls == [("search_courses", {"query": "ai"})]
  first, second = bodies
  assert [c["role"] for c in first["contents"]] == ["user", "model", "user"]
  assert first["systemInstruction"] == {"parts": [{"text": "system"}]}
  declaration = first["tools"][0]["functionDeclarations"][0]
  assert declaration["parametersJsonSchema"]["type"] == "object"
  # The model's parts go back verbatim (signature included), then results.
  assert second["contents"][-2]["parts"][0]["thoughtSignature"] == "sig"
  response = second["contents"][-1]["parts"][0]["functionResponse"]
  assert response == {
    "name": "search_courses",
    "response": {"result": "CSCI-360: Introduction to AI"},
  }


def test_gemini_forbids_tools_on_its_last_round():
  modes: list[str] = []

  def handle(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    modes.append(body["toolConfig"]["functionCallingConfig"]["mode"])
    call = {"functionCall": {"name": "search_courses", "args": {}}}
    return httpx.Response(200, content=_sse(_parts(call)))

  model = gemini.Gemini("key", "m", httpx.MockTransport(handle))
  list(model.reply("s", [], "q", TOOLS, lambda name, args: "none"))
  assert modes == ["AUTO", "AUTO", "NONE"]


@pytest.mark.parametrize(
  ("status", "message"),
  [
    (429, "The advisor is busy (free-tier limit). Try again in a minute."),
    (400, "Gemini couldn't answer (400: API key not valid)."),
  ],
)
def test_gemini_errors_read_well(status, message):
  def handle(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(
      status, json={"error": {"message": "API key not valid"}}
    )

  model = gemini.Gemini("key", "m", httpx.MockTransport(handle))
  with pytest.raises(
    llm.ModelError, match=message.replace("(", r"\(").replace(")", r"\)")
  ):
    list(model.reply("s", [], "q", [], lambda name, args: ""))


def test_gemini_without_a_key_explains_how_to_get_one():
  reason = gemini.Gemini("", "m").unavailable()
  assert reason is not None and "GEMINI_API_KEY" in reason
  assert gemini.Gemini("key", "m").unavailable() is None


def test_ollama_forbids_tools_on_its_last_round():
  offered: list[bool] = []

  def handle(request: httpx.Request) -> httpx.Response:
    offered.append("tools" in json.loads(request.content))
    call = {"function": {"name": "search_courses", "arguments": {}}}
    line = {"message": {"content": "", "tool_calls": [call]}}
    return httpx.Response(200, content=json.dumps(line))

  model = ollama.Ollama("http://ollama", "qwen", httpx.MockTransport(handle))
  list(model.reply("s", [], "q", TOOLS, lambda name, args: "none"))
  assert offered == [True, True, False]


def test_ollama_streams_then_answers_tool_results():
  payloads: list[dict[str, Any]] = []

  def handle(request: httpx.Request) -> httpx.Response:
    payloads.append(json.loads(request.content))
    if len(payloads) == 1:
      call = {
        "function": {"name": "search_courses", "arguments": {"query": "x"}}
      }
      lines = [{"message": {"content": "", "tool_calls": [call]}}]
    else:
      lines = [{"message": {"content": "Done"}}, {"message": {"content": "."}}]
    return httpx.Response(200, content="\n".join(map(json.dumps, lines)))

  model = ollama.Ollama("http://ollama", "qwen", httpx.MockTransport(handle))
  text = "".join(
    model.reply("sys", [], "q", TOOLS, lambda name, args: "result")
  )
  assert text == "Done."
  assert payloads[1]["messages"][-2]["tool_calls"][0]["function"]["name"] == (
    "search_courses"
  )
  assert payloads[1]["messages"][-1] == {
    "role": "tool",
    "name": "search_courses",
    "content": "result",
  }


def test_ollama_reports_a_stopped_daemon():
  def refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)

  model = ollama.Ollama("http://ollama", "qwen", httpx.MockTransport(refuse))
  reason = model.unavailable()
  assert reason is not None and "offline" in reason


def test_the_environment_picks_the_provider(monkeypatch):
  for name in ("USCHED_LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL"):
    monkeypatch.delenv(name, raising=False)
  assert isinstance(llm.from_env(), ollama.Ollama)
  monkeypatch.setenv("GEMINI_API_KEY", "key")
  model = llm.from_env()
  assert (
    isinstance(model, gemini.Gemini) and model.name == "gemini-flash-latest"
  )
  monkeypatch.setenv("USCHED_LLM_PROVIDER", "ollama")
  assert isinstance(llm.from_env(), ollama.Ollama)
  monkeypatch.setenv("USCHED_LLM_PROVIDER", "openai")
  with pytest.raises(ValueError, match="gemini or ollama"):
    llm.from_env()
