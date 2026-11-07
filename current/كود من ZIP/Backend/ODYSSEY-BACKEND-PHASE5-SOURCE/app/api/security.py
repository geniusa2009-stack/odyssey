"""HTTP hardening: request ids, body size limits, security headers, rate limiting."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.logging import REQUEST_CONTEXT_VARS, request_id_var

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.\-]{8,64}$")
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
]


async def _send_json(send: Send, status: int, body: dict[str, Any]) -> None:
    import json

    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                *SECURITY_HEADERS,
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class RequestContextMiddleware:
    """Assigns/propagates X-Request-ID, resets log context, adds security headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        # every request starts with a clean log context (request, session, timeline, state
        # version, decision, scenario version ...); the request id is then set
        tokens = [(var, var.set(None)) for var in REQUEST_CONTEXT_VARS]
        tokens.append((request_id_var, request_id_var.set(rid)))
        scope.setdefault("state", {})["request_id"] = rid

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                existing = {k.lower() for k, _ in headers}
                headers.extend(h for h in SECURITY_HEADERS if h[0] not in existing)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            for var, token in reversed(tokens):
                var.reset(token)


class BodySizeLimitMiddleware:
    """Rejects bodies larger than ``max_bytes`` (Content-Length or streamed)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = scope.get("state", {}).get("request_id")
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await _send_json(
                send,
                413,
                error_body(
                    "PAYLOAD_TOO_LARGE", f"request body exceeds {self.max_bytes} bytes", rid
                ),
            )
            return
        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLargeError:
            if too_large:
                await _send_json(
                    send,
                    413,
                    error_body(
                        "PAYLOAD_TOO_LARGE", f"request body exceeds {self.max_bytes} bytes", rid
                    ),
                )


class _BodyTooLargeError(Exception):
    pass


class RateLimiter(Protocol):
    def hit(self, key: str, limit_per_minute: int) -> bool: ...


@dataclass
class _Bucket:
    tokens: float
    updated: float


class InMemoryRateLimiter:
    """Token bucket per key. Single-process; a Redis-backed limiter can implement ``hit``."""

    def __init__(self, clock: Any = time.monotonic, max_keys: int = 10_000) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._clock = clock
        self._max_keys = max_keys

    def hit(self, key: str, limit_per_minute: int) -> bool:
        now = self._clock()
        bucket = self._buckets.get(key)
        rate = limit_per_minute / 60.0
        if bucket is None:
            if len(self._buckets) >= self._max_keys:
                self._buckets.clear()
            bucket = self._buckets[key] = _Bucket(tokens=float(limit_per_minute), updated=now)
        bucket.tokens = min(float(limit_per_minute), bucket.tokens + (now - bucket.updated) * rate)
        bucket.updated = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False
