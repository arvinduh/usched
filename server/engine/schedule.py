"""Builds conflict-free weekly schedules from courses' sections.

A course is registered as a bundle: one section of each type that shares
a link code (lecture, lab, and quiz with letter A, say). This module turns
sections into bundles and searches bundle combinations for weeks whose
meetings never overlap. What a student wants comes in two kinds:

- Filters are hard: no class on a day off, nothing after 6, at most three
  days on campus, lunch kept free. A week breaking one is never offered.
- Goals are ranked: best ratings, then no breaks, say. Each scores a whole
  week from 0 to 1, and earlier goals weigh more, so the first decides and
  later ones break its ties.

When nothing meets every filter, `blockers` names the filters that, each
dropped alone, would let a week through. It works on API models only;
loading courses belongs to catalog_db.
"""

import collections
import dataclasses
import enum
import heapq
import itertools
import statistics
from collections.abc import Iterable, Sequence

from server.db import models


_PER_TYPE = 6  # Best sections kept per type before bundling.
_PER_COURSE = 24  # Best bundles kept per course before combining.
_BUDGET = 50_000  # Search nodes per solve; bounds the worst case.
_NEUTRAL = 3.0  # Rating and difficulty assumed for unrated instructors.
_PREFERRED_BONUS = 0.15  # Score per section taught by a favored instructor.


class Goal(enum.StrEnum):
  """Something to maximize across a week."""

  RATING = "rating"  # Highest-rated instructors.
  EASY = "easy"  # Lowest RateMyProfessors difficulty.
  COMPACT = "compact"  # Least time between classes on a day.
  FEWER_DAYS = "fewer_days"  # Fewest days on campus.
  LATE_START = "late_start"  # Days that start late.
  EARLY_END = "early_end"  # Days that end early.
  SEATS = "seats"  # Most open seats, for safer registration.


@dataclasses.dataclass(frozen=True)
class Window:
  """A weekly time to keep free, such as lunch, in minutes after midnight."""

  days: frozenset[models.Weekday]
  start: int
  end: int


@dataclasses.dataclass(frozen=True)
class Filters:
  """What a week must satisfy; every field is optional.

  Attributes:
    excluded_days: Days with no class.
    earliest_start: Minutes after midnight before which nothing starts.
    latest_end: Minutes after midnight after which nothing ends.
    keep_free: Times with no class.
    max_days: Most days with a class, counting the fixed week.
    excluded: Lowercase name fragments of instructors to avoid.
    min_rating: Lowest acceptable RateMyProfessors rating.
    open_seats_only: Only sections with a seat left.
  """

  excluded_days: frozenset[models.Weekday] = frozenset()
  earliest_start: int | None = None
  latest_end: int | None = None
  keep_free: tuple[Window, ...] = ()
  max_days: int | None = None
  excluded: tuple[str, ...] = ()
  min_rating: float | None = None
  open_seats_only: bool = False


# How a filter reads when it is what blocks every week.
_FILTER_NAMES = {
  "excluded_days": "the days off",
  "earliest_start": "the earliest start",
  "latest_end": "the latest end",
  "keep_free": "the times kept free",
  "max_days": "the limit on days",
  "excluded": "the instructors to avoid",
  "min_rating": "the minimum rating",
  "open_seats_only": "open seats only",
}


@dataclasses.dataclass(frozen=True)
class Preferences:
  """Filters, ranked goals, and instructors to favor."""

  filters: Filters = Filters()
  goals: tuple[Goal, ...] = (Goal.RATING, Goal.COMPACT)
  preferred: tuple[str, ...] = ()


NO_PREFERENCES = Preferences()


@dataclasses.dataclass(frozen=True)
class Schedule:
  """A conflict-free set of sections covering every requested course.

  Measures describe the whole week, including fixed sections.

  Attributes:
    sections: One bundle per course, flattened; fixed sections excluded.
    average_rating: Mean rating of rated instructors, if any are rated.
    average_difficulty: Mean difficulty of rated instructors, if any.
    days: Days with a class.
    gap_minutes: Time between consecutive classes, summed over the week.
    first_start: Earliest start in the week, in minutes after midnight.
    last_end: Latest end in the week, in minutes after midnight.
    score: How well the week meets the goals; higher is better.
  """

  sections: tuple[models.Section, ...]
  average_rating: float | None
  average_difficulty: float | None
  days: frozenset[models.Weekday]
  gap_minutes: int
  first_start: int | None
  last_end: int | None
  score: float


def overlaps(a: models.Section, b: models.Section) -> bool:
  """Whether two sections meet at the same time; TBA meetings never do."""
  return any(_meetings_overlap(x, y) for x in a.meetings for y in b.meetings)


def _meetings_overlap(x: models.Meeting, y: models.Meeting) -> bool:
  if (
    x.start_minute is None
    or x.end_minute is None
    or y.start_minute is None
    or y.end_minute is None
  ):
    return False
  if not x.days or not y.days:
    return False
  if x.end_minute <= x.start_minute or y.end_minute <= y.start_minute:
    return False
  return (
    not set(x.days).isdisjoint(y.days)
    and x.start_minute < y.end_minute
    and y.start_minute < x.end_minute
  )


def _rmp(sections: Iterable[models.Section], field: str) -> list[float]:
  return [
    value
    for s in sections
    for i in s.instructors
    if i.rmp is not None and (value := getattr(i.rmp, field)) is not None
  ]


def _teaches(section: models.Section, fragments: Sequence[str]) -> bool:
  return any(
    f in i.name.lower() for i in section.instructors for f in fragments
  )


def _allowed(section: models.Section, f: Filters) -> bool:
  """Whether a section meets every filter a single section can break."""
  for meeting in section.meetings:
    if f.excluded_days.intersection(meeting.days):
      return False
    start, end = meeting.start_minute, meeting.end_minute
    if start is None or end is None:
      continue
    if f.earliest_start is not None and start < f.earliest_start:
      return False
    if f.latest_end is not None and end > f.latest_end:
      return False
    for w in f.keep_free:
      if w.days.intersection(meeting.days) and start < w.end and w.start < end:
        return False
  if _teaches(section, f.excluded):
    return False
  if f.min_rating is not None and any(
    r < f.min_rating for r in _rmp([section], "rating")
  ):
    return False
  open_seat = section.capacity == 0 or section.registered < section.capacity
  return open_seat or not f.open_seats_only


def _section_rank(
  section: models.Section, prefs: Preferences
) -> tuple[bool, float]:
  """Orders a type's sections so the search meets likely winners first."""
  ratings = _rmp([section], "rating")
  difficulty = _rmp([section], "difficulty")
  rating = statistics.fmean(ratings) if ratings else _NEUTRAL
  ease = 5.0 - (statistics.fmean(difficulty) if difficulty else _NEUTRAL)
  local = {Goal.RATING: rating, Goal.EASY: ease}
  weighted = sum(
    _weight(i) * local.get(goal, 0.0) for i, goal in enumerate(prefs.goals)
  )
  return (_teaches(section, prefs.preferred), weighted or rating)


def bundles(
  sections: Sequence[models.Section], prefs: Preferences = NO_PREFERENCES
) -> list[tuple[models.Section, ...]]:
  """Lists a course's registrable bundles that meet the filters, best first.

  A bundle takes one section of every type its link group offers. A link
  group is the sections sharing a link code plus those without one, which
  pair with any group ("Register for 1 Lecture and the Discussion").
  Cancelled sections, sections breaking a filter, and bundles that
  conflict internally are dropped.
  """
  live = [
    s for s in sections if not s.is_cancelled and _allowed(s, prefs.filters)
  ]
  links = sorted({s.link_code for s in live if s.link_code is not None})
  found: dict[frozenset[str], tuple[models.Section, ...]] = {}
  for link in links or [None]:
    by_type: dict[str, list[models.Section]] = collections.defaultdict(list)
    for s in live:
      if s.link_code in (None, link):
        by_type[s.type].append(s)
    # A group missing a type (all its labs filtered out, say) cannot be
    # registered, so it offers no bundle at all.
    needed = {
      s.type
      for s in sections
      if not s.is_cancelled and s.link_code in (None, link)
    }
    if not by_type or not needed <= by_type.keys():
      continue
    choices = [
      sorted(typed, key=lambda s: _section_rank(s, prefs), reverse=True)[
        :_PER_TYPE
      ]
      for typed in by_type.values()
    ]
    for combo in itertools.product(*choices):
      if not any(overlaps(a, b) for a, b in itertools.combinations(combo, 2)):
        found.setdefault(frozenset(s.id for s in combo), combo)
  return sorted(
    found.values(),
    key=lambda b: sum(_section_rank(s, prefs)[1] for s in b) / len(b),
    reverse=True,
  )


def _weight(rank: int) -> float:
  """Each goal weighs half the one before it: the first decides."""
  return 0.5**rank


def _clamp(x: float) -> float:
  return min(1.0, max(0.0, x))


@dataclasses.dataclass(frozen=True)
class _Measures:
  days: frozenset[models.Weekday]
  gap_minutes: int
  first_start: int | None
  last_end: int | None
  mean_first: float | None
  mean_last: float | None


def _measure(sections: Iterable[models.Section]) -> _Measures:
  """Days on campus, gaps, and day spans of a whole week."""
  by_day: dict[models.Weekday, list[tuple[int, int]]] = collections.defaultdict(
    list
  )
  for s in sections:
    for meeting in s.meetings:
      if meeting.start_minute is None or meeting.end_minute is None:
        continue
      for day in meeting.days:
        by_day[day].append((meeting.start_minute, meeting.end_minute))
  gaps = 0
  for spans in by_day.values():
    spans.sort()
    reach = spans[0][1]
    for start, end in spans[1:]:
      gaps += max(0, start - reach)
      reach = max(reach, end)
  firsts = [min(a for a, _ in spans) for spans in by_day.values()]
  lasts = [max(b for _, b in spans) for spans in by_day.values()]
  return _Measures(
    days=frozenset(by_day),
    gap_minutes=gaps,
    first_start=min(firsts) if firsts else None,
    last_end=max(lasts) if lasts else None,
    mean_first=statistics.fmean(firsts) if firsts else None,
    mean_last=statistics.fmean(lasts) if lasts else None,
  )


def _metrics(
  chosen: Sequence[models.Section], week: _Measures
) -> dict[Goal, float]:
  """Measures a week against every goal, each scaled to 0..1."""
  ratings = _rmp(chosen, "rating")
  difficulty = _rmp(chosen, "difficulty")
  seats = [1 - s.registered / s.capacity for s in chosen if s.capacity > 0]
  metrics = {
    Goal.RATING: ((statistics.fmean(ratings) if ratings else _NEUTRAL) - 1) / 4,
    Goal.EASY: (5 - (statistics.fmean(difficulty) if difficulty else _NEUTRAL))
    / 4,
    # Ten hours of gaps a week is as bad as it gets.
    Goal.COMPACT: 1 - min(week.gap_minutes, 600) / 600,
    Goal.FEWER_DAYS: 1 - (max(len(week.days), 1) - 1) / 4,
    # Days starting at 8 score 0; at noon or later, 1.
    Goal.LATE_START: _clamp(((week.mean_first or 480) - 480) / 240),
    # Days ending by 2 score 1; at 8 or later, 0.
    Goal.EARLY_END: _clamp((1200 - (week.mean_last or 1200)) / 360),
    Goal.SEATS: statistics.fmean(seats) if seats else 0.5,
  }
  return {goal: _clamp(value) for goal, value in metrics.items()}


def _score(
  chosen: Sequence[models.Section], week: _Measures, prefs: Preferences
) -> float:
  """Scores a week on its goals, earlier goals weighing more."""
  metrics = _metrics(chosen, week)
  score = sum(_weight(i) * metrics[goal] for i, goal in enumerate(prefs.goals))
  return score + _PREFERRED_BONUS * sum(
    _teaches(s, prefs.preferred) for s in chosen
  )


def solve(
  courses: Sequence[models.Course],
  prefs: Preferences = NO_PREFERENCES,
  limit: int = 3,
  around: Sequence[models.Section] = (),
) -> list[Schedule]:
  """Finds the best weeks that take every course and meet every filter.

  Sections in `around` are fixed (the rest of the student's week): nothing
  may overlap them, they count toward the day limit and the goals, and
  they are not part of the result. The search walks courses with the
  fewest options first, abandons a branch at its first conflict or broken
  filter, and stops after a fixed budget, so it always answers quickly.
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
  options.sort(key=len)
  max_days = prefs.filters.max_days
  best: list[tuple[float, int, Schedule]] = []
  budget = _BUDGET
  counter = itertools.count()

  def walk(i: int, chosen: list[models.Section]) -> None:
    nonlocal budget
    if budget <= 0:
      return
    budget -= 1
    if i == len(options):
      week = _measure([*chosen, *around])
      score = _score(chosen, week, prefs)
      ratings = _rmp(chosen, "rating")
      difficulty = _rmp(chosen, "difficulty")
      found = Schedule(
        sections=tuple(chosen),
        average_rating=round(statistics.fmean(ratings), 2) if ratings else None,
        average_difficulty=(
          round(statistics.fmean(difficulty), 2) if difficulty else None
        ),
        days=week.days,
        gap_minutes=week.gap_minutes,
        first_start=week.first_start,
        last_end=week.last_end,
        score=round(score, 3),
      )
      heapq.heappush(best, (score, next(counter), found))
      if len(best) > limit:
        heapq.heappop(best)
      return
    for bundle in options[i]:
      if any(overlaps(a, b) for a in bundle for b in chosen):
        continue
      added = [*chosen, *bundle]
      if (
        max_days is not None
        and len(_measure([*added, *around]).days) > max_days
      ):
        continue
      walk(i + 1, added)

  walk(0, [])
  return [s for _, _, s in sorted(best, reverse=True)]


def blockers(
  courses: Sequence[models.Course],
  prefs: Preferences,
  around: Sequence[models.Section] = (),
) -> list[str]:
  """Filters that, each dropped alone, would let some week through.

  Meant for when `solve` finds nothing: it says which wish to give up.
  """
  defaults = Filters()
  found = []
  for field in dataclasses.fields(Filters):
    if getattr(prefs.filters, field.name) == getattr(defaults, field.name):
      continue
    relaxed = dataclasses.replace(
      prefs.filters, **{field.name: getattr(defaults, field.name)}
    )
    loose = dataclasses.replace(prefs, filters=relaxed)
    if solve(courses, loose, limit=1, around=around):
      found.append(_FILTER_NAMES[field.name])
  return found


def displaces(section: models.Section, other: models.Section) -> bool:
  """Whether adding `section` swaps `other` out of a week.

  It does when both belong to one course and share a type, or sit in
  link groups that cannot be taken together. Mirrors the client's rule.
  """
  if other.id == section.id or other.course_code != section.course_code:
    return False
  compatible = (
    section.link_code is None
    or other.link_code is None
    or section.link_code == other.link_code
  )
  return other.type == section.type or not compatible


def missing_types(
  course: models.Course, chosen: Sequence[models.Section]
) -> list[str]:
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
