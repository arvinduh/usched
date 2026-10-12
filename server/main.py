"""FastAPI server entrypoint for usched backend services.

This module initializes the FastAPI application, mounts CORS middleware,
reports what the catalog and local model offer on startup, and exposes
API routes.
"""

import contextlib
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import fastapi
import uvicorn
from absl import logging
from fastapi.middleware import cors

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
  """Opens the catalog and reports what it and the local model offer."""
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

  from server.src.agent import ollama

  if ollama.is_ollama_available():
    logging.info("Connected to local Ollama daemon.")
    if ollama.is_model_downloaded():
      logging.info("Model '%s' is loaded and ready.", ollama.MODEL_NAME)
    else:
      logging.warning(
        "Model '%s' is not downloaded yet. Run: ollama pull %s",
        ollama.MODEL_NAME,
        ollama.MODEL_NAME,
      )
  else:
    logging.info(
      "Ollama daemon is offline. Start Ollama (`ollama run %s`) to enable "
      "local AI advising.",
      ollama.MODEL_NAME,
    )
  yield


app = fastapi.FastAPI(
  title="usched API",
  description="High-performance USC schedule optimizer and degree advisor",
  version="0.1.0",
  lifespan=lifespan,
)

app.add_middleware(
  cors.CORSMiddleware,
  allow_origins=[
    "http://localhost:18801",
    "http://127.0.0.1:18801",
    "http://localhost:5173",
    "*",
  ],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(chat.router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
  """Returns API operational readiness status and port configuration."""
  return {"status": "ok", "service": "usched", "port": "18800"}


if __name__ == "__main__":
  uvicorn.run(
    "server.main:app",
    host="127.0.0.1",
    port=18800,
    reload=True,
    timeout_graceful_shutdown=1,
    timeout_keep_alive=3,
  )
