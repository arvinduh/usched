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

from server.src.catalog import codes
from server.src.data import catalog_models as m


def audit(
  categories: Sequence[m.GeCategory],
  course_ge: Mapping[str, Sequence[str]],
  completed: Sequence[str],
  exams: Sequence[m.ApExam],
  credits: Sequence[m.ApCredit],
) -> list[m.GeProgress]:
  """Fills each category's seats with completed courses and passed exams.

  Args:
    categories: GE categories with their area and seat count.
    course_ge: Course identity (codes.identity) to its categories.
    completed: Course codes the student took; order breaks ties.
    exams: AP exam policy.
    credits: The student's AP results; failing scores earn nothing.

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
  return [
    m.GeProgress(
      code=c.code,
      name=c.name,
      required_count=c.required_count,
      courses=[v for k, v in used.get(c.code, ()) if k == "course"],
      exams=[v for k, v in used.get(c.code, ()) if k == "exam"],
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
  exams: Sequence[m.ApExam], credits: Sequence[m.ApCredit]
) -> list[m.ApExam]:
  """The exams a student's scores earn credit for, in `credits` order."""
  by_id = {e.id: e for e in exams}
  return [
    by_id[c.exam_id]
    for c in credits
    if c.exam_id in by_id and c.score >= by_id[c.exam_id].min_score
  ]


def earned_units(
  progress: Sequence[m.GeProgress],
  units: Mapping[str, m.Units],
  exams: Sequence[m.ApExam],
) -> float:
  """Units of the distinct courses and exams filling GE seats.

  Args:
    progress: A GE audit's result.
    units: Course identity to units; a variable-unit course counts its
      minimum, and courses missing here count nothing.
    exams: AP exam policy, for exam units.
  """
  courses = {codes.identity(c) for p in progress for c in p.courses}
  used_exams = {e for p in progress for e in p.exams}
  return sum(units[c].min for c in courses if c in units) + sum(
    e.units for e in exams if e.id in used_exams
  )
