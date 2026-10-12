"""Runs an advising conversation and streams it as Server-Sent Events.

Owns the prompt, the tool loop with the local model, and which chips end
a reply. Tools and their renderings live in `tools`; transport (threads,
the event loop) lives in the chat route.
"""

import json
import sqlite3
from collections.abc import Generator, Iterator, Sequence
from typing import Any, Literal

import httpx
import pydantic
from absl import logging

from server.src.agent import chips, ollama, tools
from server.src.data import catalog_db


class ChatTurn(pydantic.BaseModel):
  """A prior message in the conversation."""

  role: Literal["user", "assistant"]
  content: str


class ChatRequest(pydantic.BaseModel):
  """A student's message with what the advisor should know about them."""

  message: str
  history: list[ChatTurn] = []
  term: int = pydantic.Field(description="The term being planned.")
  program_id: str | None = None
  planned: list[str] = pydantic.Field(
    default=[], description="Codes of courses in the active schedule."
  )
  shortlisted: list[str] = pydantic.Field(
    default=[], description="Codes of courses saved for later."
  )
  completed: list[str] = pydantic.Field(
    default=[], description="Codes of courses already taken."
  )


class ChipsEvent(pydantic.BaseModel):
  """The final event of a reply: chips for the student to act on."""

  action_chips: list[chips.Chip]


SYSTEM_PROMPT = """You are usched, an academic advisor for USC students.

Be strategic, not encyclopedic:
- Spot workload traps (two project-heavy courses together) and courses that
  unlock many later requirements.
- Judge instructors by rating and difficulty, and name the sections you mean
  so the student can act.
- Call solve_schedule to build or optimize schedules, passing the student's
  day, time, and instructor preferences. Call search_courses or
  get_course_details before stating facts about a course, and
  audit_program for degree progress.

Answer in at most 120 words of plain text for a narrow side panel: short
sentences or a few "- " bullets, never tables, headings, or rules.
"""
_HISTORY_TURNS = 6
_MAX_CHIPS = 4


def _term_name(conn: sqlite3.Connection, term: int) -> str:
  for t in catalog_db.terms(conn):
    if t.code == term:
      return f"{t.season} {t.year}"
  return str(term)


def _context(conn: sqlite3.Connection, request: ChatRequest) -> str:
  def listed(codes: Sequence[str]) -> str:
    return ", ".join(codes) or "none"

  return (
    "[Student]\n"
    f"- Planning: {_term_name(conn, request.term)}\n"
    f"- Program: {request.program_id or 'not chosen'}\n"
    f"- Scheduled: {listed(request.planned)}\n"
    f"- Shortlisted: {listed(request.shortlisted)}\n"
    f"- Completed: {listed(request.completed)}\n"
  )


def closing_chips(
  conn: sqlite3.Connection,
  student: tools.Student,
  message: str,
  from_tools: Sequence[chips.Chip],
) -> list[chips.Chip]:
  """Picks up to four chips: the tools' first, then ones the message invites.

  With room left and a program chosen, suggests courses the student can
  take next.
  """
  found: list[chips.Chip] = list(from_tools)
  text = message.lower()
  if any(w in text for w in ("degree", "audit", "graduat", "requirement")):
    found.append(chips.Show(label="Open degree", view="degree"))
  if any(w in text for w in ("schedule", "calendar", "conflict", "week")):
    found.append(chips.Show(label="Open week", view="week"))
  if len(found) < 2 and student.program_id:
    found += tools.audit_program(conn, student).chips
  if not found:
    found = [
      chips.Show(label="Open degree", view="degree"),
      chips.Show(label="Open week", view="week"),
    ]
  unique = {c.label: c for c in reversed(found)}
  return list(reversed(unique.values()))[:_MAX_CHIPS]


def _event(payload: Any) -> str:
  return f"data: {json.dumps(payload)}\n\n"


def _token(text: str) -> str:
  return _event({"token": text})


def stream(request: ChatRequest, conn: sqlite3.Connection) -> Iterator[str]:
  """Yields SSE events: tokens, then one chips event, then `[DONE]`.

  The model's first pass streams straight through, so a direct answer
  appears token by token and only a tool call costs a second pass.
  """
  student = tools.Student(
    term=request.term,
    program_id=request.program_id,
    completed=tuple(request.completed),
  )
  from_tools: list[chips.Chip] = []
  if not ollama.is_ollama_available():
    yield _token(
      "The advisor is offline: start Ollama "
      f"(`ollama run {ollama.MODEL_NAME}`) to chat."
    )
  elif not ollama.is_model_downloaded():
    yield _token(
      f"Ollama is running but `{ollama.MODEL_NAME}` is not downloaded. "
      f"Run `ollama pull {ollama.MODEL_NAME}`."
    )
  else:
    try:
      from_tools = yield from _converse(request, conn, student)
    except (httpx.HTTPError, json.JSONDecodeError) as e:
      logging.error("Advisor failed: %s", e)
      yield _token(f"\n\n[The advisor failed: {e}]")
  chosen = closing_chips(conn, student, request.message, from_tools)
  yield _event(ChipsEvent(action_chips=chosen).model_dump())
  yield "data: [DONE]\n\n"


def _converse(
  request: ChatRequest, conn: sqlite3.Connection, student: tools.Student
) -> Generator[str, None, list[chips.Chip]]:
  """Streams the model's reply, running any tools it calls in between.

  Returns (as the generator's value) the chips the tools produced.
  """
  messages: list[dict[str, Any]] = [
    {
      "role": "system",
      "content": f"{SYSTEM_PROMPT}\n{_context(conn, request)}",
    },
    *(t.model_dump() for t in request.history[-_HISTORY_TURNS:]),
    {"role": "user", "content": request.message},
  ]
  calls: list[dict[str, Any]] = []
  for chunk in ollama.stream_ollama_chat(messages, tools.OLLAMA_TOOLS):
    calls.extend(chunk.get("tool_calls") or [])
    if chunk.get("content"):
      yield _token(chunk["content"])
  if not calls:
    return []
  from_tools: list[chips.Chip] = []
  messages.append({"role": "assistant", "content": "", "tool_calls": calls})
  for call in calls:
    fn = call.get("function", {})
    args = fn.get("arguments") or {}
    if isinstance(args, str):
      args = json.loads(args)
    result = tools.execute(fn.get("name", ""), args, conn, student)
    from_tools += result.chips
    messages.append(
      {"role": "tool", "name": fn.get("name", ""), "content": result.content}
    )
  for chunk in ollama.stream_ollama_chat(messages):
    if chunk.get("content"):
      yield _token(chunk["content"])
  return from_tools
