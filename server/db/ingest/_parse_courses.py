"""Parses the catalogue's course index ("Courses of Instruction").

The catalogue is USC's definition of every course: code, title, units,
description, and the prose rules (prerequisites, restrictions) that
apply across terms. Its index pages, fetched in expanded form, list one
hundred courses each with their details inline. This module turns those
pages into records; fetching belongs to catalogue_site.
"""

import dataclasses
import html
import re

from server.db import models


_COURSES_LINK = re.compile(
  r'navoid=(\d+)"[^>]*>\s*Courses of Instruction', re.IGNORECASE
)
_PAGE = re.compile(r"filter%5Bcpage%5D=(\d+)")
_ITEM = re.compile(r"<h2>(.*?)</h2>|<h3>(.*?)</h3>(.*?)</li>", re.DOTALL)
_HEAD = re.compile(r"^([A-Z]{2,5}) (\d{3}[A-Za-z]{0,4}) (.+)$")
_CODE = re.compile(r"\b([A-Z]{2,5}) (\d{3}[A-Za-z]{0,4})\b")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_GE = re.compile(
  r"^Satisfies (?:New General Education|Global Perspective) in Category ([A-H])"
)
# GE Seminars: GESM 1X0 and 1X1 fill Core category X (1 for GE-A up to
# 6 for GE-F), and every GESM fills the seminar requirement. The number decides,
# so neither depends on how an entry words its GE statement.
_SEMINAR_CORE = re.compile(r"^1([1-6])[01]")
# The closed set of labeled fields. Other "Words: ..." lines are description
# sentences that happen to contain a colon.
_FIELDS = {
  "Units": "units_text",
  "Maximum Units": "max_units",
  "Terms Offered": "terms_offered",
  "Instruction Mode": "instruction_mode",
  "Grading Option": "grading_option",
  "Prerequisite": "prerequisite",
  "Corequisite": "corequisite",
  "Concurrent Enrollment": "concurrent",
  "Recommended Preparation": "recommended_prep",
  "Registration Restriction": "registration_restriction",
  "Credit Restriction": "credit_restriction",
}
_LABEL = re.compile(
  rf"^({'|'.join(map(re.escape, _FIELDS))}):\s*(.*)$", re.IGNORECASE
)
_FIELD_BY_LABEL = {label.lower(): field for label, field in _FIELDS.items()}


@dataclasses.dataclass(frozen=True)
class CoursePage:
  """Everything one course index page describes.

  Attributes:
    courses: Course definitions in page order.
    ge_courses: GE categories courses state they satisfy.
    department_names: Course prefix to the heading it is listed under.
  """

  courses: list[models.CatalogueCourseRow]
  ge_courses: list[models.GeCourseRow]
  department_names: dict[str, str]


def course_index_navoid(index_html: str) -> int:
  """Finds the course index's navigation id on any catalogue page.

  Raises:
    ValueError: The page links no "Courses of Instruction" index.
  """
  match = _COURSES_LINK.search(index_html)
  if match is None:
    raise ValueError("No Courses of Instruction link on the catalogue page")
  return int(match.group(1))


def page_count(first_page: str) -> int:
  """Reads how many index pages there are from the first one's pager."""
  return max((int(p) for p in _PAGE.findall(first_page)), default=1)


def _text(fragment: str) -> str:
  """Strips tags and entities, collapsing whitespace."""
  plain = html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("\xa0", " ")
  plain = " ".join(plain.split())
  # Link text leaves a space before punctuation: "ACAD 260 ." -> "ACAD 260."
  return re.sub(r" ([.,;)])", r"\1", plain).replace("( ", "(")


def _code(text: str) -> str | None:
  match = _CODE.search(text)
  return f"{match.group(1)}-{match.group(2)}" if match else None


def _lines(body: str) -> list[str]:
  """Splits an entry body into text lines; <em> labels start new lines."""
  body = re.sub(r"<em>(.*?)</em>", r"<br>\1", body, flags=re.DOTALL)
  parts = re.split(r"<br\s*/?>|<hr\s*/?>", body)
  return [line for line in map(_text, parts) if line]


def _seminar_ge(
  prefix: str, number: str, catalogue_id: int
) -> list[models.GeCourseRow]:
  """The GE seats a GE Seminar fills by its number; none for other courses."""
  if prefix != "GESM":
    return []
  code = f"{prefix}-{number}"
  rows = [models.GeCourseRow(catalogue_id, "GESM", code)]
  if core := _SEMINAR_CORE.match(number):
    letter = "ABCDEF"[int(core.group(1)) - 1]
    rows.append(models.GeCourseRow(catalogue_id, f"GE-{letter}", code))
  return rows


def parse_page(page: str, catalogue_id: int) -> CoursePage:
  """Parses one expanded course index page."""
  out = CoursePage([], [], {})
  heading = ""
  for match in _ITEM.finditer(page):
    if match.group(1) is not None:
      heading = _text(match.group(1))
      continue
    head = _HEAD.match(_text(match.group(2)))
    if head is None:
      continue
    prefix, number, title = head.groups()
    code = f"{prefix}-{number}"
    out.department_names.setdefault(prefix, heading or prefix)
    fields: dict[str, str] = {}
    prose: list[str] = []
    for line in _lines(match.group(3)):
      labeled = _LABEL.match(line)
      ge = _GE.match(line)
      if labeled:
        fields[_FIELD_BY_LABEL[labeled.group(1).lower()]] = labeled.group(2)
      elif ge:
        out.ge_courses.append(
          models.GeCourseRow(catalogue_id, f"GE-{ge.group(1)}", code)
        )
      elif line.startswith("Duplicates Credit"):
        fields["duplicate_credit"] = line.removeprefix(
          "Duplicates Credit"
        ).strip()
      elif line.startswith("Cross-listed as"):
        fields["cross_listed_code"] = _code(line) or line
      elif line.startswith("(Enroll in"):
        fields["enroll_in_code"] = _code(line) or line
      else:
        prose.append(line)
    out.ge_courses.extend(_seminar_ge(prefix, number, catalogue_id))
    units_text = fields.get("units_text", "")
    numbers = [float(n) for n in _NUMBER.findall(units_text)]
    max_units = _NUMBER.search(fields.get("max_units", ""))
    out.courses.append(
      models.CatalogueCourseRow(
        catalogue_id=catalogue_id,
        code=code,
        title=title,
        units_min=min(numbers) if numbers else None,
        units_max=max(numbers) if numbers else None,
        units_text=units_text,
        max_units=float(max_units.group()) if max_units else None,
        terms_offered=fields.get("terms_offered"),
        instruction_mode=fields.get("instruction_mode"),
        grading_option=fields.get("grading_option"),
        description=prose[0] if prose else None,
        prerequisite=fields.get("prerequisite"),
        corequisite=fields.get("corequisite"),
        concurrent=fields.get("concurrent"),
        recommended_prep=fields.get("recommended_prep"),
        registration_restriction=fields.get("registration_restriction"),
        credit_restriction=fields.get("credit_restriction"),
        duplicate_credit=fields.get("duplicate_credit"),
        cross_listed_code=fields.get("cross_listed_code"),
        enroll_in_code=fields.get("enroll_in_code"),
        notes=" ".join(prose[1:]) or None,
      )
    )
  return out
