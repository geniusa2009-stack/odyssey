"""odyssey.game.v1 latency and SQL statement counts (Phase 5, section 47).

``python -m app.tools.game_bench [--database-url URL] [--redis-url URL] [--repeat N]
[--output FILE]``

Drives the mounted game API in-process (``TestClient``; no network, no TLS) through one
Earth Command session and measures, per operation, wall-clock latency (median, p95, max over
``--repeat`` calls) and SQL statements per call (SQLAlchemy ``before_cursor_execute``):

* bootstrap, snapshot, restore (the reconnect path), events page
* a common semantic action (zone entry), an inventory transfer, a mission action that records a
  simulation decision, a clock sync that advances the simulation
* Future Lens (two semantic candidates, known_only) and Black Box (with counterfactuals)
* WebSocket: command → last event received on the socket, and reconnect + resume handshake

Defaults: temporary SQLite file and the in-process bus. Pass a migrated PostgreSQL URL and a
Redis URL to measure the production stack. The server clock is a deterministic fake clock, so
every run plays the same session.
"""

from __future__ import annotations

import argparse
import itertools
import json
import platform
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import event

from app.tools.api_bench import QueryCounter

GAME = "/api/game/v1"
E = "earth.command."


def _stats(times: list[float], queries: list[int]) -> dict[str, Any]:
    times = sorted(times)
    return {
        "calls": len(times),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(times[min(len(times) - 1, int(0.95 * len(times)))], 2),
        "max_ms": round(times[-1], 2),
        "queries_median": int(statistics.median(queries)) if queries else 0,
        "queries_max": max(queries) if queries else 0,
    }


def _measure(fn: Callable[[], Any], counter: QueryCounter, repeat: int) -> dict[str, Any]:
    times: list[float] = []
    queries: list[int] = []
    for _ in range(repeat):
        counter.count = 0
        started = time.perf_counter()
        response = fn()
        times.append((time.perf_counter() - started) * 1000)
        queries.append(counter.count)
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise RuntimeError(f"{status}: {response.text[:300]}")
    return _stats(times, queries)


def run(database_url: str | None, redis_url: str | None, repeat: int) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.game.application.identity import AnonymousIdentityProvider
    from app.game.application.runtime import GameRuntime
    from app.game.content.loader import default_content
    from app.game.realtime.bus import GameBus, InMemoryGameBus, RedisGameBus
    from app.game.runtime.clock import FakeClock
    from app.main import create_app

    results: dict[str, Any] = {}
    clock = FakeClock()
    with tempfile.TemporaryDirectory() as tmp:
        url = database_url or f"sqlite+aiosqlite:///{Path(tmp) / 'game-bench.db'}"
        settings = Settings(
            environment="test",
            database_url=url,
            auto_create_schema=database_url is None,
            log_json=False,
            log_level="WARNING",
            rate_limit_per_minute=1_000_000,
            rate_limit_expensive_per_minute=1_000_000,
            redis_url=redis_url,
        )
        holder: dict[str, GameRuntime] = {}

        def runtime_for(bus: GameBus) -> GameRuntime:
            rt = GameRuntime(default_content(), bus, clock, AnonymousIdentityProvider())
            holder["rt"] = rt
            return rt

        # with Redis, the bus must be created on the app's event loop: let the app build it
        # (production runtime) and then swap in the fake clock
        app = create_app(
            settings, game_runtime=None if redis_url else runtime_for(InMemoryGameBus())
        )
        with TestClient(app) as c:
            mounted = next(r for r in app.routes if getattr(r, "path", "") == GAME)
            rt: GameRuntime = mounted.app.state.game_runtime  # type: ignore[attr-defined]
            rt.clock = clock
            bus_kind = "redis" if isinstance(rt.bus, RedisGameBus) else "in-memory"
            counter = QueryCounter()
            sync_engine = app.state.container.db_engine.sync_engine
            event.listen(sync_engine, "before_cursor_execute", counter)

            def create() -> Any:
                return c.post(f"{GAME}/sessions", json={"display_name": "Bench"})

            results["create_session"] = _measure(create, counter, max(1, repeat // 2))
            created = create().json()
            token = created["session_token"]
            sid = created["bootstrap"]["snapshot"]["session"]["id"]
            headers = {"Authorization": f"Bearer {token}"}
            base = f"{GAME}/sessions/{sid}"
            st = {"v": created["bootstrap"]["snapshot"]["state_version"]}
            n = itertools.count(1)

            def get(path: str, **params: Any) -> Callable[[], Any]:
                return lambda: c.get(f"{base}{path}", params=params, headers=headers)

            def command(action: str, target: str | None, **params: Any) -> Any:
                i = next(n)
                body: dict[str, Any] = {
                    "command_id": f"bench-{i}",
                    "session_id": sid,
                    "expected_state_version": st["v"],
                    "idempotency_key": f"bench-key-{i:08d}",
                    "action": action,
                    "params": params,
                }
                if target:
                    body["target"] = target
                r = c.post(f"{base}/commands", json=body, headers=headers)
                if r.status_code < 300:
                    st["v"] = r.json()["state_version"]
                return r

            def alternating(*calls: Callable[[], Any]) -> Callable[[], Any]:
                cycle = itertools.cycle(calls)
                return lambda: next(cycle)()

            results["bootstrap"] = _measure(get("/bootstrap"), counter, repeat)
            results["snapshot"] = _measure(get("/snapshot"), counter, repeat)
            results["action_zone_entered"] = _measure(
                alternating(
                    lambda: command("world.zone_entered", E + "laboratory"),
                    lambda: command("world.zone_entered", E + "hangar"),
                ),
                counter,
                repeat,
            )
            command("world.zone_entered", E + "hangar")
            results["inventory_transfer"] = _measure(
                alternating(
                    lambda: command(
                        "cargo.transfer",
                        E + "hangar.storage",
                        item="tool.diagnostic_scanner",
                        quantity=1,
                        **{"from": E + "player_kit"},
                    ),
                    lambda: command(
                        "inventory.move",
                        E + "player_kit",
                        item="tool.diagnostic_scanner",
                        quantity=1,
                        **{"from": E + "hangar.storage"},
                    ),
                ),
                counter,
                repeat,
            )
            results["mission_action_sim_decision"] = _measure(
                alternating(
                    lambda: command("system.set_mode", E + "hangar.ground_support", mode="eco"),
                    lambda: command("system.set_mode", E + "hangar.ground_support", mode="nominal"),
                ),
                counter,
                repeat,
            )

            def sync_one_tick() -> Any:
                clock.advance(5)
                r = c.post(f"{base}/sync", json={}, headers=headers)
                st["v"] = r.json()["state_version"]
                return r

            results["clock_sync_1_tick"] = _measure(sync_one_tick, counter, min(repeat, 3))
            lens = {
                "candidates": [
                    {
                        "id": "gs-eco",
                        "action": "system.set_mode",
                        "target": E + "hangar.ground_support",
                        "params": {"mode": "eco"},
                    },
                    {
                        "id": "gs-off",
                        "action": "system.set_mode",
                        "target": E + "hangar.ground_support",
                        "params": {"mode": "off"},
                    },
                ],
                "horizon_ticks": 12,
            }
            results["future_lens"] = _measure(
                lambda: c.post(f"{base}/future-lens", json=lens, headers=headers),
                counter,
                max(1, repeat // 2),
            )
            results["black_box"] = _measure(
                get("/black-box", counterfactuals="true"), counter, max(1, repeat // 2)
            )
            results["events_page"] = _measure(
                get("/events", after_seq=0, limit=200), counter, repeat
            )
            results["restore"] = _measure(
                lambda: c.post(
                    f"{base}/restore",
                    json={
                        "last_seq": max(
                            0,
                            c.get(f"{base}/snapshot", headers=headers).json()["session"]["last_seq"]
                            - 5,
                        )
                    },
                    headers=headers,
                ),
                counter,
                repeat,
            )
            # WebSocket: command → its last event on the socket; reconnect + resume handshake
            ws_url = f"{GAME}/ws/sessions/{sid}?token={token}"
            ws_times: list[float] = []
            with c.websocket_connect(ws_url) as sock:
                json.loads(sock.receive_text())
                for i in range(repeat):
                    target = E + ("hangar" if i % 2 else "laboratory")
                    started = time.perf_counter()
                    out = command("world.zone_entered", target).json()
                    if not out["events"]:
                        raise RuntimeError("benchmark command produced no events")
                    last = out["last_seq"]
                    while True:
                        msg = json.loads(sock.receive_text())
                        if msg.get("seq", 0) >= last:
                            break
                    ws_times.append((time.perf_counter() - started) * 1000)
            results["ws_command_to_event"] = _stats(ws_times, [])
            snap_seq = c.get(f"{base}/snapshot", headers=headers).json()["session"]["last_seq"]
            re_times: list[float] = []
            for _ in range(repeat):
                started = time.perf_counter()
                with c.websocket_connect(f"{ws_url}&last_seq={max(0, snap_seq - 5)}") as sock:
                    hello = json.loads(sock.receive_text())
                    for _ in range(hello.get("replayed") or 0):
                        sock.receive_text()
                re_times.append((time.perf_counter() - started) * 1000)
            results["ws_reconnect_resume"] = _stats(re_times, [])
            event.remove(sync_engine, "before_cursor_execute", counter)
    return {
        "report": "odyssey.game_bench",
        "protocol": "odyssey.game.v1",
        "database": "postgresql" if database_url and "postgres" in database_url else "sqlite",
        "bus": bus_kind,
        "repeat": repeat,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.machine(),
            "transport": "in-process ASGI (fastapi TestClient), no network",
        },
        "operations": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--redis-url")
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = run(args.database_url, args.redis_url, args.repeat)
    print(f"database: {report['database']}, bus: {report['bus']}, repeat: {report['repeat']}")
    print(f"{'operation':28} {'median ms':>10} {'p95 ms':>8} {'max ms':>8} {'queries':>8}")
    for name, r in report["operations"].items():
        print(
            f"{name:28} {r['median_ms']:10.2f} {r['p95_ms']:8.2f} {r['max_ms']:8.2f} "
            f"{r['queries_median']:8d}"
        )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
