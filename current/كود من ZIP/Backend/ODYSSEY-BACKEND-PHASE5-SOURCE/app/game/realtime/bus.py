"""Game realtime fan-out (``odyssey.game.v1``), same design as the v1 bus.

Events are written to ``game_events`` in the same transaction as the state change and published
after commit (best effort); the database is the source of truth and clients resume by ``seq``.
``RedisGameBus`` fans out across API processes; ``InMemoryGameBus`` needs no infrastructure.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.game.contracts.protocol import GameEventEnvelope

log = logging.getLogger(__name__)


def game_channel(session_id: str) -> str:
    return f"odyssey:game:{session_id}"


class GameBus(Protocol):
    async def publish(self, channel: str, message: GameEventEnvelope) -> None: ...

    def subscribe(
        self, channel: str
    ) -> contextlib.AbstractAsyncContextManager[AsyncIterator[GameEventEnvelope]]: ...

    async def close(self) -> None: ...


class InMemoryGameBus:
    def __init__(self, queue_size: int = 512) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[GameEventEnvelope]]] = {}
        self._queue_size = queue_size

    async def publish(self, channel: str, message: GameEventEnvelope) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            if queue.full():  # slow consumer: it will see a seq gap and resume
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(message)

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[GameEventEnvelope]]:
        queue: asyncio.Queue[GameEventEnvelope] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(channel, set()).add(queue)

        async def iterator() -> AsyncIterator[GameEventEnvelope]:
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


class RedisGameBus:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def publish(self, channel: str, message: GameEventEnvelope) -> None:
        await self._client.publish(channel, message.model_dump_json())

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[AsyncIterator[GameEventEnvelope]]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)

        async def iterator() -> AsyncIterator[GameEventEnvelope]:
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    data = raw["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield GameEventEnvelope.model_validate(json.loads(data))
                except (ValueError, KeyError):
                    log.warning("game_realtime_bad_message", extra={"error_code": "bad_message"})

        try:
            yield iterator()
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self) -> None:
        """The Redis client is owned (and closed) by the v1 container."""
