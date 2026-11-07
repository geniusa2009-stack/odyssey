"""API latency and database query counts for representative client flows (Phase 4).

``python -m app.tools.api_bench [--database-url URL] [--repeat N] [--output FILE]``

Drives the frozen contract in-process (``TestClient``; no network) through one deterministic
LUNA-01 session and measures, per endpoint: wall-clock latency (median, p95, max over
``--repeat`` calls) and the number of SQL statements executed per call (counted with a
SQLAlchemy ``before_cursor_execute`` listener). Writes JSON and prints a table.

The numbers include FastAPI validation, response serialisation and the database round trips;
they exclude network and TLS. Defaults to a temporary SQLite file; pass a PostgreSQL URL to
measure against PostgreSQL (the schema must already be migrated).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import event

API = "/api/v1"
SEED = 20261019


class QueryCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *_: Any, **__: Any) -> None:
        self.count += 1


def _measure(fn: Callable[[], Any], counter: QueryCounter, repeat: int) -> dict[str, Any]:
    times: list[float] = []
    queries: list[int] = []
    status = 0
    for _ in range(repeat):
        counter.count = 0
        started = time.perf_counter()
        response = fn()
        times.append((time.perf_counter() - started) * 1000)
        queries.append(counter.count)
        status = response.status_code
        if status >= 400:
            raise RuntimeError(f"{status}: {response.text[:300]}")
    times.sort()
    return {
        "calls": repeat,
        "status": status,
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(times[min(len(times) - 1, int(0.95 * len(times)))], 2),
        "max_ms": round(times[-1], 2),
        "queries_median": int(statistics.median(queries)),
        "queries_max": max(queries),
    }


def run(database_url: str | None, repeat: int) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        url = database_url or f"sqlite+aiosqlite:///{Path(tmp) / 'bench.db'}"
        settings = Settings(
            environment="test",
            database_url=url,
            auto_create_schema=database_url is None,
            log_json=False,
            log_level="WARNING",
            rate_limit_per_minute=1_000_000,
            rate_limit_expensive_per_minute=1_000_000,
            redis_url=None,
        )
        app = create_app(settings)
        with TestClient(app) as c:
            counter = QueryCounter()
            sync_engine = app.state.container.db_engine.sync_engine
            event.listen(sync_engine, "before_cursor_execute", counter)
            state = {"version": 0}

            def create() -> Any:
                return c.post(f"{API}/mission-sessions", json={"seed": SEED})

            results["create_session"] = _measure(create, counter, repeat)
            sid = create().json()["id"]
            base = f"{API}/mission-sessions/{sid}"

            def get(path: str, **params: Any) -> Callable[[], Any]:
                return lambda: c.get(f"{base}{path}", params=params)

            def refresh() -> None:
                state["version"] = c.get(f"{base}/snapshot").json()["state_version"]

            def advance(ticks: int) -> Callable[[], Any]:
                def call() -> Any:
                    r = c.post(
                        f"{base}/advance-commands",
                        json={"ticks": ticks, "expected_state_version": state["version"]},
                    )
                    if r.status_code < 300:
                        state["version"] = r.json()["state_version"]
                    return r

                return call

            def decide(option_id: str, **params: float) -> Callable[[], Any]:
                def call() -> Any:
                    r = c.post(
                        f"{base}/decision-commands",
                        json={
                            "option_id": option_id,
                            "parameters": params,
                            "expected_state_version": state["version"],
                        },
                    )
                    if r.status_code < 300:
                        state["version"] = r.json()["state_version"]
                    return r

                return call

            refresh()
            results["bootstrap"] = _measure(get("/bootstrap"), counter, repeat)
            results["snapshot"] = _measure(get("/snapshot"), counter, repeat)
            results["decision_options"] = _measure(get("/decision-options"), counter, repeat)
            results["advance_1_tick"] = _measure(advance(1), counter, repeat)
            results["decision_submit"] = _measure(
                decide("set_ration_level", level=0.95), counter, repeat
            )
            advance(100 - c.get(f"{base}/snapshot").json()["clock"]["tick"])()
            results["objective_outlook"] = _measure(get("/objectives"), counter, repeat)
            results["radiation_budget"] = _measure(get("/radiation-budget"), counter, repeat)
            results["resource_detail"] = _measure(get("/resources/battery"), counter, repeat)
            results["events_resume"] = _measure(
                get("/events", last_state_version=max(1, state["version"] - 5)), counter, repeat
            )
            lens_body = {
                "candidates": [
                    {"label": "shelter", "decisions": [{"option_id": "set_crew_location:shelter"}]}
                ],
                "horizon_ticks": 24,
                "samples": 4,
            }
            results["future_lens_default"] = _measure(
                lambda: c.post(f"{base}/future-lens/projections", json=lens_body),
                counter,
                repeat,
            )
            results["history"] = _measure(get("/history"), counter, repeat)
            results["timelines"] = _measure(get("/timelines"), counter, repeat)
            results["rewind_points"] = _measure(get("/rewind-points"), counter, repeat)
            # at most 5 calls: from tick 100, 5 x 24 ticks stay within the 240-tick mission
            results["advance_24_ticks"] = _measure(
                advance(24), counter, min(5, max(1, repeat // 2))
            )
            while c.get(f"{base}/snapshot").json()["status"] != "concluded":
                advance(240)()
            results["completion"] = _measure(get("/completion"), counter, repeat)
            results["black_box_summary"] = _measure(
                get("/black-box/summary"), counter, max(1, repeat // 2)
            )
            results["mission_dna"] = _measure(get("/mission-dna/share"), counter, repeat)
            results["engineering_profile"] = _measure(get("/engineering-profile"), counter, repeat)
            results["science_claims"] = _measure(
                lambda: c.get(f"{API}/science/claims"), counter, repeat
            )
            event.remove(sync_engine, "before_cursor_execute", counter)
    return {
        "report": "odyssey.api_bench",
        "database": "postgresql" if database_url and "postgres" in database_url else "sqlite",
        "repeat": repeat,
        "endpoints": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = run(args.database_url, args.repeat)
    print(f"database: {report['database']}, repeat: {report['repeat']}")
    print(f"{'endpoint':22} {'median ms':>10} {'p95 ms':>8} {'max ms':>8} {'queries':>8}")
    for name, r in report["endpoints"].items():
        print(
            f"{name:22} {r['median_ms']:10.2f} {r['p95_ms']:8.2f} {r['max_ms']:8.2f} "
            f"{r['queries_median']:8d}"
        )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
