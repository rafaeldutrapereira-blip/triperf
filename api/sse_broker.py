"""
api/sse_broker.py — SSE event broker with Redis Pub/Sub or in-memory fallback.

B-20: With multiple uvicorn workers, in-memory asyncio.Queue cannot reach clients
connected to a different worker. Redis Pub/Sub bridges all workers via a shared
channel, allowing any worker to fan-out to every connected client of a user.

Architecture:
    Publisher (any worker)
        └─ broker.publish(user_id, event_type, data)
               ├─ RedisBroker: PUBLISH labx:sse:<user_id> payload
               └─ InMemoryBroker: put_nowait into local queues

    Subscriber (SSE generator in events_routes.py)
        └─ broker.subscribe(user_id) → AsyncIterator[str]
               ├─ RedisBroker: asyncio thread reading redis.pubsub()
               └─ InMemoryBroker: asyncio.Queue.get with heartbeat

Usage:
    from .sse_broker import broker
    await broker.publish(user_id, "workout_assigned", {"name": "FTP Test"})
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import AsyncIterator

logger = logging.getLogger("labx.sse_broker")

_HEARTBEAT_INTERVAL = 25.0   # seconds between SSE heartbeat comments
_CHANNEL_PREFIX     = "labx:sse:"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


# ─────────────────────────────────────────────────────────────────
# Abstract interface
# ─────────────────────────────────────────────────────────────────

class SSEBroker(ABC):
    @abstractmethod
    async def publish(self, user_id: str, event_type: str, data: dict) -> None:
        """Send an event to all SSE connections for user_id."""

    @abstractmethod
    async def subscribe(self, user_id: str) -> AsyncIterator[str]:
        """Yield SSE-formatted strings for user_id until cancelled."""

    @abstractmethod
    def connection_count(self) -> int:
        """Total active SSE connections across all users (local only)."""


# ─────────────────────────────────────────────────────────────────
# In-memory broker (single process / dev)
# ─────────────────────────────────────────────────────────────────

class InMemoryBroker(SSEBroker):
    """Fan-out via asyncio.Queue. Works within a single process only."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    async def publish(self, user_id: str, event_type: str, data: dict) -> None:
        queues = self._queues.get(user_id, [])
        if not queues:
            return
        payload = json.dumps({"type": event_type, "data": data, "ts": _now_iso()})
        dead: list[asyncio.Queue] = []
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            try:
                queues.remove(q)
            except ValueError:
                pass

    async def subscribe(self, user_id: str) -> AsyncIterator[str]:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._queues.setdefault(user_id, []).append(q)
        try:
            yield f"data: {json.dumps({'type': 'connected', 'ts': _now_iso()})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_INTERVAL)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                self._queues.get(user_id, []).remove(q)
            except ValueError:
                pass

    def connection_count(self) -> int:
        return sum(len(v) for v in self._queues.values())

    # Legacy compatibility — events_routes.py reads _subscribers directly
    @property
    def _subscribers(self) -> dict:
        return self._queues


# ─────────────────────────────────────────────────────────────────
# Redis Pub/Sub broker (multi-worker prod)
# ─────────────────────────────────────────────────────────────────

class RedisBroker(SSEBroker):
    """
    Fan-out via Redis Pub/Sub.

    Each worker subscribes to a per-user channel and bridges to local asyncio.Queue.
    Events published from any worker reach all subscribers in all workers.
    """

    def __init__(self, redis_url: str) -> None:
        self._url    = redis_url
        self._client = self._make_client(redis_url)
        self._local: InMemoryBroker = InMemoryBroker()  # local queues in this worker
        self._listener_tasks: dict[str, asyncio.Task] = {}

    @staticmethod
    def _make_client(url: str):
        import redis  # type: ignore
        return redis.from_url(url, decode_responses=True, socket_timeout=5)

    def _channel(self, user_id: str) -> str:
        return f"{_CHANNEL_PREFIX}{user_id}"

    async def publish(self, user_id: str, event_type: str, data: dict) -> None:
        payload = json.dumps({"type": event_type, "data": data, "ts": _now_iso()})
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._client.publish, self._channel(user_id), payload
            )
        except Exception as e:
            logger.warning("RedisBroker.publish failed (%s) — falling back to local", e)
            await self._local.publish(user_id, event_type, data)

    async def subscribe(self, user_id: str) -> AsyncIterator[str]:
        # Ensure a Redis listener is running for this user in this worker
        if user_id not in self._listener_tasks or self._listener_tasks[user_id].done():
            task = asyncio.create_task(self._listen(user_id))
            self._listener_tasks[user_id] = task

        # Subscribe via local in-memory queue (filled by Redis listener)
        async for chunk in self._local.subscribe(user_id):
            yield chunk

    async def _listen(self, user_id: str) -> None:
        """Background task: Redis SUBSCRIBE → local InMemoryBroker."""
        channel = self._channel(user_id)
        try:
            pubsub = await asyncio.get_event_loop().run_in_executor(
                None, self._make_pubsub, channel
            )
            while True:
                msg = await asyncio.get_event_loop().run_in_executor(
                    None, pubsub.get_message, True, 1.0
                )
                if msg and msg["type"] == "message":
                    try:
                        evt = json.loads(msg["data"])
                        await self._local.publish(user_id, evt.get("type", "event"),
                                                  evt.get("data", {}))
                    except Exception:
                        pass
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("RedisBroker._listen(%s) error: %s", user_id, e)

    def _make_pubsub(self, channel: str):
        import redis  # type: ignore
        r = redis.from_url(self._url, decode_responses=True, socket_timeout=30)
        ps = r.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(channel)
        return ps

    def connection_count(self) -> int:
        return self._local.connection_count()


# ─────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────

def create_broker() -> SSEBroker:
    """Return the appropriate broker based on REDIS_URL availability."""
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            import redis as _redis  # type: ignore
            # Quick connectivity check
            r = _redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()
            logger.info("SSE broker: Redis Pub/Sub at %s", redis_url.split("@")[-1])
            return RedisBroker(redis_url)
        except Exception as e:
            logger.warning("Redis not reachable (%s) — using in-memory SSE broker", e)
    logger.info("SSE broker: in-memory (single-worker)")
    return InMemoryBroker()


# Module-level singleton
broker: SSEBroker = create_broker()


def publish_nowait(user_id: str, event_type: str, data: dict) -> None:
    """
    Fire-and-forget SSE publish from synchronous code (e.g. sync FastAPI route handlers).

    Schedules the publish coroutine on the running event loop if one exists,
    otherwise spawns a daemon thread with its own event loop. Never raises.
    """
    import threading

    async def _pub():
        await broker.publish(user_id, event_type, data)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_pub())
    except RuntimeError:
        # No running loop (called from a thread pool worker)
        def _run():
            asyncio.run(_pub())
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        logger.debug("publish_nowait failed: %s", e)
