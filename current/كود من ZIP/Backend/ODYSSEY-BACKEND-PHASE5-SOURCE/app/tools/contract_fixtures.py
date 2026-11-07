"""Deterministic API contract examples (``tests/fixtures/contract/examples/``).

``python -m app.tools.contract_fixtures --check`` (exit 1 when the committed examples differ)
``python -m app.tools.contract_fixtures --write`` (regenerate after a reviewed contract change)

Drives one scripted LUNA-01 session (seed 42) through the frozen contract endpoints
through an in-process app (temporary SQLite database) and writes JSON examples the frontend
can use as mock data: bootstrap, a mid-game and an emergency snapshot, a decision result, the
realtime events of one transition, a Future Lens projection, the mission completion and the
Black Box summary.

They are API contract examples, not frontend code. Determinism: UUIDs are drawn from a counter
for the duration of the run (session, timeline and decision ids and therefore state hashes are
reproducible); wall-clock timestamps are replaced by fixed placeholders.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "tests" / "fixtures" / "contract" / "examples"
API = "/api/v1"
SEED = 42
FIXED_TIME = "2026-10-19T06:00:00+00:00"
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
_UUID_PREFIX = 0xD0D00000 << 96


@contextmanager
def deterministic_uuids() -> Iterator[None]:
    """Replace ``uuid.uuid4`` by a counter (``d0d00000-0000-0000-0000-00000000000N``)."""
    counter = itertools.count(1)
    original = uuid.uuid4

    def fake() -> uuid.UUID:
        return uuid.UUID(int=_UUID_PREFIX | next(counter))

    uuid.uuid4 = fake
    try:
        yield
    finally:
        uuid.uuid4 = original


def _normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    if isinstance(value, str) and _TIMESTAMP.match(value):
        return FIXED_TIME
    return value


def render(value: Any) -> str:
    return json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def generate() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    out: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp, deterministic_uuids():
        settings = Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{Path(tmp) / 'fixtures.db'}",
            auto_create_schema=True,
            log_json=False,
            log_level="WARNING",
            rate_limit_per_minute=100_000,
            rate_limit_expensive_per_minute=100_000,
            redis_url=None,
        )
        with TestClient(create_app(settings)) as c:

            def ok(resp: Any) -> Any:
                assert resp.status_code < 300, resp.text
                return resp.json()

            sid = ok(c.post(f"{API}/mission-sessions", json={"seed": SEED}))["id"]
            base = f"{API}/mission-sessions/{sid}"
            version = {"v": 0}

            def get(path: str, **params: Any) -> Any:
                return ok(c.get(f"{base}{path}", params=params))

            def advance(ticks: int) -> Any:
                body = ok(
                    c.post(
                        f"{base}/advance-commands",
                        json={"ticks": ticks, "expected_state_version": version["v"]},
                    )
                )
                version["v"] = body["state_version"]
                return body

            def decide(option_id: str, **params: float) -> Any:
                body = ok(
                    c.post(
                        f"{base}/decision-commands",
                        json={
                            "option_id": option_id,
                            "parameters": params,
                            "expected_state_version": version["v"],
                        },
                    )
                )
                version["v"] = body["state_version"]
                return body

            out["mission_bootstrap"] = get("/bootstrap")
            version["v"] = out["mission_bootstrap"]["snapshot"]["state_version"]
            advance(15)
            before = version["v"]
            out["decision_result_example"] = decide("start_science_activity:regolith_survey")
            out["realtime_events_example"] = get("/events", last_state_version=before)
            advance(85)
            decide("start_science_activity:ice_core_sampling")
            out["mission_midgame"] = get("/snapshot")
            advance(23)  # tick 123: inside the tick-122 solar particle event
            out["mission_emergency"] = get("/snapshot")
            out["future_lens_example"] = ok(
                c.post(
                    f"{base}/future-lens/projections",
                    json={
                        "candidates": [
                            {
                                "label": "shelter",
                                "decisions": [{"option_id": "set_crew_location:shelter"}],
                            }
                        ],
                        "include_baseline": True,
                        "horizon_ticks": 24,
                        "samples": 4,
                        "prediction_mode": "known_only",
                    },
                )
            )
            advance(1)
            decide("set_crew_location:shelter")
            advance(12)
            decide("set_crew_location:habitat")
            while get("/snapshot")["status"] != "concluded":
                advance(240)
            out["mission_completion"] = get("/completion")
            out["black_box_example"] = get("/black-box/summary")
    return {name: _normalise(value) for name, value in out.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic API contract examples")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if the examples differ")
    mode.add_argument("--write", action="store_true", help="regenerate the examples")
    args = parser.parse_args(argv)
    examples = generate()
    if args.write:
        EXAMPLES.mkdir(parents=True, exist_ok=True)
        for name, value in examples.items():
            (EXAMPLES / f"{name}.json").write_text(render(value), encoding="utf-8")
        print(f"wrote {len(examples)} examples to {EXAMPLES}")
        return 0
    stale = [
        name
        for name, value in examples.items()
        if not (EXAMPLES / f"{name}.json").exists()
        or (EXAMPLES / f"{name}.json").read_text(encoding="utf-8") != render(value)
    ]
    if stale:
        print("contract examples differ: " + ", ".join(stale))
        print("regenerate after review: python -m app.tools.contract_fixtures --write")
        return 1
    print(f"contract examples unchanged ({len(examples)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
