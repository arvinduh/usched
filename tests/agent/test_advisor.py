"""Tests for the advisor's tools, brief, and stream, with the model faked."""

import dataclasses
import json
from collections.abc import Iterator
from typing import Any

import pytest

from server.agent import _brief, _chips, _tools, advisor
from server.db import models


TERM = 20271


def test_search_lists_matches_with_search_chips(conn):
  result = _tools.search_courses(conn, TERM, "data structures")
  assert result.content.startswith("CSCI-104L: Data Structures (4 units)")
  assert (
    _chips.Search(label="Show CSCI-104L", query="CSCI-104L") in result.chips
  )


def test_details_include_requisites_seats_and_an_enroll_chip(conn):
  result = _tools.get_course_details(conn, TERM, "csci-104l")
  assert "Prerequisites:" in result.content
  assert "D-clearance" in result.content
  assert any(isinstance(c, _chips.EnrollSection) for c in result.chips)
  missing = _tools.get_course_details(conn, TERM, "NOPE-1")
  assert missing.content == "NOPE-1 is not offered this term."


def test_solve_offers_each_option_as_a_proposal(conn):
  result = _tools.solve_schedule(
    conn, TERM, [], ["CSCI-104L"], excluded_days=["friday"]
  )
  assert result.content.startswith("Option 1")
  proposals = [c for c in result.chips if isinstance(c, _chips.ProposeSchedule)]
  assert proposals and proposals[0].section_ids
  absent = _tools.solve_schedule(conn, TERM, [], ["CSCI-104L", "NOPE-1"])
  assert absent.content == "Not offered this term: NOPE-1."


def test_solve_applies_filters_and_names_what_blocks_a_week(conn):
  # Only 104L's group-B lecture (29989, Tue/Thu 8:00) ends by noon.
  morning = _tools.solve_schedule(
    conn, TERM, [], ["CSCI-104L"], latest_end_time="12:00", goals=["easy"]
  )
  proposals = [
    c for c in morning.chips if isinstance(c, _chips.ProposeSchedule)
  ]
  assert proposals and all("29989" in p.section_ids for p in proposals)
  assert "days" in morning.content and "min between classes" in morning.content
  blocked = _tools.solve_schedule(
    conn,
    TERM,
    [],
    ["CSCI-104L"],
    excluded_days=["Tuesday", "Thursday"],
    latest_end_time="12:00",
  )
  assert blocked.chips == []
  # Group A's quiz meets Thursday too, so only the days off block it.
  assert "Dropping the days off would allow one" in blocked.content
  assert (
    "Unknown goals: fun"
    in _tools.solve_schedule(
      conn, TERM, [], ["CSCI-104L"], goals=["fun"]
    ).content
  )


def test_solve_fits_courses_around_the_week_and_keeps_it(conn):
  # CHEM 251x's 17367 meets Mon 14:00, as does CSCI 104L's lecture 29905.
  result = _tools.solve_schedule(conn, TERM, ["17367"], ["CSCI-104L"])
  proposals = [c for c in result.chips if isinstance(c, _chips.ProposeSchedule)]
  assert proposals
  for proposal in proposals:
    assert "17367" in proposal.section_ids
    assert "29905" not in proposal.section_ids
  assert "Keeps your week: CHEM-251x 17367" in result.content


def test_edit_week_swaps_removes_and_previews_the_result(conn):
  # 29989 is CSCI 104L's group-B lecture; it swaps out lecture 29905.
  result = _tools.edit_week(
    conn,
    TERM,
    ["17367", "29905"],
    add_sections=["29989"],
    remove_courses=["CHEM 251x"],
  )
  (proposal,) = result.chips
  assert isinstance(proposal, _chips.ProposeSchedule)
  assert proposal.section_ids == ["29989"]
  # Group A's lecture comes with a lab and a quiz to pick.
  partial = _tools.edit_week(conn, TERM, [], add_sections=["29905"])
  assert "CSCI-104L still needs a Lab and a Quiz" in partial.content
  unchanged = _tools.edit_week(conn, TERM, ["17367"], remove_sections=["1"])
  assert unchanged.content == "That leaves the week unchanged."
  assert _tools.edit_week(conn, TERM, [], add_sections=["0"]).content == (
    "Not sections this term: 0."
  )


def test_mark_taken_records_only_catalog_courses(conn):
  result = _tools.mark_taken(conn, TERM, ["csci 103l", "FAKE 999"])
  assert result.chips == [
    _chips.MarkTaken(label="Marked CSCI-103L taken", course_codes=["CSCI-103L"])
  ]
  assert result.content == "Marked taken: CSCI-103L. Not USC courses: FAKE 999."


def test_execute_reports_unknown_tools_and_bad_arguments(conn):
  assert "Unknown tool" in _tools.execute("nope", {}, conn, TERM, []).content
  bad = _tools.execute("search_courses", {"q": "x"}, conn, TERM, [])
  assert bad.content.startswith("Bad arguments for search_courses")


STUDENT = _brief.Student(
  term=TERM,
  program_id="computer-science-bs",
  section_ids=["29905"],
  shortlisted=["CSCI-420"],
  completed=["CSCI-103L"],
  ap_credits=[models.ApCredit(exam_id="AP_CALC_BC", score=5)],
)


def test_the_brief_states_progress_next_steps_and_the_week(conn):
  facts = _brief.build(conn, STUDENT)
  assert "Planning: Spring 2027" in facts.text
  assert "Program: Computer Science (BS)" in facts.text
  assert "Open GE categories:" in facts.text
  # The scheduled lecture still needs its lab and quiz.
  assert "CSCI-104L still needs a Lab and a Quiz" in facts.text
  # Courses already scheduled are not suggested again.
  (next_line,) = [
    line for line in facts.text.splitlines() if line.startswith("Can take")
  ]
  assert "CSCI-104" not in next_line
  assert {"CSCI-104", "CSCI-420", "CSCI-103"} <= facts.grounded


def test_the_brief_counts_ge_seats_the_student_filled_by_hand(conn):
  every = {f"GE-{letter}": 9 for letter in "ABCDEFGH"}
  text = _brief.build(conn, dataclasses.replace(STUDENT, ge_counted=every)).text
  assert "Open GE categories: none" in text


def test_the_brief_says_what_is_on_screen_and_the_other_schedules(conn):
  student = dataclasses.replace(
    STUDENT,
    variants=[_brief.Variant("B", ["17367"])],
    screen=_brief.Screen(
      page="planner",
      open_course="CSCI-445Lx",
      proposal=_brief.Variant("Option 2", ["30386", "29910"]),
    ),
  )
  text = _brief.build(conn, student).text
  assert "Other schedule B: CHEM-251x (17367)" in text
  assert "On screen: the planner" in text
  assert "Open course: CSCI-445Lx" in text
  assert "proposal Option 2: CSCI-445Lx (30386, 29910), not yet kept" in text
  assert "CHEM-251" in _brief.build(conn, student).grounded


def test_a_student_without_a_program_still_gets_a_brief(conn):
  facts = _brief.build(conn, dataclasses.replace(STUDENT, program_id=None))
  assert "Program: not chosen" in facts.text
  assert "Can take next" not in facts.text


@pytest.mark.parametrize(
  ("reply", "grounded", "expected"),
  [
    (
      "Take CSCI 104L, then MATH-225g. CSCI 999 also looks fun.",
      {"CSCI-104", "MATH-225"},
      ["CSCI 999"],
    ),
    ("No courses here.", {"CSCI-104", "MATH-225"}, []),
    # Never named by a source, but real: the catalog knows it.
    ("CSCI 445L is a fine elective.", set(), []),
  ],
)
def test_the_reply_check_flags_only_courses_no_source_or_catalog_backs(
  conn, reply: str, grounded: set[str], expected: list[str]
):
  assert advisor.unverified(reply, grounded, conn) == expected


def test_history_remembers_what_each_reply_offered(conn):
  turn = advisor.ChatTurn(
    role="assistant",
    content="Two ways to fit it.",
    action_chips=[
      _chips.ProposeSchedule(
        label="Preview option 1", name="Option 1", section_ids=["17367"]
      ),
      _chips.WatchCourse(label="Save", course_code="CSCI-104L"),
      _chips.Search(label="Show MATH-226", query="MATH-226"),
    ],
  )
  assert advisor.remembered(conn, TERM, turn) == (
    "Two ways to fit it.\n"
    "[Your reply offered: Option 1: CHEM-251x (17367); saving CSCI-104L]"
  )
  plain = advisor.ChatTurn(role="user", content="hi")
  assert advisor.remembered(conn, TERM, plain) == "hi"


@pytest.mark.parametrize(
  ("chips", "expected"),
  [
    (
      [
        _chips.Search(label="Show CSCI-104L", query="CSCI-104L"),
        _chips.Search(label="Show CSCI-104L", query="CSCI-104L"),
      ],
      [_chips.Search(label="Show CSCI-104L", query="CSCI-104L")],
    ),
    ([], []),
  ],
)
def test_chips_come_only_from_what_the_model_did(chips, expected):
  assert advisor.closing_chips(chips) == expected


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
