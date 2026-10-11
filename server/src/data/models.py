"""Domain data models for usched academic scheduling and persistence.

This module defines Pydantic domain models for persistent entities:
instructors, sections, courses, and degree programs, used across database,
engine, and API surfaces.
"""

import enum
from collections.abc import Sequence
from datetime import time

import pydantic


class Day(enum.IntFlag):
  """Bitmask flags representing days of week for instant bitwise checks."""

  NONE = 0
  MON = 1 << 0
  TUE = 1 << 1
  WED = 1 << 2
  THU = 1 << 3
  FRI = 1 << 4
  SAT = 1 << 5
  SUN = 1 << 6


DAY_NAME_TO_FLAG: dict[str, Day] = {
  "MON": Day.MON,
  "TUE": Day.TUE,
  "WED": Day.WED,
  "THU": Day.THU,
  "FRI": Day.FRI,
  "SAT": Day.SAT,
  "SUN": Day.SUN,
}

DAY_FLAG_TO_NAME: tuple[tuple[Day, str], ...] = (
  (Day.MON, "Mon"),
  (Day.TUE, "Tue"),
  (Day.WED, "Wed"),
  (Day.THU, "Thu"),
  (Day.FRI, "Fri"),
  (Day.SAT, "Sat"),
  (Day.SUN, "Sun"),
)


def parse_days_mask(raw: str | Sequence[str] | int | Day | None) -> Day:
  """Converts string 'Mon,Wed', day list, or integer to Day bitmask."""
  if isinstance(raw, Day):
    return raw
  if isinstance(raw, int):
    return Day(raw)
  if not raw:
    return Day.NONE
  if isinstance(raw, str):
    tokens = [t.strip().upper()[:3] for t in raw.split(",") if t.strip()]
  else:
    tokens = [str(t).strip().upper()[:3] for t in raw if str(t).strip()]

  mask = Day.NONE
  for t in tokens:
    flag = DAY_NAME_TO_FLAG.get(t)
    if flag is not None:
      mask |= flag
  return mask


def format_days_list(mask: Day | int) -> list[str]:
  """Formats Day bitmask to chronological ordered list of day names."""
  return [name for flag, name in DAY_FLAG_TO_NAME if mask & flag]


def parse_time_str(val: str | time | None) -> time:
  """Parses HH:MM string or time object into standard datetime.time."""
  if isinstance(val, time):
    return val
  if not val or ":" not in str(val):
    return time(0, 0)
  parts = str(val).strip().split(":")
  try:
    return time(int(parts[0]), int(parts[1]))
  except (ValueError, IndexError):
    return time(0, 0)


class CourseStatus(enum.StrEnum):
  """Prerequisite fulfillment state for a course."""

  COMPLETED = "completed"
  ELIGIBLE = "eligible"
  LOCKED = "locked"


class CategoryStatus(enum.StrEnum):
  """Degree category completion progress state."""

  PENDING = "pending"
  IN_PROGRESS = "in_progress"
  COMPLETED = "completed"


class Instructor(pydantic.BaseModel):
  """Faculty instructor record enriched with RateMyProfessors metrics."""

  id: str = pydantic.Field(description="Unique faculty slug or identifier.")
  name: str = pydantic.Field(description="Full legal faculty name.")
  department: str = pydantic.Field(
    default="", description="Academic department affiliation."
  )
  rmp_id: str | None = pydantic.Field(
    default=None, description="RateMyProfessors legacy ID."
  )
  rmp_rating: float | None = pydantic.Field(
    default=None, description="Average quality rating out of 5.0."
  )
  rmp_difficulty: float | None = pydantic.Field(
    default=None, description="Average difficulty rating out of 5.0."
  )
  rmp_num_ratings: int = pydantic.Field(
    default=0, description="Total number of student ratings submitted."
  )
  rmp_take_again_percent: float | None = pydantic.Field(
    default=None,
    description="Percentage of students who would take faculty again.",
  )


class Section(pydantic.BaseModel):
  """Scheduled meeting section of a course for a specific academic term."""

  id: str = pydantic.Field(description="Unique section registration ID.")
  course_id: str = pydantic.Field(
    description="Parent course code, e.g. 'CSCI-104L'."
  )
  section_type: str = pydantic.Field(
    description="Meeting format: Lecture, Lab, Discussion, Quiz."
  )
  term: str = pydantic.Field(
    description="Academic term code, e.g. '20263' for Fall 2026."
  )
  days: list[str] = pydantic.Field(
    default_factory=list, description="Days of week on which section meets."
  )
  start_time: str = pydantic.Field(
    default="00:00", description="Meeting start time (HH:MM)."
  )
  end_time: str = pydantic.Field(
    default="00:00", description="Meeting end time (HH:MM)."
  )
  start_minute: int = pydantic.Field(
    default=0, description="Minutes from midnight for meeting start."
  )
  end_minute: int = pydantic.Field(
    default=0, description="Minutes from midnight for meeting end."
  )
  location: str = pydantic.Field(
    default="", description="Classroom facility or building code."
  )
  instructor: Instructor | None = pydantic.Field(
    default=None, description="Primary faculty instructor record."
  )
  enrolled: int = pydantic.Field(
    default=0, description="Currently enrolled student count."
  )
  capacity: int = pydantic.Field(
    default=0, description="Maximum student enrollment limit."
  )
  waitlist: int = pydantic.Field(
    default=0, description="Current waitlist student count."
  )
  is_wishlist: bool = pydantic.Field(
    default=False,
    description="True if marked candidate rather than confirmed enrolled.",
  )


class Course(pydantic.BaseModel):
  """Academic course offering with sections and prerequisite chains."""

  id: str = pydantic.Field(
    description="Standardized course code, e.g. 'CSCI-104L'."
  )
  department: str = pydantic.Field(
    description="Academic subject prefix, e.g. 'CSCI'."
  )
  number: str = pydantic.Field(
    description="Course numerical catalog level, e.g. '104L'."
  )
  title: str = pydantic.Field(description="Official academic course title.")
  description: str = pydantic.Field(
    default="", description="Catalogue course description and learning scope."
  )
  units: float = pydantic.Field(
    default=4.0, description="Academic semester credit unit value."
  )
  prerequisites_raw: str = pydantic.Field(
    default="", description="Raw prerequisite requirement string."
  )
  prerequisites_json: list[list[str]] = pydantic.Field(
    default_factory=list,
    description="Normalized CNF prerequisite requirement tree.",
  )
  corequisites_raw: str = pydantic.Field(
    default="", description="Raw corequisite course requirement string."
  )
  ge_category: str | None = pydantic.Field(
    default=None, description="General Education requirement category."
  )
  ge_categories: list[str] = pydantic.Field(
    default_factory=list,
    description="General Education categories, e.g. ['GE-A', 'GE-H'].",
  )
  sections: list[Section] = pydantic.Field(
    default_factory=list, description="Available sections for current term."
  )


class DegreeCategory(pydantic.BaseModel):
  """Graduation requirement group within an academic degree program."""

  name: str = pydantic.Field(description="Category title, e.g. 'Major Core'.")
  required_units: float = pydantic.Field(
    description="Minimum credit units required."
  )
  completed_units: float = pydantic.Field(
    default=0.0, description="Units satisfied by completed courses."
  )
  required_courses: list[str] = pydantic.Field(
    default_factory=list, description="Course codes that satisfy requirement."
  )
  completed_courses: list[str] = pydantic.Field(
    default_factory=list, description="Completed course codes in category."
  )
  status: CategoryStatus = pydantic.Field(
    default=CategoryStatus.PENDING,
    description="Category progress status: pending, in_progress, completed.",
  )


class DegreeProgram(pydantic.BaseModel):
  """USC curriculum roadmap and graduation criteria for an academic major."""

  id: str = pydantic.Field(
    description="Canonical degree program slug, e.g. 'csci-bs'."
  )
  title: str = pydantic.Field(
    description="Official degree title, e.g. 'Computer Science (BS)'."
  )
  school: str = pydantic.Field(
    description="Parent USC school or academic division."
  )
  total_units: float = pydantic.Field(
    description="Total credit units required for graduation."
  )
  categories: list[DegreeCategory] = pydantic.Field(
    default_factory=list, description="Categorized graduation criteria."
  )


class ApExamDefinition(pydantic.BaseModel):
  """Advanced Placement examination standard equivalence rule."""

  id: str = pydantic.Field(description="Exam identifier, e.g. 'AP_CALC_BC'.")
  name: str = pydantic.Field(
    description="Full exam title, e.g. 'AP Calculus BC'."
  )
  fulfills_ge_category: str | None = pydantic.Field(
    default=None, description="Satisfied GE category, e.g. 'GE-F'."
  )
  waives_courses: list[str] = pydantic.Field(
    default_factory=list,
    description="Waived prerequisite courses, e.g. ['MATH-125', 'MATH-126'].",
  )
  units: float = pydantic.Field(
    default=4.0, description="Semester credit units awarded."
  )


class UserApCredit(pydantic.BaseModel):
  """User recorded AP exam credit score."""

  exam_id: str = pydantic.Field(description="Reference to ApExamDefinition.id.")
  score: int = pydantic.Field(
    description="Score achieved on examination (1-5)."
  )
  added_at: str = pydantic.Field(description="ISO timestamp when credit added.")


class UserCompletedCourse(pydantic.BaseModel):
  """Catalogue record of a completed or waived course."""

  course_id: str = pydantic.Field(description="Course identifier code.")
  term: str = pydantic.Field(
    default="", description="Academic term completed, e.g. '20253'."
  )
  grade: str = pydantic.Field(default="", description="Recorded grade or 'CR'.")
  source: str = pydantic.Field(
    default="course", description="Origin: course, ap, or transfer."
  )
  added_at: str = pydantic.Field(
    description="ISO timestamp of record addition."
  )


class ScheduleConfiguration(pydantic.BaseModel):
  """Named schedule variation containing a chosen section roster."""

  id: str = pydantic.Field(description="Unique configuration identifier.")
  name: str = pydantic.Field(
    description="Display title, e.g. 'Morning Priority'."
  )
  is_active: bool = pydantic.Field(
    default=False, description="True if currently active on timetable."
  )
  created_at: str = pydantic.Field(description="ISO creation timestamp.")
  updated_at: str = pydantic.Field(description="ISO last modified timestamp.")
  sections: list[Section] = pydantic.Field(
    default_factory=list,
    description="Enrolled sections in this schedule option.",
  )


class GeCategoryProgress(pydantic.BaseModel):
  """Fulfillment status for a single USC General Education category."""

  category: str = pydantic.Field(description="Category code, e.g. 'GE-A'.")
  name: str = pydantic.Field(description="Category title, e.g. 'The Arts'.")
  required_count: int = pydantic.Field(
    description="Number of courses required."
  )
  completed_count: int = pydantic.Field(
    description="Number of valid courses completed."
  )
  satisfying_courses: list[str] = pydantic.Field(
    default_factory=list, description="Course codes mapped to this category."
  )
  satisfying_ap: list[str] = pydantic.Field(
    default_factory=list, description="AP exam IDs mapped to this category."
  )
  is_satisfied: bool = pydantic.Field(
    default=False, description="True if requirement count met."
  )


class GeAuditSummary(pydantic.BaseModel):
  """Comprehensive General Education requirement fulfillment audit."""

  total_required: int = pydantic.Field(
    description="Total required courses (usually 10: 8 Core + 2 Global)."
  )
  total_satisfied: int = pydantic.Field(
    description="Total satisfied course slots."
  )
  categories: list[GeCategoryProgress] = pydantic.Field(
    default_factory=list, description="Progress per GE category."
  )
  is_complete: bool = pydantic.Field(
    default=False, description="True if all GE categories are satisfied."
  )


class UserState(pydantic.BaseModel):
  """Unified student state Single Source of Truth payload."""

  configurations: list[ScheduleConfiguration] = pydantic.Field(
    default_factory=list, description="All schedule configurations."
  )
  active_configuration_id: str | None = pydantic.Field(
    default=None, description="ID of currently selected configuration."
  )
  watched_courses: list[Course] = pydantic.Field(
    default_factory=list,
    description="Watched zoning area courses (watched + scheduled).",
  )
  completed_courses: list[UserCompletedCourse] = pydantic.Field(
    default_factory=list, description="Catalogue of taken courses."
  )
  ap_credits: list[UserApCredit] = pydantic.Field(
    default_factory=list, description="Earned AP exam credits."
  )
  ge_audit: GeAuditSummary | None = pydantic.Field(
    default=None, description="General Education audit evaluation."
  )
