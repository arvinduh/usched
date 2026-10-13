"""FastAPI server entrypoint for usched backend services.

This module initializes the FastAPI application, reports what the catalog
and the advisor model offer on startup, exposes the API routes, and serves
the built client when one exists.
"""

import contextlib
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import fastapi
import uvicorn
from absl import logging
from fastapi import staticfiles

from server.src.agent import llm
from server.src.data import catalog_db
from server.src.routes import catalog, chat


def _load_env_file() -> None:
  """Loads key-value pairs from root .env file into environment variables."""
  env_path = Path(".env")
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


_load_env_file()


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None]:
  """Opens the catalog and the advisor model, and reports what they offer."""
  logging.set_verbosity(logging.INFO)
  app.state.catalog = catalog_db.CatalogDb()
  try:
    conn = app.state.catalog.connect()
  except FileNotFoundError as e:
    logging.warning("%s", e)
  else:
    with contextlib.closing(conn):
      fetched = [t for t in catalog_db.terms(conn) if t.has_courses]
      logging.info(
        "Catalog has %s.",
        ", ".join(f"{t.season} {t.year}" for t in fetched) or "no terms",
      )

  app.state.model = llm.from_env()
  reason = app.state.model.unavailable()
  if reason:
    logging.warning("Advisor model %s: %s", app.state.model.name, reason)
  else:
    logging.info("Advisor model %s is ready.", app.state.model.name)
  yield


app = fastapi.FastAPI(
  title="usched API",
  description="High-performance USC schedule optimizer and degree advisor",
  version="0.1.0",
  lifespan=lifespan,
)

app.include_router(catalog.router)
app.include_router(chat.router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
  """Answers ok while the server runs; uptime monitors ping this."""
  return {"status": "ok"}


# In production the built client is served from here, so the page and the
# API share one origin. During development Vite serves it and proxies /api.
_CLIENT = Path(__file__).resolve().parents[1] / "client" / "dist"
if _CLIENT.is_dir():
  app.mount("/", staticfiles.StaticFiles(directory=_CLIENT, html=True))


if __name__ == "__main__":
  # Development server (`npm run dev`). A short graceful shutdown keeps
  # Ctrl+C from waiting on connections the browser holds open.
  uvicorn.run(
    "server.main:app",
    host="127.0.0.1",
    port=int(os.getenv("PORT", "18800")),
    reload=True,
    reload_dirs=["server"],
    timeout_graceful_shutdown=1,
  )
