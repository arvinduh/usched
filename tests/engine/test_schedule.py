"""Tests for bundling sections and solving schedules."""

from server.src.data import catalog_models as m
from server.src.engine import schedule


MON, TUE, WED = m.Weekday.MON, m.Weekday.TUE, m.Weekday.WED


def _section(
  sid: str,
  kind: str = "Lecture",
  link: str | None = None,
  days: tuple[m.Weekday, ...] = (MON,),
  start: int | None = 600,
  end: int | None = 650,
  teacher: str = "Ann Lee",
  rating: float | None = None,
  cancelled: bool = False,
) -> m.Section:
  rmp = (
    None
    if rating is None
    else m.Rating(
      rmp_id=1,
      rating=rating,
      difficulty=None,
      num_ratings=1,
      would_take_again=None,
    )
  )
  return m.Section(
    term=20271,
    id=sid,
    course_code="X-1",
    type=kind,
    link_code=link,
    session=None,
    name=None,
    units=None,
    requires_d_clearance=False,
    is_cancelled=cancelled,
    registered=0,
    capacity=10,
    waitlisted=0,
    description=None,
    notes=None,
    syllabus_url=None,
    meetings=[m.Meeting(days=list(days), start_minute=start, end_minute=end)],
    instructors=[m.Instructor(key=teacher.lower(), name=teacher, rmp=rmp)],
  )


def _course(code: str, *sections: m.Section) -> m.Course:
  return m.Course(
    term=20271,
    code=code,
    department=code.split("-")[0],
    number=code.split("-")[1],
    suffix="",
    title=code,
    description="",
    units=m.Units(min=4, max=4),
    recommended_prep=None,
    duplicate_credit=None,
    course_notes=None,
    term_notes=None,
    is_cross_listed=False,
    ge=[],
    requisites=m.Requisites(prerequisite=[], corequisite=[], concurrent=[]),
    restrictions=[],
    sections=list(sections),
  )


def test_overlap_needs_a_shared_day_and_time():
  a = _section("1", days=(MON, WED), start=600, end=650)
  assert schedule.overlaps(a, _section("2", days=(WED,), start=640, end=700))
  assert not schedule.overlaps(a, _section("3", days=(TUE,), start=600))
  assert not schedule.overlaps(a, _section("4", days=(MON,), start=650))
  assert not schedule.overlaps(a, _section("5", start=None, end=None))


def test_bundles_take_one_of_each_type_within_a_link_code():
  found = schedule.bundles(
    [
      _section("lec", "Lecture", "A", start=600),
      _section("lab1", "Lab", "A", start=700, end=750),
      _section("lab2", "Lab", "A", start=800, end=850),
      _section("labB", "Lab", "B", start=900, end=950),
    ]
  )
  ids = sorted(tuple(sorted(s.id for s in b)) for b in found)
  assert ids == [("lab1", "lec"), ("lab2", "lec"), ("labB",)]


def test_unlinked_sections_pair_with_any_link_group():
  found = schedule.bundles(
    [
      _section("lecA", "Lecture", "A", start=600),
      _section("lec", "Lecture", None, start=700, end=750),
      _section("dis", "Discussion", None, start=800, end=850),
    ]
  )
  ids = sorted(tuple(sorted(s.id for s in b)) for b in found)
  assert ids == [("dis", "lec"), ("dis", "lecA")]


def test_bundles_drop_cancelled_and_self_conflicting_sections():
  found = schedule.bundles(
    [
      _section("lec", "Lecture", "A"),
      _section("clash", "Lab", "A"),
      _section("gone", "Lab", "A", start=900, end=950, cancelled=True),
    ]
  )
  assert found == []


def test_preferences_filter_but_fall_back_with_a_penalty():
  prefs = schedule.Preferences(excluded_days=frozenset({MON}))
  only_monday = _course("A-1", _section("1", days=(MON,)))
  (best,) = schedule.solve([only_monday], prefs)
  assert best.violations == 1
  either = _course(
    "B-1", _section("2", days=(MON,)), _section("3", days=(TUE,))
  )
  assert [s.id for s in schedule.solve([either], prefs)[0].sections] == ["3"]


def test_solve_avoids_conflicts_and_ranks_by_rating():
  a = _course(
    "A-1",
    _section("a-low", start=600, rating=2.0),
    _section("a-high", start=600, teacher="Bo Ng", rating=5.0),
  )
  b = _course(
    "B-1",
    _section("b-clash", start=620),
    _section("b-free", start=700, end=750),
  )
  best = schedule.solve([a, b])[0]
  assert {s.id for s in best.sections} == {"a-high", "b-free"}
  assert best.average_rating == 5.0


def test_a_course_without_bundles_is_unsolvable():
  empty = _course("A-1", _section("x", cancelled=True))
  assert schedule.solve([empty]) == []
