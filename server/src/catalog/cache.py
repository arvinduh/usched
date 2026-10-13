"""On-disk cache of raw source responses, the input to every build.

Fetchers write exactly what a source returned, keyed by a path such as
`classes/20271/programs/ENGV-CSCI.json`; parsers and the builder read it
back. Keeping raw payloads makes builds reproducible and offline, and lets a
fetch skip anything fetched recently. Writes are atomic so an interrupted
fetch never leaves a half-written file behind.
"""

import json
import os
import pathlib
import time
from typing import Any

from server import config


DEFAULT_ROOT = config.RAW_CACHE_DIR


class RawCache:
  """A directory of raw responses addressed by relative keys.

  Attributes:
    root: Directory holding the cache.
  """

  def __init__(self, root: pathlib.Path = DEFAULT_ROOT) -> None:
    self.root = root

  def path(self, key: str) -> pathlib.Path:
    """Returns the file for `key`, e.g. "classes/terms.json"."""
    return self.root / key

  def is_fresh(self, key: str, max_age_s: float) -> bool:
    """Reports whether `key` exists and was written within `max_age_s`."""
    target = self.path(key)
    return target.is_file() and time.time() - target.stat().st_mtime < max_age_s

  def write_text(self, key: str, text: str) -> None:
    """Atomically writes `text` to `key`, creating parent directories."""
    target = self.path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, target)

  def write_json(self, key: str, data: Any) -> None:
    """Atomically writes `data` as JSON to `key`."""
    self.write_text(key, json.dumps(data, ensure_ascii=False))

  def read_text(self, key: str) -> str:
    """Reads `key` as text.

    Raises:
      FileNotFoundError: `key` was never fetched.
    """
    return self.path(key).read_text(encoding="utf-8")

  def read_json(self, key: str) -> Any:
    """Reads `key` as JSON.

    Raises:
      FileNotFoundError: `key` was never fetched.
    """
    return json.loads(self.read_text(key))

  def keys(self, prefix: str, pattern: str) -> list[str]:
    """Lists keys under `prefix` matching a glob `pattern`, sorted."""
    base = self.path(prefix)
    if not base.is_dir():
      return []
    return sorted(
      p.relative_to(self.root).as_posix() for p in base.glob(pattern)
    )
