"""Typed rows of the catalog database, one dataclass per table.

Parsers turn raw source payloads into these records and the builder writes
them; neither side touches the other's concerns. Field order matches the
table's column order in schema.sql so rows insert positionally; the builder
appends the one derived column, `resolved_code`, where a table has it.
"""

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class Term:
  """An academic term, e.g. Spring 2027 (20271)."""

  code: int
  year: int
  season: str
  status: str


@dataclasses.dataclass(frozen=True, slots=True)
class School:
  """A USC school, e.g. ENGV (Viterbi)."""

  code: str
  name: str


@dataclasses.dataclass(frozen=True, slots=True)
class Department:
  """A course-prefix program, e.g. CSCI, within a school."""

  code: str
  name: str
  school_code: str | None  # None for prefixes only the catalogue lists
  note: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class Course:
  """A course's identity across terms."""

  code: str
  key: str  # identity: department, number, sequence (codes.course_key)
  department_code: str
  number: str
  suffix: str


@dataclasses.dataclass(frozen=True, slots=True)
class Offering:
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
class OfferingUscGe:
  """One of USC's numeric GE codes for an offering."""

  term_code: int
  course_code: str
  usc_ge_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class RequisiteGroup:
  """A requisite group; met by `required_count` of its options."""

  term_code: int
  course_code: str
  kind: str
  position: int
  required_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class RequisiteCourse:
  """One course within a requisite option (options AND their courses)."""

  term_code: int
  course_code: str
  kind: str
  group_position: int
  option_position: int
  position: int
  required_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class Restriction:
  """An enrollment restriction by class standing, major, or school."""

  term_code: int
  course_code: str
  kind: str
  position: int
  code: str
  description: str
  inclusive: bool


@dataclasses.dataclass(frozen=True, slots=True)
class Section:
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
class Meeting:
  """A weekly meeting pattern of a section; `days` is a weekday bitmask."""

  term_code: int
  section_id: str
  position: int
  days: int
  start_minute: int | None
  end_minute: int | None


@dataclasses.dataclass(frozen=True, slots=True)
class Instructor:
  """A person who teaches sections, keyed by normalized name."""

  key: str
  first_name: str
  last_name: str


@dataclasses.dataclass(frozen=True, slots=True)
class SectionInstructor:
  """An instructor's place on a section's teaching list."""

  term_code: int
  section_id: str
  position: int
  instructor_key: str


@dataclasses.dataclass(frozen=True, slots=True)
class RmpProfile:
  """An instructor's RateMyProfessors profile."""

  instructor_key: str
  rmp_id: int
  department: str
  rating: float | None
  difficulty: float | None
  num_ratings: int
  would_take_again: float | None


@dataclasses.dataclass(frozen=True, slots=True)
class GeCategory:
  """A general-education category and how many courses it needs."""

  code: str
  name: str
  area: str
  required_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class ApExam:
  """An AP exam USC grants credit for at `min_score` or above."""

  id: str
  name: str
  min_score: int
  units: float


@dataclasses.dataclass(frozen=True, slots=True)
class ApExamGe:
  """A GE category an AP exam satisfies."""

  exam_id: str
  ge_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class ApExamWaiver:
  """A course an AP exam waives."""

  exam_id: str
  waived_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class Catalogue:
  """A catalogue year, which degree programs belong to."""

  id: int
  name: str


@dataclasses.dataclass(frozen=True, slots=True)
class GeCourse:
  """A course listed under a GE category in a catalogue year."""

  catalogue_id: int
  ge_code: str
  listed_code: str


@dataclasses.dataclass(frozen=True, slots=True)
class CatalogueCourse:
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
class Program:
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
class ProgramRequirement:
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
class ProgramRequirementChoice:
  """One alternative for one slot of a requirement."""

  program_id: str
  requirement_position: int
  slot: int
  position: int
  listed_code: str
  units_min: float | None
  units_max: float | None
