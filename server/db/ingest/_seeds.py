"""Loads checked-in policy seeds: GE rules, AP credit, degree minimums.

Seeds are the source of truth for data USC states only in prose (how many
courses each GE category needs, which AP exams earn what). They live as
reviewable JSON in server/seeds and are read at build time.
"""

import dataclasses
import json

from server import config
from server.db import models


@dataclasses.dataclass(frozen=True)
class GeRule:
  """A GE category's policy, before the catalogue supplies its name."""

  code: str
  area: str
  required_count: int


@dataclasses.dataclass(frozen=True)
class ApSeed:
  """AP exams and the GE categories and courses they cover."""

  exams: list[models.ApExamRow]
  ge: list[models.ApExamGeRow]
  waivers: list[models.ApExamWaiverRow]


def ge_rules() -> list[GeRule]:
  """Reads seeds/ge_categories.json."""
  data = json.loads(
    (config.SEEDS_DIR / "ge_categories.json").read_text(encoding="utf-8")
  )
  return [
    GeRule(c["code"], c["area"], int(c["required_count"]))
    for c in data["categories"]
  ]


def bachelor_minimum_units() -> float:
  """Reads seeds/degree_policy.json: units any bachelor's degree requires."""
  policy_file = config.SEEDS_DIR / "degree_policy.json"
  if not policy_file.is_file():
    return config.DEFAULT_BACHELOR_MINIMUM_UNITS
  data = json.loads(policy_file.read_text(encoding="utf-8"))
  return float(
    data.get("bachelor_minimum_units", config.DEFAULT_BACHELOR_MINIMUM_UNITS)
  )


def ap_exams() -> ApSeed:
  """Reads seeds/ap_exams.json."""
  data = json.loads(
    (config.SEEDS_DIR / "ap_exams.json").read_text(encoding="utf-8")
  )
  seed = ApSeed([], [], [])
  for exam in data["exams"]:
    seed.exams.append(
      models.ApExamRow(
        id=exam["id"],
        name=exam["name"],
        min_score=int(exam["min_score"]),
        units=float(exam["units"]),
      )
    )
    seed.ge.extend(models.ApExamGeRow(exam["id"], g) for g in exam["ge"])
    seed.waivers.extend(
      models.ApExamWaiverRow(exam["id"], code) for code in exam["waives"]
    )
  return seed


__all__ = [
  "ApSeed",
  "GeRule",
  "ap_exams",
  "bachelor_minimum_units",
  "ge_rules",
]
