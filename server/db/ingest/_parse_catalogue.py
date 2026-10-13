"""Parses catalogue.usc.edu (Acalog) pages into catalog records.

Pure functions over cached HTML. A program page is read as an ordered list
of text blocks (headings, paragraphs, list items); headings become a
requirement tree, course items become choice slots (consecutive items joined
by "or" share a slot), and prose becomes requirement notes. The General
Education program page additionally yields the per-category course lists.
"""

import dataclasses
import html.parser
import re
from collections.abc import Sequence

from server.db import models


_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCKS = _HEADINGS | {"p", "li"}
_POID = re.compile(r"poid=(\d+)")
# A program total is a line of nothing but total wording and a number:
# "Total units: 128", "Total minimum units required for the degree: 132".
# Subtotals ("Total business units: 60") name a subject and do not match.
_TOTAL = re.compile(
  r"^total\s+(?:(?:minimum|required|program)\s+)*units?"
  r"(?:\s+required)?(?:\s+for\s+(?:the\s+)?degree)?\s*:?\s*"
  r"(?:minimum\s+of\s+)?(\d+(?:\.\d+)?)\s*\+?\.?$",
  re.IGNORECASE,
)
_RANGE = r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?"
# Units in a heading: "Core (16 units)" or "Elective Units: 6".
_HEADING_UNITS = re.compile(
  rf"\(\s*{_RANGE}\s+units?\s*\)|\bunits?(?:\s+required)?:\s*{_RANGE}\s*\+?$",
  re.IGNORECASE,
)
_ITEM_UNITS = re.compile(rf"Units:\s*{_RANGE}", re.IGNORECASE)
_COURSE = re.compile(r"^([A-Z]{2,5})\s+(\d{3}[A-Za-z]{0,4})\b")
_TRAILING_OR = re.compile(r"\bor\s*$", re.IGNORECASE)
_GE_HEADING = re.compile(r"^(GE-[A-H])\b[.:]?\s*(.*)$")
_DEGREE_TYPE = re.compile(r"^[A-Z][A-Za-z]*(?:/[A-Z][A-Za-z]*)*$")
_NOT_DEGREE_TYPES = frozenset({"Online"})


@dataclasses.dataclass(frozen=True)
class Block:
  """A text-bearing element in document order."""

  tag: str
  classes: frozenset[str]
  text: str


@dataclasses.dataclass(frozen=True)
class ProgramLink:
  """A program listed in the catalogue index."""

  poid: int
  title: str


@dataclasses.dataclass(frozen=True)
class ProgramPage:
  """Everything one program page describes."""

  program: models.ProgramRow
  requirements: list[models.ProgramRequirementRow]
  choices: list[models.ProgramRequirementChoiceRow]


@dataclasses.dataclass
class _Heading:
  """A requirement heading being filled in while the page is walked."""

  position: int
  parent: int | None
  title: str
  units_min: float | None
  units_max: float | None
  notes: list[str] = dataclasses.field(default_factory=list)

  def record(self, program_id: str) -> models.ProgramRequirementRow:
    return models.ProgramRequirementRow(
      program_id=program_id,
      position=self.position,
      parent_position=self.parent,
      title=self.title,
      units_min=self.units_min,
      units_max=self.units_max,
      notes="\n".join(self.notes),
      is_general_education="general education" in self.title.lower(),
    )


class _BlockReader(html.parser.HTMLParser):
  """Flattens HTML into blocks, keeping nested text inside its outer block.

  Acalog nests "or" connectors inside course items, so text is collected per
  outermost block. A <p> ends at the next block start even if never closed.
  """

  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self.blocks: list[Block] = []
    self._tag: str | None = None
    self._classes: frozenset[str] = frozenset()
    self._nesting = 0
    self._text: list[str] = []

  def handle_starttag(
    self, tag: str, attrs: list[tuple[str, str | None]]
  ) -> None:
    if self._tag == "p" and tag in _BLOCKS:
      self._flush()
    if self._tag is not None:
      if tag == self._tag:
        self._nesting += 1
      return
    if tag in _BLOCKS:
      self._tag = tag
      self._classes = frozenset((dict(attrs).get("class") or "").split())
      self._nesting = 0
      self._text = []

  def handle_endtag(self, tag: str) -> None:
    if tag != self._tag:
      return
    if self._nesting:
      self._nesting -= 1
      return
    self._flush()

  def handle_data(self, data: str) -> None:
    if self._tag is not None:
      self._text.append(data)

  def _flush(self) -> None:
    # Acalog pads text with zero-width spaces and BOMs; drop them.
    raw = "".join(self._text).replace("​", "").replace("﻿", "")
    text = " ".join(raw.split())
    if self._tag is not None and text:
      self.blocks.append(Block(self._tag, self._classes, text))
    self._tag = None


def read_blocks(page: str) -> list[Block]:
  """Returns the page's text blocks in document order."""
  reader = _BlockReader()
  reader.feed(page)
  reader.close()
  return reader.blocks


def parse_catalogue(index_html: str) -> models.CatalogueRow:
  """Reads the selected catalogue year from the index page's year menu.

  Raises:
    ValueError: The page has no selected catalogue option.
  """
  match = re.search(
    r'<option value="(\d+)"[^>]*selected[^>]*>([^<]*Catalogue[^<]*)</option>',
    index_html,
  )
  if match is None:
    raise ValueError("Catalogue index has no selected catalogue year")
  return models.CatalogueRow(
    id=int(match.group(1)), name=match.group(2).strip()
  )


def parse_index(index_html: str) -> list[ProgramLink]:
  """Lists every program linked from the catalogue's program index."""
  links: dict[int, ProgramLink] = {}
  pattern = re.compile(
    r'<a[^>]*href="[^"]*preview_program\.php\?[^"]*"[^>]*>(.*?)</a>', re.DOTALL
  )
  for match in pattern.finditer(index_html):
    poid = _POID.search(match.group(0))
    title = " ".join(re.sub(r"<[^>]+>", "", match.group(1)).split())
    if poid and title:
      links.setdefault(
        int(poid.group(1)), ProgramLink(int(poid.group(1)), title)
      )
  return list(links.values())


def _heading_units(text: str) -> tuple[float | None, float | None]:
  match = _HEADING_UNITS.search(text)
  if match is None:
    return None, None
  # Whichever alternative matched holds the range in its pair of groups.
  groups = match.groups()
  low, high = groups[:2] if groups[0] else groups[2:]
  return float(low), float(high or low)


def _units(match: re.Match[str] | None) -> tuple[float | None, float | None]:
  if match is None:
    return None, None
  low = float(match.group(1))
  return low, float(match.group(2)) if match.group(2) else low


def program_identity(
  title: str,
) -> tuple[str, str | None, str, str | None]:
  """Splits a program title into (name, emphasis, kind, degree type).

  "American Studies and Ethnicity (Asian American Studies) (BA)" becomes
  name "American Studies and Ethnicity", emphasis "Asian American Studies",
  kind "degree", type "BA". Footnote stars are dropped.
  """
  rest = title.rstrip("* ").strip()
  degree_type: str | None = None
  extras: list[str] = []
  while (m := re.search(r"\s*\(([^()]+)\)\s*$", rest)) is not None:
    inner = m.group(1).strip()
    if (
      degree_type is None
      and _DEGREE_TYPE.match(inner)
      and inner not in _NOT_DEGREE_TYPES
    ):
      degree_type = inner
    else:
      extras.insert(0, inner)
    rest = rest[: m.start()].rstrip()
  emphasis = "; ".join(extras) or None
  lowered = title.lower()
  if degree_type is not None:
    kind = "degree"
  elif "minor" in lowered:
    kind = "minor"
  elif "certificate" in lowered:
    kind = "certificate"
  else:
    kind = "other"
  return rest, emphasis, kind, degree_type


def slugify(title: str) -> str:
  """Makes a URL-safe program id from its title."""
  return re.sub(r"[^a-z0-9]+", "-", title.lower().rstrip("* ")).strip("-")


def listed_code(text: str) -> str | None:
  """Extracts "MATH-126g" from "MATH 126g Calculus II Units: 4 or"."""
  match = _COURSE.match(text)
  return f"{match.group(1)}-{match.group(2)}" if match else None


def parse_program(
  page: str, catalogue_id: int, link: ProgramLink, program_id: str
) -> ProgramPage:
  """Parses one program page into a program, its requirements, and choices.

  Raises:
    ValueError: The page has no program heading (not a program page).
  """
  blocks = read_blocks(page)
  start = next((i for i, b in enumerate(blocks) if b.tag == "h1"), None)
  if start is None:
    raise ValueError(f"Program page {link.poid} has no title heading")

  description: list[str] = []
  requirements: list[_Heading] = []
  choices: list[models.ProgramRequirementChoiceRow] = []
  open_levels: list[tuple[int, int]] = []  # (heading level, position)
  slot = -1
  slot_size = 0
  joins_next = False
  total: float | None = None
  school: str | None = None
  # Text after "Total units" is program-wide footnotes, not the last
  # requirement's notes.
  past_total = False

  for block in blocks[start + 1 :]:
    if "close" in block.classes:
      break
    total_match = _TOTAL.match(block.text)
    if total_match:
      total = float(total_match.group(1))
      past_total = True
      continue
    if block.tag in _HEADINGS:
      level = int(block.tag[1])
      while open_levels and open_levels[-1][0] >= level:
        open_levels.pop()
      units_min, units_max = _heading_units(block.text)
      title = _HEADING_UNITS.sub("", block.text).strip(" :-")
      requirements.append(
        _Heading(
          position=len(requirements),
          parent=open_levels[-1][1] if open_levels else None,
          title=title or block.text,
          units_min=units_min,
          units_max=units_max,
        )
      )
      open_levels.append((level, len(requirements) - 1))
      slot, slot_size, joins_next = -1, 0, False
      continue

    text = block.text
    if text.lower().startswith("return to:"):
      school = text.split(":", 1)[1].strip() or None
      continue
    if text.lower() == "or":
      joins_next = True
      continue
    code = listed_code(text) if "acalog-course" in block.classes else None
    if past_total or code is None or not requirements:
      in_requirement = requirements and not past_total
      (requirements[-1].notes if in_requirement else description).append(text)
      continue

    if joins_next and slot >= 0:
      slot_size += 1
    else:
      slot, slot_size = slot + 1, 1
    units_min, units_max = _units(_ITEM_UNITS.search(text))
    choices.append(
      models.ProgramRequirementChoiceRow(
        program_id=program_id,
        requirement_position=requirements[-1].position,
        slot=slot,
        position=slot_size - 1,
        listed_code=code,
        units_min=units_min,
        units_max=units_max,
      )
    )
    joins_next = bool(_TRAILING_OR.search(text))

  name, emphasis, kind, degree_type = program_identity(link.title)
  program = models.ProgramRow(
    id=program_id,
    catalogue_id=catalogue_id,
    poid=link.poid,
    title=link.title.rstrip("* ").strip(),
    name=name,
    emphasis=emphasis,
    kind=kind,
    degree_type=degree_type,
    school=school,
    total_units=total,
    total_units_stated=total is not None,
    description="\n".join(description),
  )
  return ProgramPage(
    program=program,
    requirements=[r.record(program_id) for r in requirements],
    choices=choices,
  )


def parse_ge_lists(page: str, catalogue_id: int) -> list[models.GeCourseRow]:
  """Reads the General Education page's per-category course lists."""
  courses: dict[tuple[str, str], models.GeCourseRow] = {}
  category: str | None = None
  for block in read_blocks(page):
    if block.tag in _HEADINGS:
      match = _GE_HEADING.match(block.text)
      category = match.group(1) if match else None
      continue
    code = listed_code(block.text) if "acalog-course" in block.classes else None
    if category is not None and code is not None:
      courses.setdefault(
        (category, code),
        models.GeCourseRow(
          catalogue_id=catalogue_id, ge_code=category, listed_code=code
        ),
      )
  return list(courses.values())


def ge_category_names(page: str) -> dict[str, str]:
  """Maps GE codes to the names the catalogue gives them, e.g. The Arts."""
  names: dict[str, str] = {}
  for block in read_blocks(page):
    if block.tag in _HEADINGS and (m := _GE_HEADING.match(block.text)):
      names.setdefault(m.group(1), m.group(2).strip())
  return names


def program_ids(links: Sequence[ProgramLink]) -> dict[int, str]:
  """Assigns each program a unique slug; repeats get their poid appended."""
  ids: dict[int, str] = {}
  taken: set[str] = set()
  for link in links:
    slug = slugify(link.title)
    if slug in taken:
      slug = f"{slug}-{link.poid}"
    taken.add(slug)
    ids[link.poid] = slug
  return ids


__all__ = [
  "Block",
  "ProgramLink",
  "ProgramPage",
  "ge_category_names",
  "listed_code",
  "parse_catalogue",
  "parse_ge_lists",
  "parse_index",
  "parse_program",
  "program_identity",
  "program_ids",
  "read_blocks",
  "slugify",
]
