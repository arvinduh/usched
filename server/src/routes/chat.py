"""Server-Sent Events (SSE) AI advisor streaming chat route.

This module exposes the streaming dialogue endpoint for academic advising,
prerequisite navigation, and schedule optimization.
"""

from collections.abc import AsyncIterator

import fastapi

from server.src.agent import advisor
from server.src.data import database


router = fastapi.APIRouter(prefix="/api/chat", tags=["chat"])


def get_db(request: fastapi.Request) -> database.Database:
  """Retrieves database service instance from application state."""
  return request.app.state.db


@router.post("")
async def chat_stream(
  payload: advisor.ChatRequest,
  request: fastapi.Request,
) -> fastapi.responses.StreamingResponse:
  """Streams AI advisor markdown guidance and interactive chips via SSE."""
  db = get_db(request)

  async def event_generator() -> AsyncIterator[str]:
    conn = db.connect()
    try:
      for chunk in advisor.stream_advisor_sse(payload, conn, db):
        if await request.is_disconnected():
          break
        yield chunk
    finally:
      conn.close()

  return fastapi.responses.StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  )
