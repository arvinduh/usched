"""Turns free-form course search text into an FTS5 match expression.

Owns the search vocabulary: tokenization, abbreviation expansion ("cs" also
matches "computer science"), and recognizing course-code queries so they can
rank exact codes first. Executing the query and ranking belong to
`store`.
"""

import dataclasses
import json
import re

from server import config


# Common abbreviations students type, mapped to the phrases catalog titles
# and descriptions actually use. The abbreviation itself is always kept too.
# The client's program search reads the same file.
_ALIASES: dict[str, list[str]] = json.loads(
  (config.SEEDS_DIR / "abbreviations.json").read_text(encoding="utf-8")
)

_TOKEN = re.compile(r"[a-z]+|\d+[a-z]*")
_CODE = re.compile(r"^\s*([a-z]{2,4})\s*-?\s*(\d{1,3}[a-z]{0,2})\s*$")


@dataclasses.dataclass(frozen=True)
class Match:
  """A parsed search.

  Attributes:
    fts: FTS5 MATCH expression; every word must match one of its spellings.
    code_prefix: `LIKE` pattern such as "CSCI-104%" when the text looks like
      a course code, so exact codes can rank first; otherwise None.
  """

  fts: str
  code_prefix: str | None


def _alternatives(token: str) -> tuple[str, ...]:
  return (token, *_ALIASES.get(token, ()))


def parse(text: str) -> Match | None:
  """Builds a match for `text`, or None when it has no searchable words.

  Words are prefix-matched and ANDed; each word ORs its known expansions,
  so "intro ai" finds "Introduction to Artificial Intelligence". Only
  `[a-z0-9]` survives tokenization, which keeps FTS5 syntax out of user
  input.
  """
  lowered = text.lower()
  tokens = _TOKEN.findall(lowered)
  if not tokens:
    return None
  groups = (
    "(" + " OR ".join(f'"{alt}"*' for alt in _alternatives(t)) + ")"
    for t in tokens
  )
  code = _CODE.match(lowered)
  code_prefix = (
    f"{code.group(1).upper()}-{code.group(2).upper()}%" if code else None
  )
  return Match(fts=" AND ".join(groups), code_prefix=code_prefix)
