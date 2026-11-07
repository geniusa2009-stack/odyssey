"""Cache abstraction for external data (in-memory, local file, Redis)."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

Clock = Callable[[], float]


class CacheBackend(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class InMemoryCache:
    def __init__(self, clock: Clock = time.monotonic) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._clock = clock

    async def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires and self._clock() >= expires:
            self._data.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires = self._clock() + ttl_seconds if ttl_seconds > 0 else 0.0
        self._data[key] = (expires, value)


class FileCache:
    """JSON files under a directory; keys are hashed so they are always safe file names."""

    def __init__(self, directory: Path, clock: Clock = time.time) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock

    def _path(self, key: str) -> Path:
        return self._dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    async def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if payload.get("expires") and self._clock() >= payload["expires"]:
            return None
        return payload.get("value")

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires = self._clock() + ttl_seconds if ttl_seconds > 0 else 0
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps({"expires": expires, "value": value}), encoding="utf-8")
        tmp.replace(self._path(key))


class RedisCache:
    def __init__(self, client: Any, prefix: str = "odyssey:cache:") -> None:
        self._client = client
        self._prefix = prefix

    async def get(self, key: str) -> Any | None:
        raw = await self._client.get(self._prefix + key)
        return None if raw is None else json.loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._client.set(
            self._prefix + key, json.dumps(value), ex=ttl_seconds if ttl_seconds > 0 else None
        )
