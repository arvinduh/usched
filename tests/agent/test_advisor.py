"""Tests for the advisor's tools, brief, and stream, with the model faked."""

import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from server.src.agent import advisor, brief, chips, tools
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
    conn, TERM, [], ["CSCI-104L"], excluded_days=["friday"]
  )
  assert result.content.startswith("Option 1")
  proposals = [c for c in result.chips if isinstance(c, chips.ProposeSchedule)]
  assert proposals and proposals[0].section_ids
  absent = tools.solve_schedule(conn, TERM, [], ["CSCI-104L", "NOPE-1"])
  assert absent.content == "Not offered this term: NOPE-1."


def test_solve_fits_courses_around_the_week_and_keeps_it(conn):
  # CHEM 251x's 17367 meets Mon 14:00, as does CSCI 104L's lecture 29905.
  result = tools.solve_schedule(conn, TERM, ["17367"], ["CSCI-104L"])
  proposals = [c for c in result.chips if isinstance(c, chips.ProposeSchedule)]
  assert proposals
  for proposal in proposals:
    assert "17367" in proposal.section_ids
    assert "29905" not in proposal.section_ids
  assert "Keeps your week: CHEM-251x 17367" in result.content


def test_execute_reports_unknown_tools_and_bad_arguments(conn):
  assert "Unknown tool" in tools.execute("nope", {}, conn, TERM, []).content
  bad = tools.execute("search_courses", {"q": "x"}, conn, TERM, [])
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


def test_the_reply_check_flags_only_courses_no_source_or_catalog_backs(conn):
  grounded = {"CSCI-104", "MATH-225"}
  reply = "Take CSCI 104L, then MATH-225g. CSCI 999 also looks fun."
  assert advisor.unverified(reply, grounded, conn) == ["CSCI 999"]
  assert advisor.unverified("No courses here.", grounded, conn) == []
  # Never named by a source, but real: the catalog knows it.
  assert advisor.unverified("CSCI 445L is a fine elective.", set(), conn) == []


def test_closing_chips_prefer_tools_then_next_steps():
  search = chips.Search(label="Show CSCI-104L", query="CSCI-104L")
  assert advisor.closing_chips([search], ["MATH-226"]) == [
    search,
    chips.Search(label="Show MATH-226", query="MATH-226"),
  ]
  assert advisor.closing_chips([], []) == []


def _events(stream: Iterator[str]) -> list[Any]:
  out = []
  for event in stream:
    body = event.removeprefix("data: ").strip()
    out.append(body if body == "[DONE]" else json.loads(body))
  return out


@pytest.mark.live
def test_live_advisor_answers_from_the_brief(conn, live_model):
  """The real advisor answers a planning question without inventing courses."""
  request = advisor.ChatRequest(
    message="Which classes could I take next term?",
    term=TERM,
    program_id="computer-science-bs",
    completed=["CSCI-103L"],
  )
  events = _events(advisor.stream(request, conn, live_model))
  reply = "".join(
    e["token"] for e in events if isinstance(e, dict) and "token" in e
  )
  closing = events[-2]
  assert reply.strip()
  assert closing["unverified"] == []
  assert events[-1] == "[DONE]"
