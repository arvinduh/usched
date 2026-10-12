"""Tests for the advisor's tools and stream, with the model faked."""

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from server.src.agent import advisor, chips, ollama, tools
from server.src.data import catalog_db


STUDENT = tools.Student(
  term=20271, program_id="computer-science-bs", completed=("CSCI-103L",)
)


@pytest.fixture(scope="module")
def conn(catalog_path) -> Iterator[sqlite3.Connection]:
  conn = catalog_db.CatalogDb(catalog_path).connect()
  yield conn
  conn.close()


def test_search_lists_matches_with_search_chips(conn):
  result = tools.search_courses(conn, STUDENT, "data structures")
  assert result.content.startswith("CSCI-104L: Data Structures (4 units)")
  assert chips.Search(label="Show CSCI-104L", query="CSCI-104L") in result.chips


def test_details_include_requisites_seats_and_an_enroll_chip(conn):
  result = tools.get_course_details(conn, STUDENT, "csci-104l")
  assert "Prerequisites:" in result.content
  assert "D-clearance" in result.content
  assert any(isinstance(c, chips.EnrollSection) for c in result.chips)
  missing = tools.get_course_details(conn, STUDENT, "NOPE-1")
  assert missing.content == "NOPE-1 is not offered this term."


def test_solve_offers_each_option_as_a_proposal(conn):
  result = tools.solve_schedule(
    conn, STUDENT, ["CSCI-104L"], excluded_days=["friday"]
  )
  assert result.content.startswith("Option 1")
  proposals = [c for c in result.chips if isinstance(c, chips.ProposeSchedule)]
  assert proposals and proposals[0].section_ids
  absent = tools.solve_schedule(conn, STUDENT, ["CSCI-104L", "NOPE-1"])
  assert absent.content == "Not offered this term: NOPE-1."


def test_audit_summarizes_progress(conn):
  result = tools.audit_program(conn, STUDENT)
  assert result.content.startswith("Computer Science (BS): 4/128 units")
  assert chips.Show(label="Open degree", view="degree") in result.chips
  nobody = tools.Student(term=20271, program_id=None, completed=())
  assert "not chosen" in tools.audit_program(conn, nobody).content


def test_execute_reports_unknown_tools_and_bad_arguments(conn):
  assert "Unknown tool" in tools.execute("nope", {}, conn, STUDENT).content
  bad = tools.execute("watch_course", {"code": "X"}, conn, STUDENT)
  assert bad.content.startswith("Bad arguments for watch_course")


def _events(stream: Iterator[str]) -> list[Any]:
  out = []
  for event in stream:
    body = event.removeprefix("data: ").strip()
    out.append(body if body == "[DONE]" else json.loads(body))
  return out


def test_offline_stream_still_ends_with_chips(conn, monkeypatch):
  monkeypatch.setattr(ollama, "is_ollama_available", lambda: False)
  request = advisor.ChatRequest(message="hi", term=20271)
  events = _events(advisor.stream(request, conn))
  assert "offline" in events[0]["token"]
  assert [c["view"] for c in events[1]["action_chips"]] == ["degree", "week"]
  assert events[-1] == "[DONE]"


def test_tool_calls_run_between_two_passes(conn, monkeypatch):
  passes: list[list[dict[str, Any]]] = []

  def fake_chat(messages, tool_specs=None):
    passes.append(list(messages))
    if tool_specs is not None:
      yield {
        "tool_calls": [
          {
            "function": {
              "name": "watch_course",
              "arguments": {"course_code": "csci-104l"},
            }
          }
        ]
      }
    else:
      yield {"content": "Saved it."}

  monkeypatch.setattr(ollama, "is_ollama_available", lambda: True)
  monkeypatch.setattr(ollama, "is_model_downloaded", lambda: True)
  monkeypatch.setattr(ollama, "stream_ollama_chat", fake_chat)
  request = advisor.ChatRequest(
    message="save 104", term=20271, completed=["CSCI-103L"]
  )
  events = _events(advisor.stream(request, conn))
  assert events[0] == {"token": "Saved it."}
  assert events[1]["action_chips"][0] == {
    "action": "watch_course",
    "label": "Shortlist CSCI-104L",
    "course_code": "CSCI-104L",
  }
  assert passes[1][-1]["role"] == "tool"
  assert "Spring 2027" in passes[0][0]["content"]
