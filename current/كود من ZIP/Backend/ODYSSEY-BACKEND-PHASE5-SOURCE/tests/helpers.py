"""Shared test helpers (pure functions; fixtures live in conftest.py)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.ledger import GENESIS_HASH, DecisionRecord, record_decision
from app.simulation.scenarios.loader import get_scenario
from app.simulation.scenarios.schema import ScenarioDefinition

Plan = Mapping[int, Sequence[Mapping[str, Any]]]


@dataclass
class PlayedMission:
    initial: MissionState
    records: list[DecisionRecord]
    final: MissionState


def play(
    engine: SimulationEngine,
    seed: int,
    plan: Plan,
    until_tick: int,
    *,
    timeline_id: str = "tl-main",
    session_id: str = "sess",
) -> PlayedMission:
    """Apply ``plan`` (tick → raw decisions, applied before stepping that tick) up to a tick."""
    initial = engine.initial_state(seed)
    state = initial
    records: list[DecisionRecord] = []
    prev = GENESIS_HASH
    while True:
        for raw in plan.get(state.tick, ()):
            rec, res = record_decision(
                engine,
                state,
                parse_decision(dict(raw)),
                session_id=session_id,
                timeline_id=timeline_id,
                sequence=len(records) + 1,
                prev_record_hash=prev,
            )
            records.append(rec)
            prev = rec.record_hash
            state = res.state
        if state.tick >= until_tick or state.status == MissionStatus.CONCLUDED:
            break
        state = engine.step(state).state
    return PlayedMission(initial, records, state)


def scenario_variant(
    mutate: Callable[[dict[str, Any]], None], base: ScenarioDefinition | None = None
) -> ScenarioDefinition:
    """Deep-copy LUNA-01 (or ``base``) as a dict, mutate it, and re-validate."""
    data = (base or get_scenario("luna-01")).model_dump(mode="json", by_alias=True)
    mutate(data)
    return ScenarioDefinition.model_validate(data)


def consumer(data: dict[str, Any], consumer_id: str) -> dict[str, Any]:
    return next(c for c in data["power"]["consumers"] if c["id"] == consumer_id)


def component(data: dict[str, Any], component_id: str) -> dict[str, Any]:
    return next(c for c in data["degradation"]["components"] if c["id"] == component_id)


def quiet(data: dict[str, Any]) -> None:
    """Remove randomness and scenario events so physics tests are isolated."""
    data["events"] = []
    for comp in data["degradation"]["components"]:
        comp["fault_probability_per_tick"] = 0.0
    data["rover"]["loss_probability_per_tick"] = 0.0
