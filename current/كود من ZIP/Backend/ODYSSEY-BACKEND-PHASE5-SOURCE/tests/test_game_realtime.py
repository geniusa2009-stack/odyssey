"""odyssey.game.v1 realtime: WebSocket handshake, ordering, resume, resync, gap back-fill,
token checks and Redis fan-out."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.game.application.runtime import GameRuntime
from app.game.contracts.protocol import GameEventEnvelope
from app.game.realtime.bus import InMemoryGameBus
from tests.conftest import make_settings
from tests.game_api import GAME, E, GamePlayer, game_client, game_runtime


class DroppingBus(InMemoryGameBus):
    """Loses every message whose seq is in ``drop`` (a flaky network / slow consumer)."""

    def __init__(self, drop: set[int]) -> None:
        super().__init__()
        self.drop = drop

    async def publish(self, channel: str, message: GameEventEnvelope) -> None:
        if message.seq in self.drop:
            return
        await super().publish(channel, message)


@pytest.fixture
def api(sqlite_url: str) -> Iterator[tuple[TestClient, GameRuntime]]:
    with game_client(make_settings(sqlite_url)) as pair:
        yield pair


def _ws(g: GamePlayer, **params: Any) -> Any:
    query = "&".join(f"{k}={v}" for k, v in {"token": g.token, **params}.items())
    return g.client.websocket_connect(f"{GAME}/ws/sessions/{g.session_id}?{query}")


def _recv(ws: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ws.receive_text())
    return data


def _drain_events(ws: Any, upto_seq: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while not out or out[-1].get("seq", 0) < upto_seq:
        msg = _recv(ws)
        out.append(msg)
    return out


def test_connected_then_live_events_in_order(api: tuple[TestClient, GameRuntime]) -> None:
    g = GamePlayer(*api)
    g.create()
    with _ws(g) as ws:
        hello = _recv(ws)
        assert hello["type"] == "CONNECTED"
        assert hello["protocol"] == "odyssey.game.v1"
        assert hello["last_seq"] == g.last_seq
        out = g.act("world.zone_entered", E + "engineering")
        got = _drain_events(ws, out["last_seq"])
    assert [e["seq"] for e in got] == [e["seq"] for e in out["events"]]
    for e in got:
        GameEventEnvelope.model_validate(e)  # every frame matches the frozen envelope
        assert e["session_id"] == g.session_id
        assert e["state_version"] == out["state_version"]
        assert e["prev_state_version"] == out["state_version"] - 1


def test_resume_replays_exactly_the_missed_events(api: tuple[TestClient, GameRuntime]) -> None:
    g = GamePlayer(*api)
    g.create()
    g.act("world.zone_entered", E + "engineering")
    seen = g.last_seq
    g.act("world.zone_entered", E + "laboratory")
    g.act("world.zone_entered", E + "training")
    with _ws(g, last_seq=seen) as ws:
        hello = _recv(ws)
        assert hello["type"] == "RESUMED"
        replayed = [_recv(ws) for _ in range(hello["replayed"])]
    assert [e["seq"] for e in replayed] == list(range(seen + 1, g.last_seq + 1))


def test_resume_from_the_future_or_expired_requires_resync(sqlite_url: str) -> None:
    rt = game_runtime()
    rt.event_retention = 3
    with game_client(make_settings(sqlite_url), rt) as pair:
        g = GamePlayer(*pair)
        g.create()
        for loc in ("engineering", "laboratory", "training", "hangar", "medical"):
            g.act("world.zone_entered", E + loc)
        with _ws(g, last_seq=0) as ws:
            frame = _recv(ws)
            assert frame["type"] == "RESYNC_REQUIRED"
            assert frame["restore_path"].endswith("/restore")
        with _ws(g, last_seq=g.last_seq + 50) as ws:
            assert _recv(ws)["type"] == "RESYNC_REQUIRED"
        page = g.get("/events", after_seq=0)
        assert page["resync_required"] is True and page["events"] == []
        restored = g.post("/restore", {"last_seq": 0})
        assert restored["resync_required"] is True
        assert restored["snapshot"]["session"]["last_seq"] == g.last_seq


def test_lost_bus_messages_are_back_filled(sqlite_url: str) -> None:
    """A message lost by the bus never shows up as a gap: the socket back-fills from the
    database and the client sees every seq exactly once, in order."""
    bus = DroppingBus(drop=set())
    with game_client(make_settings(sqlite_url), game_runtime(bus=bus)) as pair:
        g = GamePlayer(*pair)
        g.create()
        with _ws(g) as ws:
            assert _recv(ws)["type"] == "CONNECTED"
            first = g.last_seq + 1
            bus.drop = {first, first + 1}
            g.act("world.zone_entered", E + "engineering")
            g.act("world.zone_entered", E + "laboratory")
            got = _drain_events(ws, g.last_seq)
    seqs = [e["seq"] for e in got]
    assert seqs == list(range(first, g.last_seq + 1))


def test_bad_token_or_id_is_refused(api: tuple[TestClient, GameRuntime]) -> None:
    g = GamePlayer(*api)
    g.create()
    client = g.client
    for url in (
        f"{GAME}/ws/sessions/{g.session_id}",
        f"{GAME}/ws/sessions/{g.session_id}?token=gst_wrong",
        f"{GAME}/ws/sessions/not-an-id?token={g.token}",
        f"{GAME}/ws/sessions/{g.session_id}?token={g.token}&last_seq=-1",
    ):
        with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(url) as ws:
            ws.receive_text()
        assert exc.value.code == 1008


def test_ping_pong_and_garbage_is_ignored(api: tuple[TestClient, GameRuntime]) -> None:
    g = GamePlayer(*api)
    g.create()
    with _ws(g) as ws:
        _recv(ws)
        ws.send_text("not json")
        ws.send_text(json.dumps({"type": "command", "action": "mission.authorize"}))
        ws.send_text(json.dumps({"type": "ping"}))
        assert _recv(ws)["type"] == "PONG"
    assert g.snapshot()["state_version"] == 1  # nothing a socket sends can mutate state


def test_informational_events_do_not_change_the_state_version(
    api: tuple[TestClient, GameRuntime],
) -> None:
    g = GamePlayer(*api)
    g.create()
    g.act("world.zone_entered", E + "engineering")
    version = g.snapshot()["state_version"]
    g.post(
        "/future-lens",
        {
            "candidates": [
                {
                    "id": "heat-eco",
                    "action": "system.set_mode",
                    "target": E + "engineering.thermal_plant",
                    "params": {"mode": "eco"},
                }
            ],
            "horizon_ticks": 4,
        },
    )
    page = g.get("/events", after_seq=0, limit=500)
    ready = [e for e in page["events"] if e["type"] == "future_lens.ready"]
    assert len(ready) == 1
    assert ready[0]["state_version"] == ready[0]["prev_state_version"]
    snap = g.snapshot()
    assert [e["seq"] for e in page["events"]] == list(range(1, snap["session"]["last_seq"] + 1))
    assert snap["state_version"] >= version


@pytest.mark.redis
def test_redis_fan_out_end_to_end(sqlite_url: str, redis_url: str) -> None:
    """With Redis configured the production runtime fans events out through Redis pub/sub."""
    settings = make_settings(sqlite_url, redis_url=redis_url)
    with game_client(settings, inject=False) as (client, rt):
        assert type(rt.bus).__name__ == "RedisGameBus"
        g = GamePlayer(client, rt)
        g.create()
        with _ws(g) as ws:
            assert _recv(ws)["type"] == "CONNECTED"
            out = g.act("world.zone_entered", E + "engineering")
            got = _drain_events(ws, out["last_seq"])
        assert [e["seq"] for e in got] == [e["seq"] for e in out["events"]]


@pytest.mark.redis
async def test_redis_game_bus_round_trip(redis_url: str) -> None:
    import asyncio

    import redis.asyncio as aioredis

    from app.game.realtime.bus import RedisGameBus

    client = aioredis.from_url(redis_url)
    bus = RedisGameBus(client)
    env = GameEventEnvelope(
        event_id="gs_x:1",
        seq=1,
        session_id="gs_x",
        timeline_id="gt_x",
        state_version=2,
        prev_state_version=1,
        type="clock.updated",
        scope="mission",
        sim_tick=0,
        sim_time_hours=0.0,
        server_time="2026-10-27T00:00:00+00:00",
        payload={"mode": "PAUSED"},
    )
    try:
        async with bus.subscribe("odyssey:game:test") as sub:
            await asyncio.sleep(0.1)
            await bus.publish("odyssey:game:test", env)
            got = await asyncio.wait_for(_first(sub), 3)
        assert got == env
    finally:
        await client.aclose()


async def _first(it: AsyncIterator[GameEventEnvelope]) -> GameEventEnvelope:
    async for x in it:
        return x
    raise AssertionError("no message")


def test_query_string_tokens_are_redacted_from_server_logs() -> None:
    """The WebSocket accepts ``?token=``; the server's own access lines must not leak it."""
    import logging

    from app.core.logging import QuerySecretFilter, configure_logging

    configure_logging("INFO", json_output=False)
    logger = logging.getLogger("uvicorn.error")
    assert any(isinstance(f, QuerySecretFilter) for f in logger.filters)
    record = logger.makeRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:5000", f"{GAME}/ws/sessions/gs_x?token=gst_SECRET-value&last_seq=3"),
        None,
    )
    for f in logger.filters:
        if isinstance(f, QuerySecretFilter):
            f.filter(record)
    message = record.getMessage()
    assert "gst_SECRET" not in message
    assert "token=[REDACTED]&last_seq=3" in message
