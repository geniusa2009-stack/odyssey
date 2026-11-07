"""Realtime bus, HTTP hardening (rate limit, body limit, headers), structured logging."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest

from app.api.security import InMemoryRateLimiter
from app.api.v1.ws import is_ping
from app.core.config import Settings
from app.core.logging import JsonFormatter, redact, request_id_var, session_id_var
from app.realtime.bus import InMemoryEventBus, RealtimeMessage, RedisEventBus, session_channel
from app.telemetry.stats import RuntimeStats


def _msg(tick: int, kind: Any = "MISSION_STATE_CHANGED") -> RealtimeMessage:
    # Phase 4: messages use the frozen realtime envelope (odyssey.realtime.v1)
    return RealtimeMessage(
        event_id=f"t1:{tick}:0",
        type=kind,
        session_id="s1",
        timeline_id="t1",
        state_version=tick,
        prev_state_version=None,
        seq=0,
        seq_count=1,
        sim_tick=tick,
        sim_time_hours=float(tick),
        server_time="2026-10-19T06:00:00+00:00",
    )


class TestInMemoryBus:
    async def test_publish_subscribe_and_cleanup(self) -> None:
        bus = InMemoryEventBus()
        channel = session_channel("s1")
        async with bus.subscribe(channel) as a, bus.subscribe(channel) as b:
            assert bus.subscriber_count(channel) == 2
            await bus.publish(channel, _msg(1))
            await bus.publish(session_channel("other"), _msg(99))
            got_a = await asyncio.wait_for(a.__anext__(), 1)
            got_b = await asyncio.wait_for(b.__anext__(), 1)
            assert got_a.sim_tick == got_b.sim_tick == 1
        assert bus.subscriber_count(channel) == 0

    async def test_slow_consumer_keeps_newest(self) -> None:
        bus = InMemoryEventBus(queue_size=3)
        async with bus.subscribe("c") as sub:
            for t in range(10):
                await bus.publish("c", _msg(t))
            ticks = [(await sub.__anext__()).sim_tick for _ in range(3)]
        assert ticks == [7, 8, 9]

    def test_message_schema_rejects_unknown_types(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _msg(1, kind="drop_tables")

    @pytest.mark.redis
    async def test_redis_bus_fan_out(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        publisher = RedisEventBus(aioredis.from_url(redis_url))
        subscriber = RedisEventBus(aioredis.from_url(redis_url))
        try:
            async with subscriber.subscribe("odyssey:test:chan") as sub:
                await asyncio.sleep(0.1)
                await publisher.publish("odyssey:test:chan", _msg(5, "SYSTEM_ALERT"))
                got = await asyncio.wait_for(sub.__anext__(), 3)
            assert got.sim_tick == 5 and got.type == "SYSTEM_ALERT"
        finally:
            await publisher.close()
            await subscriber.close()


class TestRateLimiter:
    def test_token_bucket(self) -> None:
        now = [0.0]
        limiter = InMemoryRateLimiter(clock=lambda: now[0])
        assert all(limiter.hit("ip", 3) for _ in range(3))
        assert not limiter.hit("ip", 3)
        assert limiter.hit("other-ip", 3)
        now[0] += 20.0  # 3/min → one token per 20 s
        assert limiter.hit("ip", 3)
        assert not limiter.hit("ip", 3)

    def test_bounded_memory(self) -> None:
        limiter = InMemoryRateLimiter(max_keys=5)
        for i in range(20):
            limiter.hit(f"k{i}", 10)
        assert len(limiter._buckets) <= 5


class TestWebSocketFrames:
    @pytest.mark.parametrize(
        ("frame", "expected"),
        [
            ('{"type":"ping"}', True),
            ('{"type": "ping"}', True),
            (' {"type" : "ping"} ', True),
            ('{"type":"pong"}', False),
            ("ping", False),
            ("[]", False),
            ('{"type":"ping","x":"' + "a" * 2000 + '"}', False),
        ],
    )
    def test_is_ping(self, frame: str, expected: bool) -> None:
        assert is_ping(frame) is expected


class TestLogging:
    def test_redaction(self) -> None:
        data = {
            "api_key": "x",
            "nested": {"Authorization": "Bearer y", "ok": 1},
            "list": [{"password": "p"}],
        }
        assert redact(data) == {
            "api_key": "[REDACTED]",
            "nested": {"Authorization": "[REDACTED]", "ok": 1},
            "list": [{"password": "[REDACTED]"}],
        }

    def test_json_formatter_includes_context(self) -> None:
        token_r = request_id_var.set("req-12345678")
        token_s = session_id_var.set("sess-1")
        try:
            record = logging.LogRecord(
                "odyssey", logging.INFO, __file__, 1, "simulation_run", None, None
            )
            record.event_type = "advance"
            record.duration_ms = 1.5
            payload = json.loads(JsonFormatter().format(record))
        finally:
            request_id_var.reset(token_r)
            session_id_var.reset(token_s)
        assert payload["request_id"] == "req-12345678"
        assert payload["mission_session_id"] == "sess-1"
        assert payload["event_type"] == "advance" and payload["duration_ms"] == 1.5


class TestSettings:
    def test_secrets_have_no_defaults_and_are_masked(self) -> None:
        s = Settings(_env_file=None)
        assert s.ai_api_key is None and s.nasa_api_key is None
        masked = Settings(_env_file=None, nasa_api_key="abc")
        assert "abc" not in repr(masked)

    def test_cors_origins_from_comma_list(self) -> None:
        s = Settings(_env_file=None, cors_origins="http://a.test, http://b.test")
        assert s.cors_origins == ["http://a.test", "http://b.test"]

    def test_zero_infrastructure_defaults(self) -> None:
        s = Settings(_env_file=None)
        assert s.database_url.startswith("sqlite")
        assert s.redis_url is None and s.ai_provider == "mock"
        assert s.nasa_remote_enabled is False


class TestRuntimeStats:
    def test_aggregation(self) -> None:
        stats = RuntimeStats()
        stats.record("advance", 10.0, ticks=24)
        stats.record("advance", 30.0, ticks=24)
        stats.record("decision", 1.0)
        snap = {s.kind: s for s in stats.snapshot()}
        assert snap["advance"].count == 2 and snap["advance"].mean_ms == 20.0
        assert snap["advance"].max_ms == 30.0 and snap["advance"].ticks_simulated == 48
        with pytest.raises(ValueError, match="duration_ms"):
            stats.record("x", -1)
        stats.reset()
        assert stats.snapshot() == []
