"""Tests for bundling sections and solving schedules."""

from server.db import models
from server.engine import schedule


MON, TUE, WED = (
  models.Weekday.MON,
  models.Weekday.TUE,
  models.Weekday.WED,
)


def _section(
  sid: str,
  kind: str = "Lecture",
  link: str | None = None,
  days: tuple[models.Weekday, ...] = (MON,),
  start: int | None = 600,
  end: int | None = 650,
  teacher: str = "Ann Lee",
  rating: float | None = None,
  cancelled: bool = False,
) -> models.Section:
  rmp = (
    None
    if rating is None
    else models.Rating(
      rmp_id=1,
      rating=rating,
      difficulty=None,
      num_ratings=1,
      would_take_again=None,
    )
  )
  return models.Section(
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
    meetings=[
      models.Meeting(days=list(days), start_minute=start, end_minute=end)
    ],
    instructors=[models.Instructor(key=teacher.lower(), name=teacher, rmp=rmp)],
  )


def _course(code: str, *sections: models.Section) -> models.Course:
  return models.Course(
    term=20271,
    code=code,
    department=code.split("-")[0],
    number=code.split("-")[1],
    suffix="",
    title=code,
    description="",
    units=models.Units(min=4, max=4),
    recommended_prep=None,
    duplicate_credit=None,
    course_notes=None,
    term_notes=None,
    is_cross_listed=False,
    ge=[],
    requisites=models.Requisites(
      prerequisite=[], corequisite=[], concurrent=[]
    ),
    restrictions=[],
    sections=[s.model_copy(update={"course_code": code}) for s in sections],
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


def test_filters_are_hard_and_blockers_name_the_culprit():
  no_monday = schedule.Preferences(
    filters=schedule.Filters(excluded_days=frozenset({MON}))
  )
  only_monday = _course("A-1", _section("1", days=(MON,)))
  assert schedule.solve([only_monday], no_monday) == []
  assert schedule.blockers([only_monday], no_monday) == ["the days off"]
  either = _course(
    "B-1", _section("2", days=(MON,)), _section("3", days=(TUE,))
  )
  (best,) = schedule.solve([either], no_monday)
  assert [s.id for s in best.sections] == ["3"]


def _goals(*goals: schedule.Goal, **filters) -> schedule.Preferences:
  return schedule.Preferences(filters=schedule.Filters(**filters), goals=goals)


def test_compact_trades_a_rating_for_no_breaks():
  a = _course("A-1", _section("a", start=600, end=650))
  b = _course(
    "B-1",
    _section("b-near", start=650, end=700, rating=2.0),
    _section("b-far", start=900, end=950, teacher="Bo Ng", rating=5.0),
  )
  compact = schedule.solve([a, b], _goals(schedule.Goal.COMPACT))[0]
  assert {s.id for s in compact.sections} == {"a", "b-near"}
  assert compact.gap_minutes == 0
  rated = schedule.solve([a, b], _goals(schedule.Goal.RATING))[0]
  assert {s.id for s in rated.sections} == {"a", "b-far"}
  assert rated.gap_minutes == 250


def test_fewer_days_and_day_limits_count_the_fixed_week():
  fixed = [_section("fixed", days=(MON,), start=500, end=550)]
  b = _course(
    "B-1",
    _section("b-mon", days=(MON,), start=700, end=750),
    _section("b-tue", days=(TUE,), start=700, end=750, rating=5.0),
  )
  fewest = schedule.solve([b], _goals(schedule.Goal.FEWER_DAYS), around=fixed)
  assert [s.id for s in fewest[0].sections] == ["b-mon"]
  assert fewest[0].days == {MON}
  one_day = _goals(schedule.Goal.RATING, max_days=1)
  assert [
    s.id for s in schedule.solve([b], one_day, around=fixed)[0].sections
  ] == ["b-mon"]


def test_kept_free_windows_and_latest_end_exclude_sections():
  b = _course(
    "B-1",
    _section("lunch", start=720, end=770),
    _section("late", start=1100, end=1150),
    _section("fine", start=600, end=650),
  )
  lunch = schedule.Window(frozenset({MON}), 720, 780)
  prefs = _goals(schedule.Goal.RATING, keep_free=(lunch,), latest_end=18 * 60)
  assert [s.sections[0].id for s in schedule.solve([b], prefs)] == ["fine"]


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


def test_missing_types_follow_the_chosen_link_group():
  lecture = _section("lec", "Lecture", "A")
  lab = _section("lab", "Lab", "A", start=700, end=750)
  quiz_b = _section("quiz", "Quiz", "B", start=800, end=850)
  course = _course("X-1", lecture, lab, quiz_b)
  assert schedule.missing_types(course, []) == ["Lecture", "Lab", "Quiz"]
  assert schedule.missing_types(course, [lecture]) == ["Lab"]


FRI = models.Weekday.FRI


def test_alternatives_trade_the_best_ratings_for_a_free_friday():
  a = _course(
    "A-1",
    _section("a-fri", days=(MON, FRI), rating=5.0),
    _section("a-wed", days=(MON, WED), teacher="Bo Ng", rating=2.0),
  )
  b = _course(
    "B-1",
    _section("b-fri", days=(FRI,), start=780, end=830, rating=5.0),
    _section(
      "b-tue", days=(TUE,), start=780, end=830, teacher="Cy Oh", rating=2.0
    ),
  )
  found = schedule.alternatives([a, b])
  assert [(o.lens.goal, o.lens.day_off) for o in found] == [
    (schedule.Goal.RATING, None),
    (schedule.Goal.RATING, FRI),
  ]
  best, free = (o.schedule for o in found)
  assert {s.id for s in best.sections} == {"a-fri", "b-fri"}
  assert {s.id for s in free.sections} == {"a-wed", "b-tue"}
  assert FRI in best.days and FRI not in free.days


def test_alternatives_drop_weeks_that_move_one_course_of_two():
  a = _course("A-1", _section("a", start=540, end=590))
  b = _course(
    "B-1",
    _section("b-mon", start=660, end=710, rating=5.0),
    _section("b-fri", days=(FRI,), start=780, end=830, teacher="Bo Ng"),
  )
  # A late start would move only B, so it is no real alternative.
  (only,) = schedule.alternatives([a, b])
  assert {s.id for s in only.schedule.sections} == {"a", "b-mon"}


def test_alternatives_ignore_an_instructor_swap_at_the_same_time():
  a = _course(
    "A-1",
    _section("a-best", rating=5.0),
    _section("a-same", teacher="Bo Ng", rating=4.0),
    _section("a-late", start=840, end=890, teacher="Cy Oh", rating=1.0),
  )
  found = schedule.alternatives([a])
  assert [o.schedule.sections[0].id for o in found] == ["a-best", "a-late"]
  assert found[1].lens.goal == schedule.Goal.LATE_START
