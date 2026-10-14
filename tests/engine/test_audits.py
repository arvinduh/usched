"""Tests for which students the audits hold to GE."""

import pytest

from server.db import models
from server.engine import audits


def _program(kind: str, degree_type: str | None) -> models.ProgramSummary:
  return models.ProgramSummary(
    id="p",
    title="P",
    name="P",
    emphasis=None,
    kind=kind,
    degree_type=degree_type,
    school=None,
    total_units=None,
    total_units_stated=False,
  )


@pytest.mark.parametrize("degree_type", ["BS", "BA", "BFA", "BS/MS", None])
def test_undergraduates_owe_general_education(degree_type):
  assert audits.needs_general_education(_program("degree", degree_type))


@pytest.mark.parametrize(
  "degree_type", ["MS", "MBA", "LLM", "PhD", "MD", "DPT"]
)
def test_graduate_degrees_owe_no_general_education(degree_type):
  assert not audits.needs_general_education(_program("degree", degree_type))


def test_no_program_or_a_minor_keeps_general_education():
  assert audits.needs_general_education(None)
  assert audits.needs_general_education(_program("minor", None))
