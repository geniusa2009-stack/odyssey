"""Performance at scale: missions/s, memory, and the cost of lens, black box and replay.

Measures; does not optimise. Peak RSS comes from ``resource.getrusage`` (self + worker
children); "history memory" is measured with ``tracemalloc`` while a full 240-tick history is
held.
"""

from __future__ import annotations

import gc
import pickle
import resource
import statistics
import time
import tracemalloc
from collections.abc import Callable, Sequence
from typing import Any

from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.future_lens import FutureLens, FutureLensRequest
from app.simulation.analysis.reconstruct import counterfactual_factory, reconstruct
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.replay import replay
from app.simulation.scenarios.loader import get_scenario

from .quality import injected_failures
from .runner import run_mission
from .sweep import SweepSpec, run_sweep, seeds_from


def _rss_mb() -> dict[str, float]:
    to_mb = 1 / 1024  # Linux reports KiB
    return {
        "self_peak_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * to_mb,
        "children_peak_mb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * to_mb,
    }


def _timed(fn: Callable[[], Any], repeat: int = 3) -> tuple[float, Any]:
    best, out = float("inf"), None
    for _ in range(repeat):
        t = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t)
    return best * 1000, out


def bench_missions(
    counts: Sequence[int], *, workers: int, strategy: str = "balanced"
) -> list[dict[str, Any]]:
    rows = []
    for n in counts:
        gc.collect()
        t = time.perf_counter()
        res = run_sweep(SweepSpec(strategies=(strategy,), seeds=seeds_from(1, n)), workers=workers)
        wall = time.perf_counter() - t
        rows.append(
            {
                "missions": n,
                "workers": workers,
                "strategy": strategy,
                "wall_s": wall,
                "ms_per_mission": wall / n * 1000,
                "missions_per_s": n / wall,
                "result_rows_kb": len(pickle.dumps(res.rows)) / 1024,
                **_rss_mb(),
            }
        )
    return rows


def bench_components(engine: SimulationEngine | None = None) -> dict[str, Any]:
    eng = engine or SimulationEngine(get_scenario("luna-01"))
    out: dict[str, Any] = {}
    initial = eng.initial_state(1)
    ms, _ = _timed(lambda: eng.advance(initial, 240))
    out["engine_240_ticks_ms"] = ms
    ms, run = _timed(lambda: run_mission(eng, "balanced", 1))
    out["mission_balanced_ms"] = ms
    ms, _ = _timed(lambda: run_mission(eng, "balanced", 1, check_invariants=True), repeat=1)
    out["mission_balanced_with_invariants_ms"] = ms

    mid = eng.advance(initial, 100).state
    small = FutureLensRequest.model_validate(
        {
            "candidates": [
                {
                    "label": "eco",
                    "decisions": [
                        {"type": "set_subsystem_mode", "subsystem": "comms", "mode": "eco"}
                    ],
                }
            ]
        }
    )
    large = FutureLensRequest.model_validate(
        {
            "candidates": [
                {
                    "label": f"c{i}",
                    "decisions": [{"type": "set_thermal_setpoint", "target_c": 12.0 + i}],
                }
                for i in range(4)
            ],
            "horizon_ticks": 72,
            "samples": 16,
        }
    )
    out["future_lens_default_ms"], _ = _timed(lambda: FutureLens(eng).predict(mid, small))
    out["future_lens_5x16x72_ms"], _ = _timed(lambda: FutureLens(eng).predict(mid, large), repeat=1)

    decisions = [d.to_replay() for d in run.decisions]
    out["replay_240_ticks_ms"], _ = _timed(
        lambda: replay(eng, run.initial, decisions, run.final.tick)
    )
    out["replay_with_history_ms"], _ = _timed(
        lambda: replay(eng, run.initial, decisions, run.final.tick, record_history=True)
    )

    bb_times = []
    for case in injected_failures():
        t = time.perf_counter()
        rec = reconstruct(case.engine, case.initial, case.records, case.final.tick)
        cf = counterfactual_factory(case.engine, case.initial, case.records, case.final.tick)
        build_black_box(case.engine, rec, counterfactual=cf)
        bb_times.append((time.perf_counter() - t) * 1000)
    out["black_box_with_counterfactuals_ms"] = {
        "mean": statistics.fmean(bb_times),
        "max": max(bb_times),
        "cases": len(bb_times),
    }

    gc.collect()
    tracemalloc.start()
    history = replay(eng, run.initial, decisions, run.final.tick, record_history=True).history
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    out["history_240_states_mb"] = current / 1e6
    out["history_peak_mb"] = peak / 1e6
    out["state_json_bytes"] = len(history[-1].model_dump_json())
    out.update(_rss_mb())
    return out
