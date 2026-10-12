"""API models for catalog data: what the server returns about courses.

These shapes are the contract with the client (whose types are generated
from the OpenAPI schema they produce), so they follow the catalog schema's
structure: term-scoped offerings, every meeting and instructor, requisites
as pick-N groups of AND options, and programs as requirement trees.
Field docs carry units and invariants; names mirror the database.
"""

import enum

import pydantic


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
  sequence: str | None
  recommended_prep: str | None
  duplicate_credit: str | None
  course_notes: str | None
  term_notes: str | None
  is_cross_listed: bool
  ge: list[str] = pydantic.Field(description="GE categories, e.g. GE-B.")
  requisites: Requisites
  restrictions: list[Restriction]
  sections: list[Section]


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


class RequirementChoice(pydantic.BaseModel):
  """One course that can fill a requirement slot."""

  course: CourseRef
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


class GeProgress(pydantic.BaseModel):
  """How a GE category is filled; satisfied once filled reaches required."""

  code: str
  name: str
  required_count: int
  courses: list[str] = pydantic.Field(description="Completed codes used here.")
  exams: list[str] = pydantic.Field(description="AP exam ids used here.")
