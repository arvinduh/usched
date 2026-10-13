"""Tests for the model providers against faked HTTP, and their configuration."""

import json
from typing import Any

import httpx
import pytest

from server.src.agent import gemini, llm


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


def test_the_environment_configures_gemini(monkeypatch):
  for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
    monkeypatch.delenv(name, raising=False)
  model = llm.from_env()
  assert isinstance(model, gemini.Gemini)
  assert model.name == "gemini-flash-latest"
  assert model.unavailable() is not None
  monkeypatch.setenv("GEMINI_API_KEY", "key")
  monkeypatch.setenv("GEMINI_MODEL", "gemini-pro-latest")
  model = llm.from_env()
  assert model.name == "gemini-pro-latest" and model.unavailable() is None
