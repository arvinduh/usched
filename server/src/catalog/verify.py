"""Checks a freshly built catalog before it may replace the live one.

Invariants are facts the schema cannot express with constraints alone
(meeting times inside a day, unit ranges in order, every fetched term
populated). Any violation fails the build, so the live database is only
ever one that passed. Resolution rates are reported, not enforced: they
depend on how much of USC the cache holds (a one-term fetch resolves
fewer references), not on whether the build is correct.
"""

import dataclasses
import sqlite3


# (description, query counting violating rows)
_INVARIANTS = (
  ("dangling references", "SELECT COUNT(*) FROM pragma_foreign_key_check"),
  (
    "meetings with impossible times",
    """SELECT COUNT(*) FROM meeting
       WHERE days NOT BETWEEN 0 AND 127
          OR start_minute NOT BETWEEN 0 AND 1440
          OR end_minute NOT BETWEEN 0 AND 1440
          OR start_minute >= end_minute""",
  ),
  (
    "unit ranges out of order",
    """SELECT (SELECT COUNT(*) FROM offering WHERE units_min > units_max)
            + (SELECT COUNT(*) FROM section WHERE units_min > units_max)
            + (SELECT COUNT(*) FROM catalogue_course
               WHERE units_min > units_max)
            + (SELECT COUNT(*) FROM program_requirement
               WHERE units_min > units_max)""",
  ),
  (
    "negative seat counts",
    """SELECT COUNT(*) FROM section
       WHERE registered < 0 OR capacity < 0 OR waitlisted < 0""",
  ),
  (
    "course codes not in their canonical spelling",
    """SELECT COUNT(*) FROM offering o JOIN course c ON c.code = o.course_code
       WHERE o.course_code != c.code COLLATE BINARY""",
  ),
  (
    "Active terms with no offerings",
    """SELECT COUNT(*) FROM term t WHERE t.status = 'Active'
       AND NOT EXISTS (SELECT 1 FROM offering o WHERE o.term_code = t.code)""",
  ),
  (
    "offerings without sections",
    """SELECT COUNT(*) FROM offering o WHERE NOT EXISTS
       (SELECT 1 FROM section s
        WHERE s.term_code = o.term_code AND s.course_code = o.course_code)""",
  ),
)

# (metric, query returning a percentage)
_RATES = (
  (
    "requisites resolved",
    "SELECT 100.0 * AVG(resolved_code IS NOT NULL) FROM requisite_course",
  ),
  (
    "program choices resolved",
    """SELECT 100.0 * AVG(resolved_code IS NOT NULL)
       FROM program_requirement_choice""",
  ),
  (
    "GE courses resolved",
    "SELECT 100.0 * AVG(resolved_code IS NOT NULL) FROM ge_course",
  ),
  (
    "instructors on RateMyProfessors",
    """SELECT 100.0 * COUNT(r.instructor_key) / COUNT(*)
       FROM instructor i LEFT JOIN rmp_profile r ON r.instructor_key = i.key""",
  ),
)


@dataclasses.dataclass(frozen=True)
class Report:
  """What verification found.

  Attributes:
    problems: Violated invariants; empty means the catalog may go live.
    rates: Each measured percentage, None when its table is empty.
  """

  problems: list[str]
  rates: dict[str, float | None]


def verify(conn: sqlite3.Connection) -> Report:
  """Checks every invariant and measures every rate of a built catalog."""
  problems = []
  for description, query in _INVARIANTS:
    (count,) = conn.execute(query).fetchone()
    if count:
      problems.append(f"{count} {description}")
  rates: dict[str, float | None] = {}
  for name, query in _RATES:
    (rate,) = conn.execute(query).fetchone()
    rates[name] = None if rate is None else round(rate, 1)
  return Report(problems, rates)
