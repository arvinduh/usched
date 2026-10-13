"""Tests for course identity keys."""

import pytest

from server.db.ingest import codes


@pytest.mark.parametrize(
  ("code", "key"),
  [
    ("CHEM-105aLg", "CHEM-105A"),
    ("CHEM-105A", "CHEM-105A"),
    ("CHEM-105bL", "CHEM-105B"),
    ("MATH-118gx", "MATH-118"),
    ("MATH-118xg", "MATH-118"),
    ("ACAD-490x", "ACAD-490"),
    ("ACCT-551T", "ACCT-551T"),
    ("CSCI-104L", "CSCI-104"),
    ("csci 104l", "CSCI-104"),
    ("AMST-101gmw", "AMST-101"),
    ("ARCH-102AL", "ARCH-102A"),
  ],
)
def test_attribute_letters_do_not_change_identity(code, key):
  assert codes.course_key(code) == key


@pytest.mark.parametrize("text", ["", "CS 1", "the 100 level", "CSCI-1040"])
def test_non_codes_have_no_key(text):
  assert codes.course_key(text) is None


def test_mentions_find_codes_in_prose():
  text = "Take CSCI 104L or CSCI-104 next, then MATH 225; skip the 100 level."
  assert codes.mentions(text) == {
    "CSCI-104": "CSCI 104L",
    "MATH-225": "MATH 225",
  }
