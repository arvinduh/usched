"""Audits General Education progress from completed courses and AP exams.

USC's rule: a course (or exam) may count once in each area, so one course
can fill a Core Literacy (GE-A..F) and a Global Perspective (GE-G, H) at
once but never two Core categories. Within an area this is a bipartite
matching between credits and category seats; a maximum matching fills
the most seats, where a greedy pass can strand a category. Policy comes
from the catalog (categories, exams); this module is pure.
"""

import collections
from collections.abc import Mapping, Sequence

from server import config
from server.db import models
from server.db.ingest import codes


def audit(
  categories: Sequence[models.GeCategory],
  course_ge: Mapping[str, Sequence[str]],
  completed: Sequence[str],
  exams: Sequence[models.ApExam],
  credits: Sequence[models.ApCredit],
  counted: Mapping[str, int] | None = None,
) -> list[models.GeProgress]:
  """Fills each category's seats with completed courses and passed exams.

  Args:
    categories: GE categories with their area and seat count.
    course_ge: Course identity (codes.identity) to its categories.
    completed: Course codes the student took; order breaks ties.
    exams: AP exam policy.
    credits: The student's AP results; failing scores earn nothing.
    counted: Seats the student counted by hand per category, such as
      transfer courses the catalog cannot place. They fill only seats
      courses and exams left open.

  Returns:
    Progress per category, in `categories` order.
  """
  # A credit is ("course", code) or ("exam", id) with the categories it fits.
  credit_ge: list[tuple[tuple[str, str], Sequence[str]]] = [
    (("exam", e.id), e.ge) for e in passed(exams, credits)
  ]
  credit_ge += [
    (("course", code), course_ge.get(codes.identity(code), ()))
    for code in completed
  ]
  filled: dict[str, list[int]] = collections.defaultdict(list)
  for area in {c.area for c in categories}:
    seats = [
      c.code
      for c in categories
      if c.area == area
      for _ in range(c.required_count)
    ]
    for seat, credit in _match(seats, [ge for _, ge in credit_ge]).items():
      filled[seats[seat]].append(credit)
  used = {
    code: [credit_ge[i][0] for i in sorted(indexes)]
    for code, indexes in filled.items()
  }
  counted = counted or {}
  return [
    models.GeProgress(
      code=c.code,
      name=c.name,
      area=c.area,
      required_count=c.required_count,
      courses=[v for k, v in used.get(c.code, ()) if k == "course"],
      exams=[v for k, v in used.get(c.code, ()) if k == "exam"],
      counted=max(
        0,
        min(counted.get(c.code, 0), c.required_count - len(filled[c.code])),
      ),
    )
    for c in categories
  ]


def _match(
  seats: Sequence[str], fits: Sequence[Sequence[str]]
) -> dict[int, int]:
  """Maximum bipartite matching of credits to seats (Kuhn's algorithm).

  `fits[i]` lists the categories credit i counts for. Returns seat index
  to the index of the credit filling it. A credit fills at most one seat,
  which is what limits it to one category per area.
  """
  owner: dict[int, int] = {}  # Seat index to credit index.

  def place(credit: int, seen: set[int]) -> bool:
    for seat, code in enumerate(seats):
      if code not in fits[credit] or seat in seen:
        continue
      seen.add(seat)
      if seat not in owner or place(owner[seat], seen):
        owner[seat] = credit
        return True
    return False

  for i in range(len(fits)):
    place(i, set())
  return owner


def passed(
  exams: Sequence[models.ApExam], credits: Sequence[models.ApCredit]
) -> list[models.ApExam]:
  """The exams a student's scores earn credit for, in `credits` order."""
  by_id = {e.id: e for e in exams}
  return [
    by_id[c.exam_id]
    for c in credits
    if c.exam_id in by_id and c.score >= by_id[c.exam_id].min_score
  ]


def counted_units(progress: Sequence[models.GeProgress]) -> float:
  """Units of the GE courses the student counted by hand.

  Each counted Core or Global seat is one course of GE_COURSE_UNITS. A
  seminar seat earns nothing: the seminar is also a Core course.
  """
  return config.GE_COURSE_UNITS * sum(
    p.counted for p in progress if p.area != "seminar"
  )


def earned_units(
  progress: Sequence[models.GeProgress],
  units: Mapping[str, models.Units],
  exams: Sequence[models.ApExam],
) -> float:
  """Units of the distinct courses, exams, and hand counts filling GE seats.

  Args:
    progress: A GE audit's result.
    units: Course identity to units; a variable-unit course counts its
      minimum, and courses missing here count nothing.
    exams: AP exam policy, for exam units.
  """
  courses = {codes.identity(c) for p in progress for c in p.courses}
  used_exams = {e for p in progress for e in p.exams}
  return (
    sum(units[c].min for c in courses if c in units)
    + sum(e.units for e in exams if e.id in used_exams)
    + counted_units(progress)
  )


def required_units(
  progress: Sequence[models.GeProgress], earned: float
) -> float:
  """The fewest GE units that can meet every category, given `earned`.

  One more course fills at most one open seat per area, so the area with
  the most open seats decides how many courses are left.
  """
  open_seats: dict[str, int] = collections.defaultdict(int)
  for p in progress:
    open_seats[p.area] += max(0, p.required_count - p.filled)
  return earned + config.GE_COURSE_UNITS * max(open_seats.values(), default=0)
