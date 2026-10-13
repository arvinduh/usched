"""Live evaluations: real questions to the configured advisor, judged on facts.

Each case asks the real model a question a student would, against the
fixture catalog, and checks what the reply did rather than how it reads:
the schedules it proposed exist, have no conflicts, and keep what they
should; the edits and records it made are the ones asked for; and it named
no course the catalog lacks. They spend quota, so they run only on
request: `npm run test:live`.
"""

import dataclasses
import json
from collections.abc import Sequence
from typing import Any

import pytest

from server.src.agent import advisor, brief, chips
from server.src.data import catalog_db
from server.src.engine import schedule


pytestmark = pytest.mark.live

TERM = 20271
CHEM_251 = "17367"  # Mon 14:00.
CSCI_104_LECTURE_A = "29905"  # Mon, Wed 14:00; clashes with CHEM 251x.


@dataclasses.dataclass(frozen=True)
class Outcome:
  """What one reply did."""

  text: str
  chips: list[dict[str, Any]]
  unverified: list[str]

  def proposals(self) -> list[list[str]]:
    return [
      c["section_ids"] for c in self.chips if c["action"] == "propose_schedule"
    ]

  def taken(self) -> list[str]:
    return [
      code
      for c in self.chips
      if c["action"] == "mark_taken"
      for code in c["course_codes"]
    ]


def _ask(conn, model, message: str, **fields: Any) -> Outcome:
  request = advisor.ChatRequest(
    message=message,
    term=TERM,
    program_id=fields.pop("program_id", "computer-science-bs"),
    **fields,
  )
  text: list[str] = []
  closing: dict[str, Any] = {}
  for event in advisor.stream(request, conn, model):
    body = event.removeprefix("data: ").strip()
    if body == "[DONE]":
      break
    payload = json.loads(body)
    if "token" in payload:
      text.append(payload["token"])
    else:
      closing = payload
  outcome = Outcome(
    "".join(text), closing["action_chips"], closing["unverified"]
  )
  assert outcome.unverified == [], f"named unknown courses: {outcome.text}"
  return outcome


def _assert_valid_week(conn, section_ids: Sequence[str]) -> None:
  """Every section exists this term and no two overlap."""
  sections = catalog_db.sections(conn, TERM, list(section_ids))
  assert {s.id for s in sections} == set(section_ids)
  for i, a in enumerate(sections):
    for b in sections[i + 1 :]:
      assert not schedule.overlaps(a, b), f"{a.id} overlaps {b.id}"


def _courses(conn, section_ids: Sequence[str]) -> set[str]:
  return {
    s.course_code for s in catalog_db.sections(conn, TERM, list(section_ids))
  }


def test_fitting_a_course_around_the_week(conn, live_model):
  out = _ask(
    conn, live_model, "Fit CSCI 104L into my week.", section_ids=[CHEM_251]
  )
  assert out.proposals(), out.text
  for week in out.proposals():
    _assert_valid_week(conn, week)
    assert CHEM_251 in week
    assert "CSCI-104L" in _courses(conn, week)


def test_a_schedule_honors_a_free_day(conn, live_model):
  out = _ask(
    conn,
    live_model,
    "Build me a schedule with CSCI 104L and CSCI 445L. Keep Fridays free.",
  )
  assert out.proposals(), out.text
  for week in out.proposals():
    _assert_valid_week(conn, week)
    assert {"CSCI-104L", "CSCI-445Lx"} <= _courses(conn, week)
    for s in catalog_db.sections(conn, TERM, week):
      assert all("Fri" not in m.days for m in s.meetings), s.id


def test_dropping_a_course_edits_the_week(conn, live_model):
  out = _ask(
    conn,
    live_model,
    "Drop CHEM 251x from my week.",
    section_ids=[CHEM_251, CSCI_104_LECTURE_A],
  )
  (week,) = out.proposals()
  assert CHEM_251 not in week
  assert CSCI_104_LECTURE_A in week


def test_saying_what_was_taken_records_it(conn, live_model):
  out = _ask(conn, live_model, "I already took CSCI 103L last year.")
  assert "CSCI-103L" in out.taken(), out.text


def test_a_question_about_one_course_reads_its_details(conn, live_model):
  out = _ask(conn, live_model, "Tell me about CSCI 445L. Who teaches it?")
  assert "445" in out.text
  assert any(
    c["action"] in ("enroll_section", "watch_course") for c in out.chips
  )


def test_a_topic_search_finds_the_course(conn, live_model):
  out = _ask(conn, live_model, "Is there a robotics course this term?")
  assert "445" in out.text


def test_this_course_means_the_open_card(conn, live_model):
  out = _ask(
    conn,
    live_model,
    "Is this course a good fit for me?",
    screen=brief.Screen(open_course="CSCI-445Lx"),
  )
  assert "445" in out.text


def test_a_follow_up_refers_to_an_earlier_option(conn, live_model):
  option_2 = ["30386", "29910", CHEM_251]  # CSCI 445Lx, and CHEM 251x.
  history = [
    advisor.ChatTurn(role="user", content="Fit CSCI 445L into my week."),
    advisor.ChatTurn(
      role="assistant",
      content="Two options fit; option 2 keeps your Mondays light.",
      action_chips=[
        chips.ProposeSchedule(
          label="Preview option 1",
          name="Option 1",
          section_ids=["30386", "29911", CHEM_251],
        ),
        chips.ProposeSchedule(
          label="Preview option 2", name="Option 2", section_ids=option_2
        ),
      ],
    ),
  ]
  out = _ask(
    conn,
    live_model,
    "Take option 2, but drop CHEM 251x.",
    history=history,
    section_ids=[CHEM_251],
  )
  assert out.proposals(), out.text
  week = out.proposals()[-1]
  _assert_valid_week(conn, week)
  assert CHEM_251 not in week
  assert {"30386", "29910"} <= set(week)


def test_next_steps_name_only_real_courses(conn, live_model):
  out = _ask(
    conn,
    live_model,
    "What should I take next semester?",
    completed=["CSCI-103L", "CSCI-170"],
  )
  assert "104" in out.text
