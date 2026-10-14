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
from fastapi.middleware import gzip
from starlette.responses import Response
from starlette.types import Scope

from server import config
from server.agent import _llm
from server.db import store
from server.routes import catalog, chat


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None]:
  """Opens the catalog and the advisor model, and reports what they offer."""
  logging.set_verbosity(logging.INFO)
  app.state.catalog = store.CatalogDb()
  try:
    conn = app.state.catalog.connect()
  except FileNotFoundError as e:
    logging.warning("%s", e)
  else:
    with contextlib.closing(conn):
      fetched = [t for t in store.terms(conn) if t.has_courses]
      logging.info(
        "Catalog has %s.",
        ", ".join(f"{t.season} {t.year}" for t in fetched) or "no terms",
      )

  app.state.model = _llm.from_env()
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
# A search page is ~200KB of JSON and compresses about tenfold. Starlette
# leaves text/event-stream alone, so the advisor still streams token by token.
app.add_middleware(gzip.GZipMiddleware, minimum_size=1024)

app.include_router(catalog.router)
app.include_router(chat.router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
  """Answers ok while the server runs; uptime monitors ping this."""
  return {"status": "ok"}


# In production the built client is served from here, so the page and the
# API share one origin. During development Vite serves it and proxies /api.
_CLIENT = config.CLIENT_DIST_DIR


class _Client(staticfiles.StaticFiles):
  """The built client: hashed assets cache for good, the page never does.

  Vite names each file in assets/ by its content, so a cached copy is never
  stale; the page that names them must be rechecked to pick up a rebuild.
  """

  def file_response(
    self,
    full_path: str | os.PathLike[str],
    stat_result: os.stat_result,
    scope: Scope,
    status_code: int = 200,
  ) -> Response:
    response = super().file_response(full_path, stat_result, scope, status_code)
    response.headers["Cache-Control"] = (
      "public, max-age=31536000, immutable"
      if Path(full_path).parent.name == "assets"
      else "no-cache"
    )
    return response


if _CLIENT.is_dir():
  app.mount("/", _Client(directory=_CLIENT, html=True))


if __name__ == "__main__":
  # Development server (`npm run dev`). A short graceful shutdown keeps
  # Ctrl+C from waiting on connections the browser holds open.
  uvicorn.run(
    "server.main:app",
    host="127.0.0.1",
    port=config.PORT,
    reload=True,
    reload_dirs=["server"],
    timeout_graceful_shutdown=1,
  )
