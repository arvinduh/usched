"""Action chips: one-tap follow-ups the advisor attaches to a reply.

Each chip is a typed command the client applies to its plan or opens. The
union is discriminated by `action`, so the generated client types narrow
on it and an unknown or malformed chip fails validation here, not
silently in the browser.
"""

from typing import Annotated, Literal

import pydantic


class ProposeSchedule(pydantic.BaseModel):
  """Previews a set of sections as a schedule the student can accept."""

  action: Literal["propose_schedule"] = "propose_schedule"
  label: str
  name: str
  section_ids: list[str]
  tradeoff: str = pydantic.Field(
    default="",
    description="Why to pick this week over the other options, e.g. "
    "'No class on Fri, avg prof 3.4'; empty when there is no choice.",
  )


class EnrollSection(pydantic.BaseModel):
  """Adds one section (and so its course) to the active schedule."""

  action: Literal["enroll_section"] = "enroll_section"
  label: str
  section_id: str


class WatchCourse(pydantic.BaseModel):
  """Shortlists a course without picking sections."""

  action: Literal["watch_course"] = "watch_course"
  label: str
  course_code: str


class MarkTaken(pydantic.BaseModel):
  """Records courses as taken; the client applies it with undo."""

  action: Literal["mark_taken"] = "mark_taken"
  label: str
  course_codes: list[str]


class Search(pydantic.BaseModel):
  """Runs a course search."""

  action: Literal["search"] = "search"
  label: str
  query: str


Chip = Annotated[
  ProposeSchedule | EnrollSection | WatchCourse | MarkTaken | Search,
  pydantic.Field(discriminator="action"),
]
