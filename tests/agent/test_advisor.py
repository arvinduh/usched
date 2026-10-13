"""Tests for the advisor's tools, brief, and stream, with the model faked."""

import dataclasses
import json
import sqlite3
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from server.src.agent import advisor, brief, chips, llm, tools
from server.src.data import catalog_db
from server.src.data import catalog_models as m


TERM = 20271


@pytest.fixture(scope="module")
def conn(catalog_path) -> Iterator[sqlite3.Connection]:
  conn = catalog_db.CatalogDb(catalog_path).connect()
  yield conn
  conn.close()


def test_search_lists_matches_with_search_chips(conn):
  result = tools.search_courses(conn, TERM, "data structures")
  assert result.content.startswith("CSCI-104L: Data Structures (4 units)")
  assert chips.Search(label="Show CSCI-104L", query="CSCI-104L") in result.chips


def test_details_include_requisites_seats_and_an_enroll_chip(conn):
  result = tools.get_course_details(conn, TERM, "csci-104l")
  assert "Prerequisites:" in result.content
  assert "D-clearance" in result.content
  assert any(isinstance(c, chips.EnrollSection) for c in result.chips)
  missing = tools.get_course_details(conn, TERM, "NOPE-1")
  assert missing.content == "NOPE-1 is not offered this term."


def test_solve_offers_each_option_as_a_proposal(conn):
  result = tools.solve_schedule(
    conn, TERM, ["CSCI-104L"], excluded_days=["friday"]
  )
  assert result.content.startswith("Option 1")
  proposals = [c for c in result.chips if isinstance(c, chips.ProposeSchedule)]
  assert proposals and proposals[0].section_ids
  absent = tools.solve_schedule(conn, TERM, ["CSCI-104L", "NOPE-1"])
  assert absent.content == "Not offered this term: NOPE-1."


def test_execute_reports_unknown_tools_and_bad_arguments(conn):
  assert "Unknown tool" in tools.execute("nope", {}, conn, TERM).content
  bad = tools.execute("search_courses", {"q": "x"}, conn, TERM)
  assert bad.content.startswith("Bad arguments for search_courses")


STUDENT = brief.Student(
  term=TERM,
  program_id="computer-science-bs",
  section_ids=["29905"],
  shortlisted=["CSCI-420"],
  completed=["CSCI-103L"],
  ap_credits=[m.ApCredit(exam_id="AP_CALC_BC", score=5)],
)


def test_the_brief_states_progress_next_steps_and_the_week(conn):
  facts = brief.build(conn, STUDENT)
  assert "Planning: Spring 2027" in facts.text
  assert "Program: Computer Science (BS)" in facts.text
  assert "Open GE categories:" in facts.text
  # The scheduled lecture still needs its lab and quiz.
  assert "CSCI-104L still needs a Lab and a Quiz" in facts.text
  # Courses already scheduled are not suggested again.
  assert "CSCI-104" not in {c.split("L")[0] for c in facts.next_codes}
  assert {"CSCI-104", "CSCI-420", "CSCI-103"} <= facts.grounded


def test_a_student_without_a_program_still_gets_a_brief(conn):
  facts = brief.build(conn, dataclasses.replace(STUDENT, program_id=None))
  assert "Program: not chosen" in facts.text
  assert facts.next_codes == []


@dataclasses.dataclass
class FakeModel:
  """Replies with scripted tokens, optionally calling one tool first."""

  tokens: Sequence[str]
  call: tuple[str, dict[str, Any]] | None = None
  reason: str | None = None
  name: str = "fake"
  seen_system: str = ""
  tool_output: str = ""

  def unavailable(self) -> str | None:
    return self.reason

  def reply(
    self,
    system: str,
    history: Sequence[llm.Turn],
    message: str,
    tools: Sequence[llm.Tool],
    execute: llm.Execute,
  ) -> Iterator[str]:
    del history, message, tools
    self.seen_system = system
    if self.call:
      self.tool_output = execute(*self.call)
    yield from self.tokens


def _events(stream: Iterator[str]) -> list[Any]:
  out = []
  for event in stream:
    body = event.removeprefix("data: ").strip()
    out.append(body if body == "[DONE]" else json.loads(body))
  return out


def _request(**overrides: Any) -> advisor.ChatRequest:
  fields: dict[str, Any] = {
    "message": "what next?",
    "term": TERM,
    "program_id": "computer-science-bs",
    "completed": ["CSCI-103L"],
  }
  return advisor.ChatRequest(**(fields | overrides))


def test_an_unavailable_model_says_why_and_still_offers_chips(conn):
  model = FakeModel([], reason="No key.")
  events = _events(advisor.stream(_request(message="hi"), conn, model))
  assert events[0] == {"token": "No key."}
  assert [c["view"] for c in events[1]["action_chips"]] == ["degree", "week"]
  assert events[-1] == "[DONE]"


def test_the_model_answers_from_the_brief(conn):
  model = FakeModel(["Take ", "CSCI 104L."])
  events = _events(advisor.stream(_request(), conn, model))
  assert "[Student brief]" in model.seen_system
  assert [e["token"] for e in events[:2]] == ["Take ", "CSCI 104L."]
  assert events[2]["unverified"] == []


def test_courses_no_source_mentions_are_flagged(conn):
  model = FakeModel(["Try CSCI 999 and CSCI 104L."])
  closing = _events(advisor.stream(_request(), conn, model))[-2]
  assert closing["unverified"] == ["CSCI 999"]


def test_tool_results_ground_courses_and_add_chips(conn):
  model = FakeModel(
    ["CSCI 445L fits."], call=("search_courses", {"query": "robot"})
  )
  closing = _events(advisor.stream(_request(), conn, model))[-2]
  assert "CSCI-445" in model.tool_output
  assert closing["unverified"] == []
  assert closing["action_chips"][0]["action"] == "search"


def test_model_errors_become_a_message(conn):
  @dataclasses.dataclass
  class Failing(FakeModel):
    def reply(
      self,
      system: str,
      history: Sequence[llm.Turn],
      message: str,
      tools: Sequence[llm.Tool],
      execute: llm.Execute,
    ) -> Iterator[str]:
      raise llm.ModelError("The advisor is busy.")
      yield ""

  events = _events(advisor.stream(_request(), conn, Failing([])))
  assert events[0] == {"token": "\n\nThe advisor is busy."}
  assert events[-1] == "[DONE]"
