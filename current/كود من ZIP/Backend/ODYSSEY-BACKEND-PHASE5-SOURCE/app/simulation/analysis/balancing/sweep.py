"""Batch execution: strategies × seeds (× scenario overrides), optionally in parallel.

Results are returned sorted by (strategy, seed) regardless of worker scheduling, so a sweep's
output is byte-identical for any number of workers.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario, scenario_content_hash
from app.simulation.scenarios.schema import ScenarioDefinition

from .overrides import apply_overrides
from .runner import MissionMetrics, run_mission
from .strategies import make_strategy


def resolve_scenario_id(name: str) -> str:
    """Accept ``luna-01``, ``luna01`` or ``LUNA01``."""
    from app.simulation.scenarios.loader import list_scenarios

    wanted = name.lower().replace("-", "").replace("_", "")
    for sc in list_scenarios():
        if sc.id.replace("-", "") == wanted:
            return sc.id
    raise KeyError(f"unknown scenario {name!r}")


@dataclass(frozen=True, slots=True)
class SweepSpec:
    scenario_id: str = "luna-01"
    strategies: tuple[str, ...] = ("balanced",)
    seeds: tuple[int, ...] = tuple(range(1, 51))
    overrides: tuple[tuple[str, Any], ...] = ()
    check_invariants: bool = False
    suppressed_events: tuple[str, ...] = ()

    def options(self) -> RunOptions:
        return RunOptions(suppressed_events=frozenset(self.suppressed_events))

    def build_scenario(self) -> ScenarioDefinition:
        return apply_overrides(get_scenario(self.scenario_id), self.overrides)


@dataclass(slots=True)
class SweepResult:
    spec: SweepSpec
    scenario_hash: str
    rows: list[MissionMetrics] = field(default_factory=list)


# Worker-process state (one engine per process, built once).
_WORKER: dict[str, Any] = {}


def _init_worker(scenario_json: dict[str, Any]) -> None:
    _WORKER["engine"] = SimulationEngine(ScenarioDefinition.model_validate(scenario_json))


_Chunk = tuple[list[tuple[str, int]], dict[str, Any], bool, tuple[str, ...]]


def _run_chunk(args: _Chunk) -> list[MissionMetrics]:
    jobs, overrides, strict, suppressed = args
    engine: SimulationEngine = _WORKER["engine"]
    opts = RunOptions(suppressed_events=frozenset(suppressed))
    return [
        run_mission(
            engine, s, seed, overrides=overrides, options=opts, check_invariants=strict
        ).metrics
        for s, seed in jobs
    ]


def run_sweep(
    spec: SweepSpec, *, workers: int = 1, progress: Callable[[int, int], None] | None = None
) -> SweepResult:
    """Run every (strategy, seed) pair. ``workers > 1`` uses a process pool."""
    for name in spec.strategies:
        make_strategy(name, 0)  # fail fast on unknown names
    scenario = spec.build_scenario()
    jobs = [(s, seed) for s in spec.strategies for seed in spec.seeds]
    overrides = dict(spec.overrides)
    rows: list[MissionMetrics] = []
    if workers <= 1 or len(jobs) < 8:
        engine = SimulationEngine(scenario)
        for i, (s, seed) in enumerate(jobs, 1):
            rows.append(
                run_mission(
                    engine,
                    s,
                    seed,
                    overrides=overrides,
                    options=spec.options(),
                    check_invariants=spec.check_invariants,
                ).metrics
            )
            if progress is not None:
                progress(i, len(jobs))
    else:
        size = max(1, len(jobs) // (workers * 8))
        chunks = [jobs[i : i + size] for i in range(0, len(jobs), size)]
        payload = scenario.model_dump(mode="json", by_alias=True)
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(payload,)
        ) as pool:
            done = 0
            tasks = [(c, overrides, spec.check_invariants, spec.suppressed_events) for c in chunks]
            for chunk_rows in pool.map(_run_chunk, tasks):
                rows.extend(chunk_rows)
                done += len(chunk_rows)
                if progress is not None:
                    progress(done, len(jobs))
    rows.sort(key=lambda r: (r.strategy, r.seed))
    return SweepResult(spec=spec, scenario_hash=scenario_content_hash(scenario), rows=rows)


def default_workers() -> int:
    return max(1, min(8, (os.cpu_count() or 1)))


def seeds_from(start: int, count: int) -> tuple[int, ...]:
    return tuple(range(start, start + count))


def iter_rows(results: Iterable[SweepResult]) -> Iterable[MissionMetrics]:
    for res in results:
        yield from res.rows


def strategies_or_all(names: Sequence[str] | None) -> tuple[str, ...]:
    from .strategies import PROBE_STRATEGIES

    out: list[str] = []
    for raw in names or ["all"]:
        key = raw.strip().lower().replace("-", "_")
        for name in PROBE_STRATEGIES if key == "all" else (key,):
            if name not in out:
                out.append(name)
    return tuple(out)
