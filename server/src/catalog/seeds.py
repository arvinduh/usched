"""Loads checked-in policy seeds: GE category rules and AP exam credit.

Seeds are the source of truth for data USC states only in prose (how many
courses each GE category needs, which AP exams earn what). They live as
reviewable JSON next to this module and are read at build time.
"""

import dataclasses
import json
import pathlib

from server.src.catalog import records


_DIR = pathlib.Path(__file__).resolve().parent / "seeds"


@dataclasses.dataclass(frozen=True)
class GeRule:
  """A GE category's policy, before the catalogue supplies its name."""

  code: str
  area: str
  required_count: int


@dataclasses.dataclass(frozen=True)
class ApSeed:
  """AP exams and the GE categories and courses they cover."""

  exams: list[records.ApExam]
  ge: list[records.ApExamGe]
  waivers: list[records.ApExamWaiver]


def ge_rules() -> list[GeRule]:
  """Reads seeds/ge_categories.json."""
  data = json.loads((_DIR / "ge_categories.json").read_text(encoding="utf-8"))
  return [
    GeRule(c["code"], c["area"], int(c["required_count"]))
    for c in data["categories"]
  ]


def ap_exams() -> ApSeed:
  """Reads seeds/ap_exams.json."""
  data = json.loads((_DIR / "ap_exams.json").read_text(encoding="utf-8"))
  seed = ApSeed([], [], [])
  for exam in data["exams"]:
    seed.exams.append(
      records.ApExam(
        id=exam["id"],
        name=exam["name"],
        min_score=int(exam["min_score"]),
        units=float(exam["units"]),
      )
    )
    seed.ge.extend(records.ApExamGe(exam["id"], g) for g in exam["ge"])
    seed.waivers.extend(
      records.ApExamWaiver(exam["id"], code) for code in exam["waives"]
    )
  return seed
