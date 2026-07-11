"""
S16 — Real-time: Server-Sent Events (SSE) para notificaciones en tiempo real.
B-20 — Redis Pub/Sub broker para multi-worker support.

Uso en frontend:
    const es = new EventSource('/api/events', {withCredentials: true});
    es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    es.addEventListener('workout_assigned', handler);
    es.addEventListener('garmin_sync_done', handler);
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..sse_broker import broker

logger = logging.getLogger("labx.events")
router = APIRouter(prefix="/events", tags=["notifications"])


# ── Legacy compatibility alias — coach_main.py /api/metrics reads this ───────
# Returns a dict-like view of active connections per user_id.
class _SubscribersView:
    def values(self):
        if hasattr(broker, "_local"):
            return broker._local._queues.values()
        if hasattr(broker, "_queues"):
            return broker._queues.values()
        return {}.values()

_subscribers = _SubscribersView()


async def publish_event(user_id: str, event_type: str, data: dict) -> None:
    """
    Publish an SSE event to all active connections for user_id.

    Works across multiple uvicorn workers when Redis is available (B-20).
    Falls back to in-memory fan-out in single-worker or dev mode.
    """
    await broker.publish(user_id, event_type, data)


@router.get("")
async def event_stream(
    request: Request,
    me: User    = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    S16: Stream SSE de eventos para el usuario autenticado.
    El cliente debe conectarse con EventSource y credenciales.
    Eventos: connected | workout_assigned | garmin_sync_done | wellness_reminder | message_received
    """
    conn_id = uuid.uuid4().hex[:8]
    logger.info("SSE conectado user_id=%s conn=%s", me.id, conn_id)

    async def _generate():
        async for chunk in broker.subscribe(me.id):
            if await request.is_disconnected():
                break
            yield chunk
        logger.info("SSE desconectado user_id=%s conn=%s", me.id, conn_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
