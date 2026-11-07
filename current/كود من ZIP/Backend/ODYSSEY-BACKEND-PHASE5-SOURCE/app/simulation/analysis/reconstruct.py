"""Full mission reconstruction (the input to every post-hoc analysis)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.ledger import DecisionRecord
from app.simulation.replay.replay import ReplayDecision, replay


@dataclass(frozen=True, slots=True)
class MissionRecord:
    """Replayed mission: ``history[t]`` is the effective state at tick ``t``."""

    records: tuple[DecisionRecord, ...]
    history: tuple[MissionState, ...]
    events: tuple[MissionEvent, ...]

    @property
    def final_state(self) -> MissionState:
        return self.history[-1]

    def decision_info(self) -> dict[str, dict[str, Any]]:
        return {
            r.decision_id: {
                "decision_type": r.decision_type,
                "inputs": r.inputs,
                "phase": r.phase,
                "sequence": r.sequence,
                "tick": r.tick,
            }
            for r in self.records
        }


def reconstruct(
    engine: SimulationEngine,
    initial_state: MissionState,
    records: Sequence[DecisionRecord],
    until_tick: int,
    *,
    verify_hashes: bool = True,
) -> MissionRecord:
    result = replay(
        engine,
        initial_state,
        [ReplayDecision.from_record(r) for r in records],
        until_tick,
        record_history=True,
        verify_hashes=verify_hashes,
    )
    return MissionRecord(
        records=tuple(sorted(records, key=lambda r: r.sequence)),
        history=tuple(result.history),
        events=tuple(result.events),
    )


def counterfactual_factory(
    engine: SimulationEngine,
    initial_state: MissionState,
    records: Sequence[DecisionRecord],
    until_tick: int,
) -> Callable[[str], tuple[MissionState, ...]]:
    """Return ``decision_id → history without that decision`` (other decisions kept).

    Results are memoised per decision id; each call is a full deterministic replay with the same
    seed, so the only difference from the real mission is the removed decision.
    """
    decisions = [ReplayDecision.from_record(r) for r in records]
    cache: dict[str, tuple[MissionState, ...]] = {}

    def run(decision_id: str) -> tuple[MissionState, ...]:
        if decision_id not in cache:
            kept = [d for d in decisions if d.decision_id != decision_id]
            result = replay(
                engine, initial_state, kept, until_tick, record_history=True, skip_invalid=True
            )
            cache[decision_id] = tuple(result.history)
        return cache[decision_id]

    return run
