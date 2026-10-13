"""Parses classes.usc.edu API payloads into catalog records.

Pure functions over raw JSON as the fetcher cached it: no I/O, so they are
tested against saved fixtures. They keep every field USC provides that has
meaning to a student, normalized into the record types, and leave
cross-file concerns (deduplication, code resolution) to the builder.
"""

import dataclasses
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from server.src.catalog import codes, records


# Weekday bitmask used by `meeting.days`.
DAY_BITS: Mapping[str, int] = {
  "Mon": 1,
  "Tue": 2,
  "Wed": 4,
  "Thu": 8,
  "Fri": 16,
  "Sat": 32,
  "Sun": 64,
}

_REQUISITE_FIELDS: Mapping[str, str] = {
  "prerequisite": "prerequisiteCourseCodes",
  "corequisite": "corequisiteCourseCodes",
  "concurrent": "concurrentCourses",
}
_RESTRICTION_FIELDS: Mapping[str, str] = {
  "class": "courseRestrictions",
  "major": "majorRestrictions",
  "school": "schoolRestrictions",
}
_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclasses.dataclass(frozen=True)
class Listing:
  """Everything one course listing (term, school, program) describes."""

  courses: list[records.Course]
  offerings: list[records.Offering]
  usc_ge_codes: list[records.OfferingUscGe]
  requisite_groups: list[records.RequisiteGroup]
  requisite_courses: list[records.RequisiteCourse]
  restrictions: list[records.Restriction]
  sections: list[records.Section]
  meetings: list[records.Meeting]
  instructors: list[records.Instructor]
  section_instructors: list[records.SectionInstructor]


def parse_terms(raw: Sequence[Mapping[str, Any]]) -> list[records.Term]:
  """Parses `/Terms/All`."""
  return [
    records.Term(
      code=int(t["termCode"]),
      year=int(t["year"]),
      season=str(t["season"]),
      status=str(t["status"]),
    )
    for t in raw
  ]


def parse_schools(
  raw: Sequence[Mapping[str, Any]],
) -> tuple[list[records.School], list[records.Department]]:
  """Parses `/Schools/TermCode` into schools and their departments.

  A department listed under several schools (rare, e.g. ANAT) belongs to the
  first in USC's sort order.
  """
  schools: list[records.School] = []
  departments: dict[str, records.Department] = {}
  for school in sorted(raw, key=lambda s: s.get("sortOrder") or 0):
    code = str(school["prefix"])
    schools.append(records.School(code=code, name=str(school["name"])))
    for program in school.get("programs") or []:
      prefix = str(program["prefix"])
      departments.setdefault(
        prefix.upper(),
        records.Department(
          code=prefix,
          name=str(program.get("name") or prefix),
          school_code=code,
          note=_text(program.get("programNote")),
        ),
      )
  return schools, list(departments.values())


def course_code(prefix: str, number: str, suffix: str | None) -> str:
  """Builds a canonical code such as CSCI-104L from its parts."""
  return f"{prefix}-{number}{suffix or ''}"


def parse_listing(raw: Mapping[str, Any], term: int) -> Listing:
  """Parses one `/Courses/CoursesByTermSchoolProgram` payload."""
  out = Listing([], [], [], [], [], [], [], [], [], [])
  for course in raw.get("courses") or []:
    _parse_course(course, term, out)
  return out


def _parse_course(course: Mapping[str, Any], term: int, out: Listing) -> None:
  prefix = str(course["prefix"])
  number = str(course["classNumber"])
  # A sequence letter (597A of 597A/597B) precedes the suffix: ARCH-102AL.
  suffix = f"{course.get('sequence') or ''}{course.get('suffix') or ''}"
  code = course_code(prefix, number, suffix)
  units_min, units_max = _units(
    course.get("courseUnits"), course.get("maxUnits")
  )

  out.courses.append(
    records.Course(
      code=code,
      key=codes.course_key(code) or code.upper(),
      department_code=prefix,
      number=number,
      suffix=suffix,
    )
  )
  out.offerings.append(
    records.Offering(
      term_code=term,
      course_code=code,
      usc_course_id=int(course["courseId"]),
      title=str(course.get("name") or code),
      description=str(course.get("description") or "").strip(),
      units_min=units_min,
      units_max=units_max,
      recommended_prep=_text(course.get("recommendedPrep")),
      duplicate_credit=_text(course.get("duplicateCredit")),
      course_notes=_text(course.get("courseNotes")),
      term_notes=_text(course.get("termNotes")),
      is_cross_listed=bool(course.get("isCrossListed")),
    )
  )
  if usc_ge := _text(course.get("geCode")):
    out.usc_ge_codes.append(records.OfferingUscGe(term, code, usc_ge))
  for kind, field in _REQUISITE_FIELDS.items():
    _parse_requisites(course.get(field) or [], term, code, kind, out)
  for kind, field in _RESTRICTION_FIELDS.items():
    _parse_restrictions(course.get(field) or [], term, code, kind, out)
  for section in course.get("sections") or []:
    _parse_section(section, term, code, out)


def _units(course_units: Any, max_units: Any) -> tuple[float, float]:
  """Returns (min, max) units; `courseUnits` lists every allowed value."""
  values = [float(u) for u in course_units or [] if u is not None]
  if values:
    return min(values), max(values)
  if max_units is not None:
    return 0.0, float(max_units)
  return 0.0, 0.0


def _parse_requisites(
  groups: Iterable[Mapping[str, Any]],
  term: int,
  code: str,
  kind: str,
  out: Listing,
) -> None:
  for g_pos, group in enumerate(groups):
    options = group.get("courseOptions") or []
    out.requisite_groups.append(
      records.RequisiteGroup(
        term_code=term,
        course_code=code,
        kind=kind,
        position=g_pos,
        required_count=int(group.get("requiredCourses") or 1),
      )
    )
    for o_pos, option in enumerate(options):
      # An option is its own course plus any it must be taken with ("ands").
      members: list[Mapping[str, Any]] = [option, *(option.get("ands") or [])]
      for c_pos, member in enumerate(members):
        out.requisite_courses.append(
          records.RequisiteCourse(
            term_code=term,
            course_code=code,
            kind=kind,
            group_position=g_pos,
            option_position=o_pos,
            position=c_pos,
            required_code=course_code(
              str(member["prefix"]), str(member["number"]), member.get("suffix")
            ),
          )
        )


def _parse_restrictions(
  entries: Iterable[Mapping[str, Any]],
  term: int,
  code: str,
  kind: str,
  out: Listing,
) -> None:
  for pos, item in enumerate(entries):
    out.restrictions.append(
      records.Restriction(
        term_code=term,
        course_code=code,
        kind=kind,
        position=pos,
        code=str(item["groupCode"]),
        description=str(item.get("groupDescription") or item["groupCode"]),
        inclusive=str(item.get("restrictionCode") or "I") == "I",
      )
    )


def _parse_section(
  section: Mapping[str, Any], term: int, code: str, out: Listing
) -> None:
  section_id = str(section["sisSectionId"])
  units = [float(u) for u in section.get("units") or []]
  session = section.get("session") or {}
  out.sections.append(
    records.Section(
      term_code=term,
      id=section_id,
      course_code=code,
      usc_section_id=(
        int(section["peSectionId"]) if section.get("peSectionId") else None
      ),
      type=str(section.get("rnrMode") or "Lecture"),
      type_code=_text(section.get("rnrModeCode")),
      link_code=_text(section.get("linkCode")),
      session_code=_text(session.get("rnrSessionCode")),
      name=_text(section.get("name")),
      units_min=min(units) if units else None,
      units_max=max(units) if units else None,
      requires_d_clearance=bool(section.get("hasDClearance")),
      is_cancelled=bool(section.get("isCancelled")),
      registered=int(section.get("registeredSeats") or 0),
      capacity=int(section.get("totalSeats") or 0),
      waitlisted=int(section.get("waitlistedSeats") or 0),
      description=_text(section.get("description")),
      notes=_text(section.get("notes")),
      syllabus_url=_text(section.get("syllabus")),
    )
  )
  for pos, meeting in enumerate(section.get("schedule") or []):
    out.meetings.append(_parse_meeting(meeting, term, section_id, pos))
  for pos, person in enumerate(section.get("instructors") or []):
    instructor = parse_instructor(person)
    if instructor is None:
      continue
    out.instructors.append(instructor)
    out.section_instructors.append(
      records.SectionInstructor(
        term_code=term,
        section_id=section_id,
        position=pos,
        instructor_key=instructor.key,
      )
    )


def _parse_meeting(
  meeting: Mapping[str, Any], term: int, section_id: str, position: int
) -> records.Meeting:
  days = 0
  for day in meeting.get("days") or []:
    days |= DAY_BITS.get(str(day), 0)
  start = _minutes(meeting.get("startTime"))
  end = _minutes(meeting.get("endTime"))
  timed = start is not None and end is not None and days != 0
  return records.Meeting(
    term_code=term,
    section_id=section_id,
    position=position,
    days=days if timed else 0,
    start_minute=start if timed else None,
    end_minute=end if timed else None,
  )


def _minutes(clock: Any) -> int | None:
  """Converts "HH:MM" to minutes after midnight; None for TBA or junk."""
  match = _CLOCK.match(str(clock or ""))
  if match is None:
    return None
  return int(match.group(1)) * 60 + int(match.group(2))


def instructor_key(first: str, last: str) -> str:
  """Normalizes a name into the key instructors are stored under."""
  return " ".join(f"{first} {last}".lower().split())


def parse_instructor(person: Mapping[str, Any]) -> records.Instructor | None:
  """Builds an instructor from USC's name fields; None when nameless."""
  first = " ".join(str(person.get("firstName") or "").split())
  last = " ".join(str(person.get("lastName") or "").split())
  if not (first or last):
    return None
  return records.Instructor(
    key=instructor_key(first, last), first_name=first, last_name=last
  )


def _text(value: Any) -> str | None:
  """Normalizes optional text: blank or missing becomes None."""
  if value is None:
    return None
  text = str(value).strip()
  return text or None
