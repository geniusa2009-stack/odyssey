"""Realtime event bus.

Publishers (the service layer, *after* a transaction commits) publish typed messages to a
per-session channel; WebSocket connections subscribe. Two implementations share one interface:

* :class:`InMemoryEventBus` — single process, zero infrastructure (default).
* :class:`RedisEventBus` — Redis pub/sub fan-out across API processes (multiplayer-ready).

Delivery is best-effort: the database is the source of truth. State-transition events are
also retained in ``mission_realtime_events`` (written in the same transaction), so a client
that missed messages resumes from its last event id or re-fetches the snapshot
(``GET /mission-sessions/{id}/snapshot``). Envelopes carry ``state_version`` and
``prev_state_version`` so clients detect gaps.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.realtime.contract import RealtimeEvent

log = logging.getLogger(__name__)

# Messages on the bus are the frozen realtime envelopes (app/realtime/contract.py).
RealtimeMessage = RealtimeEvent


def session_channel(session_id: str) -> str:
    return f"odyssey:session:{session_id}"


class EventBus(Protocol):
    async def publish(self, channel: str, message: RealtimeMessage) -> None: ...

    def subscribe(
        self, channel: str
    ) -> contextlib.AbstractAsyncContextManager[AsyncIterator[RealtimeMessage]]: ...

    async def close(self) -> None: ...


class InMemoryEventBus:
    def __init__(self, queue_size: int = 256) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[RealtimeMessage]]] = {}
        self._queue_size = queue_size

    async def publish(self, channel: str, message: RealtimeMessage) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            if queue.full():  # slow consumer: drop oldest, keep newest state
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(message)

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[RealtimeMessage]]:
        queue: asyncio.Queue[RealtimeMessage] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(channel, set()).add(queue)

        async def iterator() -> AsyncIterator[RealtimeMessage]:
            while True:
                yield await queue.get()

        try:
            yield iterator()
        finally:
            subs = self._subscribers.get(channel)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(channel, None)

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, ()))

    async def close(self) -> None:
        self._subscribers.clear()


class RedisEventBus:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def publish(self, channel: str, message: RealtimeMessage) -> None:
        await self._client.publish(channel, message.model_dump_json())

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[RealtimeMessage]]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)

        async def iterator() -> AsyncIterator[RealtimeMessage]:
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    data = raw["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield RealtimeEvent.model_validate(json.loads(data))
                except (ValueError, KeyError):
                    log.warning("realtime_bad_message", extra={"error_code": "bad_message"})

        try:
            yield iterator()
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self) -> None:
        await self._client.aclose()
