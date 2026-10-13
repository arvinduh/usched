"""Tests for how the build settles rows that listings report differently."""

import dataclasses

from server.src.catalog import build


@dataclasses.dataclass(frozen=True)
class Row:
  key: str
  value: int


def _table(better=None) -> build._Table:
  return build._Table(lambda r: r.key, better)


def test_identical_rows_are_plain_duplicates():
  table = _table()
  table.add([Row("a", 1), Row("a", 1)])
  assert (table.duplicates, table.settled, table.conflicts) == (1, 0, 0)


def test_the_home_listing_wins_in_either_order():
  for first_home in (True, False):
    table = _table()
    table.add([Row("a", 1)], home=first_home)
    table.add([Row("a", 2)], home=not first_home)
    expected = 1 if first_home else 2
    assert table.rows() == [Row("a", expected)]
    assert (table.settled, table.conflicts) == (1, 0)


def test_a_better_rule_settles_and_otherwise_first_wins():
  table = _table(lambda row, kept: row.value > kept.value)
  table.add([Row("a", 1), Row("a", 3), Row("a", 2)])
  assert table.rows() == [Row("a", 3)]
  assert table.settled == 2
  plain = _table()
  plain.add([Row("a", 1), Row("a", 2)])
  assert plain.rows() == [Row("a", 1)]
  assert plain.example == (Row("a", 1), Row("a", 2))
