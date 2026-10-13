"""Canonical data models for the usched catalog and SQLite database.

Defines both the external Pydantic models returned by the API (contracts with
the web client) and the internal dataclass rows matching schema.sql tables for
catalog ingestion and SQLite storage.
"""

import dataclasses
import enum

import pydantic


# =============================================================================
# API Boundary Models (Pydantic)
# =============================================================================


class Weekday(enum.StrEnum):
  """A meeting day, in the abbreviation USC uses."""

  MON = "Mon"
  TUE = "Tue"
  WED = "Wed"
  THU = "Thu"
  FRI = "Fri"
  SAT = "Sat"
  SUN = "Sun"


class Term(pydantic.BaseModel):
  """An academic term."""

  code: int = pydantic.Field(description="USC term code, e.g. 20271.")
  season: str = pydantic.Field(description="Spring, Summer, or Fall.")
  year: int
  status: str = pydantic.Field(description="As USC reports it, e.g. Active.")
  has_courses: bool = pydantic.Field(
    description="Whether this term's courses were fetched."
  )


class Units(pydantic.BaseModel):
  """A unit count or range; min equals max for fixed-unit courses."""

  min: float
  max: float


class Rating(pydantic.BaseModel):
  """An instructor's RateMyProfessors profile."""

  rmp_id: int
  rating: float | None = pydantic.Field(description="1-5; None if unrated.")
  difficulty: float | None = pydantic.Field(description="1-5; None if unrated.")
  num_ratings: int
  would_take_again: float | None = pydantic.Field(
    description="Percent of students who would take again; None if unknown."
  )


class Instructor(pydantic.BaseModel):
  """Someone teaching a section."""

  key: str = pydantic.Field(description="Normalized name, e.g. carter slocum.")
  name: str
  rmp: Rating | None


class Meeting(pydantic.BaseModel):
  """A weekly meeting pattern; empty days and null times mean TBA."""

  days: list[Weekday]
  start_minute: int | None = pydantic.Field(
    description="Minutes after midnight, e.g. 600 = 10:00."
  )
  end_minute: int | None


class Section(pydantic.BaseModel):
  """A registrable section of a course in a term."""

  term: int
  id: str = pydantic.Field(description="USC section number, e.g. 29905.")
  course_code: str
  type: str = pydantic.Field(description="Lecture, Lab, Discussion, Quiz, ...")
  link_code: str | None = pydantic.Field(
    description=(
      "Bundle letter: take one section of each type sharing a letter. "
      "None means the section stands alone."
    )
  )
  session: str | None = pydantic.Field(description="USC session code.")
  name: str | None = pydantic.Field(description="Special-topic title.")
  units: Units | None
  requires_d_clearance: bool
  is_cancelled: bool
  registered: int
  capacity: int
  waitlisted: int
  description: str | None = pydantic.Field(
    description="Registration guidance, e.g. which sections to pair."
  )
  notes: str | None
  syllabus_url: str | None
  meetings: list[Meeting]
  instructors: list[Instructor]


class CourseRef(pydantic.BaseModel):
  """A reference to a course as a source wrote it."""

  code: str = pydantic.Field(description="As written, e.g. CSCI-103.")
  resolved: str | None = pydantic.Field(
    description="The catalog course it matches, e.g. CSCI-103L, if any."
  )


class RequisiteGroup(pydantic.BaseModel):
  """Met by `required_count` of its options; an option is courses ANDed."""

  required_count: int
  options: list[list[CourseRef]]


class Requisites(pydantic.BaseModel):
  """Every group of each kind must be met."""

  prerequisite: list[RequisiteGroup]
  corequisite: list[RequisiteGroup]
  concurrent: list[RequisiteGroup]


class Restriction(pydantic.BaseModel):
  """Who may enroll: inclusive entries admit a group, exclusive bar it."""

  kind: str = pydantic.Field(description="class, major, or school.")
  code: str
  description: str
  inclusive: bool


class Course(pydantic.BaseModel):
  """A course as offered in one term, with its sections."""

  term: int
  code: str = pydantic.Field(description="e.g. CSCI-104L.")
  department: str
  number: str
  suffix: str
  title: str
  description: str
  units: Units
  recommended_prep: str | None
  duplicate_credit: str | None
  course_notes: str | None
  term_notes: str | None
  is_cross_listed: bool
  ge: list[str] = pydantic.Field(description="GE categories, e.g. GE-B.")
  requisites: Requisites
  restrictions: list[Restriction]
  sections: list[Section]


class KnownCourse(pydantic.BaseModel):
  """A course the catalog knows, in its canonical spelling."""

  code: str = pydantic.Field(description="e.g. BISC-101Lgx.")
  title: str


class ProgramSummary(pydantic.BaseModel):
  """A degree, minor, certificate, or other program."""

  id: str = pydantic.Field(description="Slug, e.g. computer-science-bs.")
  title: str
  name: str
  emphasis: str | None
  kind: str = pydantic.Field(description="degree, minor, certificate, other.")
  degree_type: str | None = pydantic.Field(
    description="e.g. BS; None if not a degree."
  )
  school: str | None
  total_units: float | None
  total_units_stated: bool = pydantic.Field(
    description="False when the total is the university's bachelor's minimum."
  )


class RequirementChoice(pydantic.BaseModel):
  """One course that can fill a requirement slot."""

  course: CourseRef
  title: str | None = pydantic.Field(
    description="From the course's latest offering; None if never offered."
  )
  units: Units | None


class Requirement(pydantic.BaseModel):
  """A requirement heading; each slot is filled by one of its choices."""

  position: int
  parent: int | None = pydantic.Field(
    description="Parent requirement position."
  )
  title: str
  units: Units | None
  notes: str = pydantic.Field(description="Prose rules, e.g. Take at least...")
  is_general_education: bool = pydantic.Field(
    description="The university GE requirement; the GE audit decides it."
  )
  slots: list[list[RequirementChoice]]


class Program(ProgramSummary):
  """A program with its full requirement tree."""

  catalogue: str = pydantic.Field(description="e.g. USC Catalogue 2026-2027.")
  description: str
  requirements: list[Requirement]


class GeCategory(pydantic.BaseModel):
  """A GE category and how many courses it needs."""

  code: str
  name: str
  area: str = pydantic.Field(description="core or global.")
  required_count: int


class ApExam(pydantic.BaseModel):
  """An AP exam USC grants credit for."""

  id: str
  name: str
  min_score: int
  units: float
  ge: list[str]
  waives: list[CourseRef]


class ApCredit(pydantic.BaseModel):
  """A student's AP exam result."""

  exam_id: str
  score: int = pydantic.Field(ge=1, le=5)


class GeAuditRequest(pydantic.BaseModel):
  """What a student has done toward General Education."""

  completed: list[str] = pydantic.Field(description="Course codes taken.")
  ap_credits: list[ApCredit] = []
  ge_counted: dict[str, int] = pydantic.Field(
    default={}, description="GE seats the student counted by hand, by code."
  )


class GeProgress(pydantic.BaseModel):
  """How a GE category is filled; satisfied once filled reaches required."""

  code: str
  name: str
  required_count: int
  courses: list[str] = pydantic.Field(description="Completed codes used here.")
  exams: list[str] = pydantic.Field(description="AP exam ids used here.")
  counted: int = pydantic.Field(
    default=0,
    description="Seats the student counted by hand, such as transfer credit.",
  )

  @property
  def filled(self) -> int:
    """Seats filled by courses, exams, and the student's own count."""
    return len(self.courses) + len(self.exams) + self.counted


class RequirementStatus(enum.StrEnum):
  """How far along a requirement is."""

  DONE = "done"
  PARTIAL = "partial"
  TODO = "todo"
  MANUAL = "manual"  # Only prose rules; a person has to judge it.


class RequirementProgress(pydantic.BaseModel):
  """Progress on one requirement of a program."""

  position: int = pydantic.Field(description="The requirement's position.")
  status: RequirementStatus
  units: float = pydantic.Field(
    description="Units earned here and in nested requirements."
  )
  courses: list[str] = pydantic.Field(
    description="Completed codes filling this requirement's own slots."
  )


class ProgramAuditRequest(pydantic.BaseModel):
  """What a student has done: courses taken and AP exams passed."""

  completed: list[str]
  ap_credits: list[ApCredit] = []
  ge_counted: dict[str, int] = pydantic.Field(
    default={}, description="GE seats the student counted by hand, by code."
  )


class ProgramAudit(pydantic.BaseModel):
  """A program audited against completed courses in a planning term."""

  units: float = pydantic.Field(
    description=(
      "Units of every completed course with known units, plus passed AP exams."
    )
  )
  requirements: list[RequirementProgress]
  locked: dict[str, list[str]] = pydantic.Field(
    description=(
      "Program courses whose prerequisites are not yet met, each mapped to "
      "the untaken courses of its unmet prerequisite groups."
    )
  )


# =============================================================================
# Database Table Row Dataclasses (SQLite Internal Records)
# =============================================================================


@dataclasses.dataclass(frozen=True, slots=True)
class TermRow:
  """An academic term, e.g. Spring 2027 (20271)."""

  code: int
  year: int
  season: str
  status: str


@dataclasses.dataclass(frozen=True, slots=True)
class SchoolRow:
  """A USC school, e.g. ENGV (Viterbi)."""

  code: str
  name: str


@dataclasses.dataclass(frozen=True, slots=True)
class DepartmentRow:
  """A course-prefix program, e.g. CSCI, within a school."""

  code: str
  name: str
  school_code: str | None  # None for prefixes only the catalogue lists
  note: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class CourseRow:
  """A course's identity across terms."""

  code: str
  key: str  # identity: department, number, sequence (codes.course_key)
  department_code: str
  number: str
  suffix: str


@dataclasses.dataclass(frozen=True, slots=True)
class OfferingRow:
  """A course as offered in one term."""

  term_code: int
  course_code: str
  usc_course_id: int
  title: str
  description: str
  units_min: float
  units_max: float
  recommended_prep: str | None
  duplicate_credit: str | None
  course_notes: str | None
  term_notes: str | None
  is_cross_listed: bool


@dataclasses.dataclass(frozen=True, slots=True)
class OfferingUscGeRow:
  """One of USC's numeric GE codes for an offering."""

  term_code: int
  course_code: str
  usc_ge_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class RequisiteGroupRow:
  """A requisite group; met by `required_count` of its options."""

  term_code: int
  course_code: str
  kind: str
  position: int
  required_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class RequisiteCourseRow:
  """One course within a requisite option (options AND their courses)."""

  term_code: int
  course_code: str
  kind: str
  group_position: int
  option_position: int
  position: int
  required_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class RestrictionRow:
  """An enrollment restriction by class standing, major, or school."""

  term_code: int
  course_code: str
  kind: str
  position: int
  code: str
  description: str
  inclusive: bool


@dataclasses.dataclass(frozen=True, slots=True)
class SessionRow:
  """A registration session within a term (regular, or a shorter one)."""

  term_code: int
  code: str
  usc_session_id: int


@dataclasses.dataclass(frozen=True, slots=True)
class SectionRow:
  """A registrable section of an offering."""

  term_code: int
  id: str
  course_code: str
  usc_section_id: int | None
  type: str
  type_code: str | None
  link_code: str | None
  session_code: str | None
  name: str | None
  units_min: float | None
  units_max: float | None
  requires_d_clearance: bool
  is_cancelled: bool
  registered: int
  capacity: int
  waitlisted: int
  description: str | None
  notes: str | None
  syllabus_url: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class MeetingRow:
  """A weekly meeting pattern of a section; `days` is a weekday bitmask."""

  term_code: int
  section_id: str
  position: int
  days: int
  start_minute: int | None
  end_minute: int | None


@dataclasses.dataclass(frozen=True, slots=True)
class InstructorRow:
  """A person who teaches sections, keyed by normalized name."""

  key: str
  first_name: str
  last_name: str


@dataclasses.dataclass(frozen=True, slots=True)
class SectionInstructorRow:
  """An instructor's place on a section's teaching list."""

  term_code: int
  section_id: str
  position: int
  instructor_key: str


@dataclasses.dataclass(frozen=True, slots=True)
class RmpProfileRow:
  """An instructor's RateMyProfessors profile."""

  instructor_key: str
  rmp_id: int
  department: str
  rating: float | None
  difficulty: float | None
  num_ratings: int
  would_take_again: float | None


@dataclasses.dataclass(frozen=True, slots=True)
class GeCategoryRow:
  """A general-education category and how many courses it needs."""

  code: str
  name: str
  area: str
  required_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class ApExamRow:
  """An AP exam USC grants credit for at `min_score` or above."""

  id: str
  name: str
  min_score: int
  units: float


@dataclasses.dataclass(frozen=True, slots=True)
class ApExamGeRow:
  """A GE category an AP exam satisfies."""

  exam_id: str
  ge_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class ApExamWaiverRow:
  """A course an AP exam waives."""

  exam_id: str
  waived_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class CatalogueRow:
  """A catalogue year, which degree programs belong to."""

  id: int
  name: str


@dataclasses.dataclass(frozen=True, slots=True)
class GeCourseRow:
  """A course listed under a GE category in a catalogue year."""

  catalogue_id: int
  ge_code: str
  listed_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class CatalogueCourseRow:
  """A course as the catalogue defines it for a year; mirrors the table."""

  catalogue_id: int
  code: str
  title: str
  units_min: float | None
  units_max: float | None
  units_text: str
  max_units: float | None
  terms_offered: str | None
  instruction_mode: str | None
  grading_option: str | None
  description: str | None
  prerequisite: str | None
  corequisite: str | None
  concurrent: str | None
  recommended_prep: str | None
  registration_restriction: str | None
  credit_restriction: str | None
  duplicate_credit: str | None
  cross_listed_code: str | None
  enroll_in_code: str | None
  notes: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class ProgramRow:
  """A degree, minor, certificate, or other program in a catalogue year."""

  id: str
  catalogue_id: int
  poid: int
  title: str
  name: str
  emphasis: str | None
  kind: str
  degree_type: str | None
  school: str | None
  total_units: float | None
  total_units_stated: bool
  description: str


@dataclasses.dataclass(frozen=True, slots=True)
class ProgramRequirementRow:
  """A requirement heading in a program, possibly nested."""

  program_id: str
  position: int
  parent_position: int | None
  title: str
  units_min: float | None
  units_max: float | None
  notes: str
  is_general_education: bool


@dataclasses.dataclass(frozen=True, slots=True)
class ProgramRequirementChoiceRow:
  """One alternative for one slot of a requirement."""

  program_id: str
  requirement_position: int
  slot: int
  position: int
  listed_code: str
  units_min: float | None
  units_max: float | None


__all__ = [
  # API boundary models
  "ApCredit",
  "ApExam",
  "Course",
  "CourseRef",
  "GeAuditRequest",
  "GeCategory",
  "GeProgress",
  "Instructor",
  "KnownCourse",
  "Meeting",
  "Program",
  "ProgramAudit",
  "ProgramAuditRequest",
  "ProgramSummary",
  "Rating",
  "Requirement",
  "RequirementChoice",
  "RequirementProgress",
  "RequirementStatus",
  "RequisiteGroup",
  "Requisites",
  "Restriction",
  "Section",
  "Term",
  "Units",
  "Weekday",
  # Database table row dataclasses
  "ApExamGeRow",
  "ApExamRow",
  "ApExamWaiverRow",
  "CatalogueCourseRow",
  "CatalogueRow",
  "CourseRow",
  "DepartmentRow",
  "GeCategoryRow",
  "GeCourseRow",
  "InstructorRow",
  "MeetingRow",
  "OfferingRow",
  "OfferingUscGeRow",
  "ProgramRequirementChoiceRow",
  "ProgramRequirementRow",
  "ProgramRow",
  "RequisiteCourseRow",
  "RequisiteGroupRow",
  "RestrictionRow",
  "RmpProfileRow",
  "SchoolRow",
  "SectionInstructorRow",
  "SectionRow",
  "SessionRow",
  "TermRow",
]
