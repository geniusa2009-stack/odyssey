"""Backward compatibility: sessions pinned to LUNA-01 v0.1.0 replay exactly as before Phase 3.

Sessions store the scenario definition they were created with (``mission_scenarios``), so an old
session keeps running on v0.1.0 numbers after the shipped scenario moves to a newer version.
That only holds if every Phase 3 engine mechanic is *opt-in* through scenario fields. This test
replays eight golden missions recorded at commit 9d0b00d (before any Phase 3 change) on the
v0.1.0 definition and requires byte-identical final states and event streams.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.simulation.canonical import sha256_hex
from app.simulation.domain.decisions import parse_decision
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.replay import ReplayDecision, replay
from app.simulation.scenarios.loader import get_scenario, load_scenario_file

COMPAT = Path(__file__).parent / "fixtures" / "compat"
V010 = load_scenario_file(COMPAT / "luna-01-v0.1.0.yaml")
GOLDEN: list[dict[str, Any]] = json.loads(
    (COMPAT / "luna-01-v0.1.0-golden.json").read_text(encoding="utf-8")
)["cases"]


def test_fixture_is_the_v010_scenario() -> None:
    assert V010.version == "0.1.0"
    assert get_scenario("luna-01").version != V010.version


@pytest.mark.parametrize("case", GOLDEN, ids=[c["label"] for c in GOLDEN])
def test_v010_missions_replay_identically(case: dict[str, Any]) -> None:
    engine = SimulationEngine(V010)
    strategy = case["label"].split(":")[0]
    decisions = [
        ReplayDecision(f"{strategy}:{i + 1}", i + 1, d["tick"], parse_decision(d["decision"]))
        for i, d in enumerate(case["decisions"])
    ]
    result = replay(engine, engine.initial_state(case["seed"]), decisions, 240)
    state = result.state
    assert state.tick == case["final_tick"]
    assert state.outcome is not None and state.outcome.code == case["outcome"]
    assert {k: v.status.value for k, v in sorted(state.objectives.items())} == case["objectives"]
    assert state.state_hash() == case["final_state_hash"]
    events = sha256_hex([e.model_dump(mode="json") for e in result.events])
    assert events == case["events_hash"]


def test_v010_has_no_phase3_metrics() -> None:
    """Dose-budget metrics exist only for scenarios that declare a mission dose limit."""
    engine = SimulationEngine(V010)
    assert not engine.metrics.has("crew.projected_dose_margin_msv")
    assert SimulationEngine(get_scenario("luna-01")).metrics.has("crew.projected_dose_margin_msv")
