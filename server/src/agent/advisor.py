"""Runs an advising conversation and streams it as Server-Sent Events.

Owns the prompt, the student brief that grounds it, which chips end a
reply, and the reply check: any course the reply names that the brief, a
tool result, and the catalog all lack is reported back as unverified.
Models live behind llm.Model; tools and their renderings in `tools`;
transport (threads, the event loop) in the chat route.
"""

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence, Set
from typing import Any, Literal

import pydantic

from server.src.agent import brief, chips, llm, tools
from server.src.catalog import codes
from server.src.data import catalog_db, catalog_models


class ChatTurn(pydantic.BaseModel):
  """A prior message in the conversation."""

  role: Literal["user", "assistant"]
  content: str
  action_chips: list[chips.Chip] = pydantic.Field(
    default=[], description="What an assistant turn offered, as it ended."
  )


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
  variants: list[brief.Variant] = pydantic.Field(
    default=[], description="The student's other schedules."
  )
  screen: brief.Screen = pydantic.Field(
    default_factory=brief.Screen,
    description="What the student is looking at as they ask.",
  )


class ClosingEvent(pydantic.BaseModel):
  """The final event of a reply: chips, and courses the reply made up."""

  action_chips: list[chips.Chip]
  unverified: list[str] = pydantic.Field(
    description="Courses the reply names that the catalog does not have."
  )


SYSTEM_PROMPT = f"""You are usched, an academic advisor for USC students.

Ground every answer in facts:
- The student brief below lists their progress, the courses they can take
  next, open GE categories, and their week. Answer from it first.
- Name only courses that appear in the brief or in a tool result. For any
  other course, call search_courses or get_course_details first; never
  guess a course code, title, time, or instructor.
- The brief also says what is on screen: "this course" is the open course,
  and "this one" or "option 2" is the proposal the week shows.
- If the facts do not answer the question, say so plainly.

Work in steps: up to {llm.TOOL_ROUNDS} rounds of tool calls, then answer.
- In one round, call every tool you can already decide on together, e.g.
  get_course_details for each course being compared.
- Chain when one result decides the next: search_courses for candidates,
  then solve_schedule with the best ones.

Let the student act on what you say:
- When they want a schedule, or to fit courses together, call
  solve_schedule; its options appear on the student's week to keep.
- When they ask about one course, call get_course_details; its sections
  become buttons that add them to the week.
- When they ask to add, swap, or drop sections or courses, call edit_week
  with section numbers from the brief or a tool result; they see the
  edited week to keep. When they say they took a course, call mark_taken.

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


def closing_chips(from_tools: Sequence[chips.Chip]) -> list[chips.Chip]:
  """Up to four chips, all from what the model did; the last of a label wins.

  A reply that used no tools ends with none: a chip is a follow-up to
  something the advisor actually looked up or built, never filler.
  """
  unique = {c.label: c for c in reversed(from_tools)}
  return list(reversed(unique.values()))[:_MAX_CHIPS]


def remembered(conn: sqlite3.Connection, term: int, turn: ChatTurn) -> str:
  """A past turn as the model rereads it, with what the reply offered.

  History is text, so without this the model forgets the schedules it
  proposed and cannot resolve "option 2" or "the first one" later.
  """
  offered: list[str] = []
  for chip in turn.action_chips:
    match chip:
      case chips.ProposeSchedule(name=name, section_ids=ids):
        offered.append(
          brief.schedule_line(conn, term, brief.Variant(name, ids))
        )
      case chips.EnrollSection(section_id=sid):
        offered.append(f"adding section {sid}")
      case chips.WatchCourse(course_code=code):
        offered.append(f"saving {code}")
      case chips.MarkTaken(course_codes=taken):
        offered.append(f"marked {', '.join(taken)} taken")
      case chips.Search():
        pass
  if not offered:
    return turn.content
  return f"{turn.content}\n[Your reply offered: {'; '.join(offered)}]"


def unverified(
  reply: str, grounded: Set[str], conn: sqlite3.Connection
) -> list[str]:
  """Courses `reply` names, as written, that no source or catalog backs.

  A course the brief and tools never mentioned is still real if the
  catalog knows it in any term; only invented codes are flagged.
  """
  named = {
    key: written
    for key, written in codes.mentions(reply).items()
    if key not in grounded
  }
  known = catalog_db.canonical(conn, named)
  return [written for key, written in named.items() if key not in known]


def _event(payload: Any) -> str:
  return f"data: {json.dumps(payload)}\n\n"


def _token(text: str) -> str:
  return _event({"token": text})


def stream(
  request: ChatRequest, conn: sqlite3.Connection, model: llm.Model
) -> Iterator[str]:
  """Yields SSE events: tokens, then one closing event, then `[DONE]`."""
  from_tools: list[chips.Chip] = []
  flagged: list[str] = []
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
        variants=request.variants,
        screen=request.screen,
      ),
    )
    grounded = set(facts.grounded)

    def execute(name: str, arguments: Mapping[str, Any]) -> str:
      result = tools.execute(
        name, arguments, conn, request.term, request.section_ids
      )
      from_tools.extend(result.chips)
      grounded.update(codes.mentions(result.content))
      return result.content

    reply: list[str] = []
    try:
      for token in model.reply(
        f"{SYSTEM_PROMPT}\n{facts.text}",
        [
          llm.Turn(t.role, remembered(conn, request.term, t))
          for t in request.history[-_HISTORY_TURNS:]
        ],
        request.message,
        tools.TOOLS,
        execute,
      ):
        reply.append(token)
        yield _token(token)
    except llm.ModelError as e:
      yield _token(f"\n\n{e}")
    flagged = unverified("".join(reply), grounded, conn)
  closing = ClosingEvent(
    action_chips=closing_chips(from_tools),
    unverified=flagged,
  )
  yield _event(closing.model_dump())
  yield "data: [DONE]\n\n"
