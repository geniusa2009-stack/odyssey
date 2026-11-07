"""Performance sanity checks (generous thresholds; numbers are printed with ``-s``).

These guard against accidental order-of-magnitude regressions, not micro-benchmarks. Measured
reference values for one development machine are recorded in docs/TESTING.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.future_lens import FutureLens, FutureLensRequest
from app.simulation.analysis.reconstruct import counterfactual_factory, reconstruct
from app.simulation.engine.engine import SimulationEngine
from tests.helpers import play

pytestmark = pytest.mark.perf


def best_of(fn: Callable[[], object], repeat: int = 3) -> float:
    """Best wall time in milliseconds (best-of-N reduces scheduler noise)."""
    times = []
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        times.append((time.perf_counter() - started) * 1000)
    return min(times)


def test_tick_throughput(engine: SimulationEngine) -> None:
    initial = engine.initial_state(1)
    ms = best_of(lambda: engine.advance(initial, 240))
    per_tick = ms / 240
    print(f"\n[perf] full 240-tick mission: {ms:.1f} ms ({per_tick:.3f} ms/tick)")
    assert per_tick < 5.0


def test_future_lens_branching(engine: SimulationEngine) -> None:
    mid = engine.advance(engine.initial_state(1), 100).state
    req = FutureLensRequest.model_validate(
        {
            "candidates": [
                {
                    "label": f"c{i}",
                    "decisions": [{"type": "set_thermal_setpoint", "target_c": 12.0 + i}],
                }
                for i in range(4)
            ],
            "horizon_ticks": 48,
            "samples": 4,
        }
    )
    ms = best_of(lambda: FutureLens(engine).predict(mid, req), repeat=2)
    print(f"\n[perf] Future Lens 5 branches x 4 samples x 48 ticks: {ms:.1f} ms")
    assert ms < 15_000


def test_timeline_reconstruction_and_black_box(engine: SimulationEngine) -> None:
    plan = {
        t: [{"type": "set_thermal_setpoint", "target_c": 15.0 + (t % 5)}]
        for t in range(10, 230, 10)
    }
    played = play(engine, 3, plan, 240)
    rec_ms = best_of(lambda: reconstruct(engine, played.initial, played.records, played.final.tick))
    record = reconstruct(engine, played.initial, played.records, played.final.tick)
    cf = counterfactual_factory(engine, played.initial, played.records, played.final.tick)
    bb_ms = best_of(lambda: build_black_box(engine, record, counterfactual=cf), repeat=1)
    print(
        f"\n[perf] reconstruct 240 ticks / {len(played.records)} decisions (hash-verified): "
        f"{rec_ms:.1f} ms; black box with counterfactuals: {bb_ms:.1f} ms"
    )
    assert rec_ms < 10_000 and bb_ms < 60_000


def test_api_state_reads(client: TestClient) -> None:
    sid = client.post("/api/v1/mission-sessions", json={"seed": 1}).json()["id"]
    client.post(f"/api/v1/mission-sessions/{sid}/advance", json={"ticks": 120})
    n = 30
    started = time.perf_counter()
    for _ in range(n):
        assert client.get(f"/api/v1/mission-sessions/{sid}/state").status_code == 200
    per_read = (time.perf_counter() - started) * 1000 / n
    adv = best_of(
        lambda: client.post(f"/api/v1/mission-sessions/{sid}/advance", json={"ticks": 1}), repeat=5
    )
    print(
        f"\n[perf] GET /state (SQLite, in-process): {per_read:.2f} ms/read; "
        f"POST /advance 1 tick: {adv:.2f} ms"
    )
    assert per_read < 500
