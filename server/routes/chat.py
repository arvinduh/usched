"""Server-Sent Events (SSE) AI advisor streaming chat route.

This module exposes the streaming dialogue endpoint for academic advising,
prerequisite navigation, and schedule optimization. The advisor itself is
blocking (synchronous model and SQLite calls), so this route owns moving it
off the event loop; the advisor module owns what gets said.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator

import fastapi

from server.agent import _llm, advisor
from server.db import store


router = fastapi.APIRouter(prefix="/api/chat", tags=["chat"])


async def _relay(
  payload: advisor.ChatRequest,
  catalog: store.CatalogDb,
  model: _llm.Model,
) -> AsyncIterator[str]:
  """Runs the blocking advisor on a worker thread and relays its chunks.

  Iterating the advisor directly would block the event loop for the whole
  reply, stalling every other request and Ctrl+C handling. When the client
  disconnects, Starlette cancels this generator and the `finally` signals the
  worker to stop at its next chunk.

  Args:
    payload: The chat request to answer.
    catalog: The catalog; the worker opens its own connection.
    model: The advisor's language model.

  Yields:
    SSE-formatted chunks in production order.
  """
  loop = asyncio.get_running_loop()
  chunks: asyncio.Queue[str | None] = asyncio.Queue()
  stop = threading.Event()

  def deliver(chunk: str | None) -> None:
    if not loop.is_closed():
      loop.call_soon_threadsafe(chunks.put_nowait, chunk)

  def produce() -> None:
    try:
      conn = catalog.connect()
    except FileNotFoundError as e:
      deliver(f"data: {json.dumps({'token': str(e)})}\n\ndata: [DONE]\n\n")
      deliver(None)
      return
    try:
      for chunk in advisor.stream(payload, conn, model):
        if stop.is_set():
          return
        deliver(chunk)
    finally:
      conn.close()
      deliver(None)

  # Daemon so a reply still generating never blocks process shutdown.
  threading.Thread(target=produce, name="advisor", daemon=True).start()
  try:
    while (chunk := await chunks.get()) is not None:
      yield chunk
  finally:
    stop.set()


@router.post(
  "",
  response_class=fastapi.responses.StreamingResponse,
  responses={
    200: {
      "model": advisor.ClosingEvent,
      "description": (
        "An event stream of `{token}` (answer text), `{thought}` (reasoning) "
        "and `{step}` (a tool starting) events, then one ClosingEvent, then "
        "`[DONE]`."
      ),
    }
  },
)
async def chat_stream(
  payload: advisor.ChatRequest,
  request: fastapi.Request,
) -> fastapi.responses.StreamingResponse:
  """Streams AI advisor markdown guidance and interactive chips via SSE."""
  return fastapi.responses.StreamingResponse(
    _relay(payload, request.app.state.catalog, request.app.state.model),
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  )


__all__: list[str] = [
  "chat_stream",
  "router",
]
