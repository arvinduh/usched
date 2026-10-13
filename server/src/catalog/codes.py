"""Course identity: what makes two spellings of a code the same course.

A code is department, number, an optional sequence letter (the a of
CHEM 105a), and attribute letters (L lab, g GE, x, m, w, p). Sources
disagree on attributes, writing MATH-118gx and MATH-118xg, or ACAD-490x
and ACAD-490, but never on department, number, and sequence. The key
built from those three is the course's identity everywhere: the build
merges by it and the API looks codes up through it.
"""

import re


_PARTS = re.compile(r"^\s*([A-Za-z]{2,5})[\s-]*(\d{3})([A-Za-z]*)\s*$")
_ATTRIBUTES = frozenset("lgxmwp")


def course_key(code: str) -> str | None:
  """Returns a code's identity, e.g. CHEM-105aLg -> CHEM-105A.

  Returns None for text that is not a course code.
  """
  match = _PARTS.match(code)
  if match is None:
    return None
  department, number, letters = match.groups()
  first = letters[:1].lower()
  sequence = first.upper() if first and first not in _ATTRIBUTES else ""
  return f"{department.upper()}-{number}{sequence}"


def identity(code: str) -> str:
  """Returns the key that compares codes: course_key, else the text itself.

  Text that is not a code (a placeholder some source wrote) still gets a
  stable, case-insensitive key, so callers never special-case None.
  """
  return course_key(code) or code.strip().upper()
