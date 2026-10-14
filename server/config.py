"""Central configuration and constants for the usched server.

Single Source of Truth (SSOT) registry for environment variables, paths,
URLs, API parameters, and domain policy defaults across the server.
"""

import os
from pathlib import Path


def _load_env_file(root_dir: Path) -> None:
  """Loads key-value pairs from root .env file into environment variables."""
  env_path = root_dir / ".env"
  if not env_path.is_file():
    return
  try:
    with open(env_path, encoding="utf-8") as f:
      for line in f:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
          key, val = trimmed.split("=", 1)
          os.environ.setdefault(key.strip(), val.strip())
  except OSError:
    pass


SERVER_DIR: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = SERVER_DIR.parent
_load_env_file(ROOT_DIR)

PORT: int = int(os.getenv("PORT", "18800"))
CLIENT_PORT: int = int(os.getenv("CLIENT_PORT", "18801"))
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
_models_raw = os.getenv(
  "GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
)
GEMINI_MODELS: tuple[str, ...] = tuple(
  m.strip() for m in _models_raw.split(",") if m.strip()
)

DATA_DIR: Path = SERVER_DIR / "data"
_catalog_db_env = os.getenv("CATALOG_DB_PATH")
DB_PATH: Path = (
  Path(_catalog_db_env) if _catalog_db_env else DATA_DIR / "catalog.db"
)
SEEDS_DIR: Path = SERVER_DIR / "seeds"
CLIENT_DIST_DIR: Path = ROOT_DIR / "client" / "dist"
RAW_CACHE_DIR: Path = DATA_DIR / "raw"

GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TIMEOUT_SECONDS: float = 45.0
GEMINI_CONNECT_TIMEOUT_SECONDS: float = 10.0
GEMINI_MAX_OUTPUT_TOKENS: int = 2048
GEMINI_TEMPERATURE: float = 0.4
GEMINI_RETRY_DELAY_SECONDS: float = 1.5
MAX_TOOL_ROUNDS: int = 2

USC_CLASSES_API_BASE: str = "https://classes.usc.edu/api"
USC_CATALOGUE_BASE: str = "https://catalogue.usc.edu"
RMP_GRAPHQL_ENDPOINT: str = "https://www.ratemyprofessors.com/graphql"

DEFAULT_BACHELOR_MINIMUM_UNITS: float = 128.0
# Most units a term takes at flat tuition; each unit past it costs extra.
# The client's OVERLOAD_UNITS mirrors it.
OVERLOAD_UNIT_THRESHOLD: int = 18
