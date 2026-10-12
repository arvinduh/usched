"""FastAPI server entrypoint for usched backend services.

This module initializes the FastAPI application, mounts CORS middleware,
ensures database schema integrity on startup, and exposes API routes.
"""

import contextlib
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import fastapi
import uvicorn
from absl import logging
from fastapi.middleware import cors

from server.src.data import catalog_db, database
from server.src.routes import catalog, chat, courses, degree, ge, schedule


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
  """Ensures database initialization and reports catalogue status on startup."""
  logging.set_verbosity(logging.INFO)
  db = database.Database()
  db.init()
  app.state.db = db
  app.state.catalog = catalog_db.CatalogDb()
  if not app.state.catalog.path.is_file():
    logging.warning("No catalog database yet; build it with `npm run catalog`.")
  conn = db.connect()
  try:
    cursor = conn.execute("SELECT COUNT(*) FROM courses")
    count = int(cursor.fetchone()[0])
    logging.info("Connected to database with %d courses available.", count)
  finally:
    conn.close()

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
app.include_router(courses.router)
app.include_router(schedule.router)
app.include_router(degree.router)
app.include_router(ge.router)
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
