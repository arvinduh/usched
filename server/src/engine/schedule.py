"""Builds conflict-free weekly schedules from courses' sections.

A course is registered as a bundle: one section of each type that shares
a link code (lecture, lab, and quiz with letter A, say). This module turns
sections into bundles, ranks them against a student's preferences, and
searches bundle combinations for ones whose meetings never overlap. It
works on API models only; loading courses belongs to catalog_db.
"""

import collections
import dataclasses
import itertools
import statistics
from collections.abc import Iterable, Sequence

from server.src.data import catalog_models as m


_PER_TYPE = 4  # Best sections kept per type before bundling.
_PER_COURSE = 8  # Best bundles kept per course before combining.
_NEUTRAL_RATING = 3.0


@dataclasses.dataclass(frozen=True)
class Preferences:
  """What a student wants from a schedule; every field is optional.

  Attributes:
    excluded_days: Days with no class.
    earliest_start: Minutes after midnight before which nothing starts.
    latest_end: Minutes after midnight after which nothing ends.
    preferred: Lowercase name fragments of instructors to favor.
    excluded: Lowercase name fragments of instructors to avoid.
    min_rating: Lowest acceptable RateMyProfessors rating.
  """

  excluded_days: frozenset[m.Weekday] = frozenset()
  earliest_start: int | None = None
  latest_end: int | None = None
  preferred: tuple[str, ...] = ()
  excluded: tuple[str, ...] = ()
  min_rating: float | None = None


NO_PREFERENCES = Preferences()


@dataclasses.dataclass(frozen=True)
class Schedule:
  """A conflict-free set of sections covering every requested course.

  Attributes:
    sections: One bundle per course, flattened.
    average_rating: Mean rating of rated instructors, if any are rated.
    violations: Sections breaking a preference because no section of
      their type met it.
    score: Higher is better.
  """

  sections: tuple[m.Section, ...]
  average_rating: float | None
  violations: int
  score: float


def overlaps(a: m.Section, b: m.Section) -> bool:
  """Whether two sections meet at the same time; TBA meetings never do."""
  return any(_meetings_overlap(x, y) for x in a.meetings for y in b.meetings)


def _meetings_overlap(x: m.Meeting, y: m.Meeting) -> bool:
  if None in (x.start_minute, x.end_minute, y.start_minute, y.end_minute):
    return False
  assert x.start_minute is not None and x.end_minute is not None
  assert y.start_minute is not None and y.end_minute is not None
  return (
    not set(x.days).isdisjoint(y.days)
    and x.start_minute < y.end_minute
    and y.start_minute < x.end_minute
  )


def _ratings(sections: Iterable[m.Section]) -> list[float]:
  return [
    i.rmp.rating
    for s in sections
    for i in s.instructors
    if i.rmp is not None and i.rmp.rating is not None
  ]


def _teaches(section: m.Section, fragments: Sequence[str]) -> bool:
  return any(
    f in i.name.lower() for i in section.instructors for f in fragments
  )


def _violates(section: m.Section, prefs: Preferences) -> bool:
  for meeting in section.meetings:
    if prefs.excluded_days.intersection(meeting.days):
      return True
    start, end = meeting.start_minute, meeting.end_minute
    if prefs.earliest_start is not None and start is not None:
      if start < prefs.earliest_start:
        return True
    if prefs.latest_end is not None and end is not None:
      if end > prefs.latest_end:
        return True
  if _teaches(section, prefs.excluded):
    return True
  low = prefs.min_rating
  return low is not None and any(r < low for r in _ratings([section]))


def _section_rank(section: m.Section, prefs: Preferences) -> tuple[bool, float]:
  ratings = _ratings([section])
  rating = statistics.fmean(ratings) if ratings else _NEUTRAL_RATING
  return (_teaches(section, prefs.preferred), rating)


def bundles(
  sections: Sequence[m.Section], prefs: Preferences = NO_PREFERENCES
) -> list[tuple[m.Section, ...]]:
  """Lists a course's registrable bundles, best first.

  A bundle takes one section of every type its link group offers. A link
  group is the sections sharing a link code plus those without one, which
  pair with any group ("Register for 1 Lecture and the Discussion"). Within
  a type, sections meeting every preference are preferred; when none do,
  the type's sections are kept anyway and later count as violations.
  Cancelled sections and bundles that conflict internally are dropped.
  """
  live = [s for s in sections if not s.is_cancelled]
  links = sorted({s.link_code for s in live if s.link_code is not None})
  found: dict[frozenset[str], tuple[m.Section, ...]] = {}
  for link in links or [None]:
    by_type: dict[str, list[m.Section]] = collections.defaultdict(list)
    for s in live:
      if s.link_code in (None, link):
        by_type[s.type].append(s)
    if not by_type:
      continue
    choices = []
    for typed in by_type.values():
      ok = [s for s in typed if not _violates(s, prefs)] or typed
      ok.sort(key=lambda s: _section_rank(s, prefs), reverse=True)
      choices.append(ok[:_PER_TYPE])
    for combo in itertools.product(*choices):
      if not any(overlaps(a, b) for a, b in itertools.combinations(combo, 2)):
        found.setdefault(frozenset(s.id for s in combo), combo)
  return sorted(found.values(), key=lambda b: _score(b, prefs), reverse=True)


def _score(sections: Sequence[m.Section], prefs: Preferences) -> float:
  ratings = _ratings(sections)
  rating = statistics.fmean(ratings) if ratings else _NEUTRAL_RATING
  preferred = sum(_teaches(s, prefs.preferred) for s in sections)
  violations = sum(_violates(s, prefs) for s in sections)
  return 2.0 * rating + 5.0 * preferred - 10.0 * violations


def solve(
  courses: Sequence[m.Course],
  prefs: Preferences = NO_PREFERENCES,
  limit: int = 3,
  around: Sequence[m.Section] = (),
) -> list[Schedule]:
  """Finds the best conflict-free schedules that take every course.

  Sections in `around` are fixed (the rest of the student's week): no
  bundle may overlap them, and they are not part of the result. Courses
  without a registrable bundle that fits make the problem unsolvable, so
  the result is empty. Each course contributes its best few fitting
  bundles, which bounds the search to `_PER_COURSE ** len(courses)`
  combinations.
  """
  options = [
    [
      b
      for b in bundles(c.sections, prefs)
      if not any(overlaps(s, f) for s in b for f in around)
    ][:_PER_COURSE]
    for c in courses
  ]
  if not options or not all(options):
    return []
  found: list[Schedule] = []
  for combo in itertools.product(*options):
    chosen = [s for bundle in combo for s in bundle]
    if any(
      overlaps(a, b)
      for i, x in enumerate(combo)
      for y in combo[i + 1 :]
      for a in x
      for b in y
    ):
      continue
    ratings = _ratings(chosen)
    found.append(
      Schedule(
        sections=tuple(chosen),
        average_rating=round(statistics.fmean(ratings), 2) if ratings else None,
        violations=sum(_violates(s, prefs) for s in chosen),
        score=round(_score(chosen, prefs), 2),
      )
    )
  found.sort(key=lambda s: s.score, reverse=True)
  return found[:limit]


def missing_types(course: m.Course, chosen: Sequence[m.Section]) -> list[str]:
  """Section types the chosen sections' link group still needs.

  The group is fixed by the first chosen section with a link code; until
  then every type the course offers counts.
  """
  link = next((s.link_code for s in chosen if s.link_code is not None), None)
  required = dict.fromkeys(
    s.type
    for s in course.sections
    if not s.is_cancelled and (link is None or s.link_code in (None, link))
  )
  for s in chosen:
    required.pop(s.type, None)
  return list(required)
