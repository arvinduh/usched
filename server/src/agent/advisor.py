"""Runs an advising conversation and streams it as Server-Sent Events.

Owns the prompt, the student brief that grounds it, which chips end a
reply, and the reply check: any course the reply names that the brief, a
tool result, and the catalog all lack is reported back as unverified.
Models live behind llm.Model; tools and their renderings in `tools`;
transport (threads, the event loop) in the chat route.
"""

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Literal

import pydantic

from server.src.agent import brief, chips, llm, tools
from server.src.catalog import codes
from server.src.data import catalog_db, catalog_models


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
  section_ids: list[str] = pydantic.Field(
    default=[], description="Sections in the active schedule."
  )
  shortlisted: list[str] = pydantic.Field(
    default=[], description="Codes of courses saved for later."
  )
  completed: list[str] = pydantic.Field(
    default=[], description="Codes of courses already taken."
  )
  ap_credits: list[catalog_models.ApCredit] = []


class ClosingEvent(pydantic.BaseModel):
  """The final event of a reply: chips, and courses the reply made up."""

  action_chips: list[chips.Chip]
  unverified: list[str] = pydantic.Field(
    description="Courses the reply names that the catalog does not have."
  )


SYSTEM_PROMPT = """You are usched, an academic advisor for USC students.

Ground every answer in facts:
- The student brief below lists their progress, the courses they can take
  next, open GE categories, and their week. Answer from it first.
- Name only courses that appear in the brief or in a tool result. For any
  other course, call search_courses or get_course_details first; never
  guess a course code, title, time, or instructor.
- If the facts do not answer the question, say so plainly.

Let the student act on what you say:
- When they want a schedule, or to fit courses together, call
  solve_schedule; each option it finds becomes a button to preview and keep.
- When they ask about one course, call get_course_details; its sections
  become buttons that add them to the week.

Be strategic: point out workload traps, courses that unlock later
requirements, and instructor ratings, and name sections so the student can
act.

Write Markdown for a narrow side panel, under about 150 words:
- Open with a sentence that answers the question directly.
- Explain in short paragraphs. Use a list only for three or more parallel
  items, such as courses to compare, one line each: the course code, then
  why. Use **bold** only for the one thing to act on.
- Never use tables or headings.
"""
_HISTORY_TURNS = 6
_MAX_CHIPS = 4


def closing_chips(
  message: str, from_tools: Sequence[chips.Chip], next_codes: Sequence[str]
) -> list[chips.Chip]:
  """Picks up to four chips: the tools' first, then ones the message invites.

  With room left, suggests the courses the student can take next.
  """
  found: list[chips.Chip] = list(from_tools)
  text = message.lower()
  if any(w in text for w in ("degree", "audit", "graduat", "requirement")):
    found.append(chips.Show(label="Open degree", view="degree"))
  if any(w in text for w in ("schedule", "calendar", "conflict", "week")):
    found.append(chips.Show(label="Open week", view="week"))
  if len(found) < 2:
    found += [chips.Search(label=f"Show {c}", query=c) for c in next_codes[:2]]
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


def stream(
  request: ChatRequest, conn: sqlite3.Connection, model: llm.Model
) -> Iterator[str]:
  """Yields SSE events: tokens, then one closing event, then `[DONE]`."""
  from_tools: list[chips.Chip] = []
  next_codes: list[str] = []
  unverified: list[str] = []
  reason = model.unavailable()
  if reason:
    yield _token(reason)
  else:
    facts = brief.build(
      conn,
      brief.Student(
        term=request.term,
        program_id=request.program_id,
        section_ids=request.section_ids,
        shortlisted=request.shortlisted,
        completed=request.completed,
        ap_credits=request.ap_credits,
      ),
    )
    next_codes = facts.next_codes
    grounded = set(facts.grounded)

    def execute(name: str, arguments: Mapping[str, Any]) -> str:
      result = tools.execute(name, arguments, conn, request.term)
      from_tools.extend(result.chips)
      grounded.update(codes.mentions(result.content))
      return result.content

    reply: list[str] = []
    try:
      for token in model.reply(
        f"{SYSTEM_PROMPT}\n{facts.text}",
        [
          llm.Turn(t.role, t.content) for t in request.history[-_HISTORY_TURNS:]
        ],
        request.message,
        tools.TOOLS,
        execute,
      ):
        reply.append(token)
        yield _token(token)
    except llm.ModelError as e:
      yield _token(f"\n\n{e}")
    named = {
      key: written
      for key, written in codes.mentions("".join(reply)).items()
      if key not in grounded
    }
    known = catalog_db.canonical(conn, named)
    unverified = [w for key, w in named.items() if key not in known]
  closing = ClosingEvent(
    action_chips=closing_chips(request.message, from_tools, next_codes),
    unverified=unverified,
  )
  yield _event(closing.model_dump())
  yield "data: [DONE]\n\n"
