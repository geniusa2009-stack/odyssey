"""Phase 4: frontend-facing projections never reveal hidden future information.

Method: a *variant* of LUNA-01 that differs only in unforeseeable events after tick ``t``
(scheduled ones removed, random flares limited to ``<= t``). Played with the same seed and the
same decisions up to ``t``, both missions are in the same state. Every projection a client can
receive at ``t`` (snapshot, radiation budget, objectives, decision options, known-only Future
Lens) must then be identical: if any of them consulted a future hidden event, the two would
differ. Two power checks show the comparison can fail: the omniscient Future Lens and the raw
engine Future Lens result *do* differ between the two scenarios.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.read_models.analysis import build_future_lens_view
from app.read_models.decisions import build_decision_options
from app.read_models.mission import TimelineRef, build_snapshot
from app.read_models.objectives import build_objectives
from app.read_models.radiation import build_radiation
from app.read_models.visibility import entered_phases
from app.simulation.analysis.future_lens import (
    CandidateBranch,
    FutureLens,
    FutureLensRequest,
    FutureLensResult,
)
from app.simulation.domain.decisions import (
    DecisionInput,
    SetCrewLocation,
    StartScienceActivity,
)
from app.simulation.domain.enums import CrewLocation
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario
from app.simulation.scenarios.schema import ScenarioDefinition

SEEDS = (3, 11, 29)
TICKS = (60, 100, 121)
TIMELINE = TimelineRef(
    id="t",
    label="main",
    parent_timeline_id=None,
    fork_tick=None,
    fork_sequence=None,
    status="active",
    is_active=True,
    head_tick=0,
    head_sequence=0,
    state_version=1,
)


def without_future_hidden_events(sc: ScenarioDefinition, t: int) -> ScenarioDefinition:
    data = sc.model_dump(mode="json", by_alias=True)
    kept: list[dict[str, Any]] = []
    for event in data["events"]:
        trigger = event["trigger"]
        if not event["foreseeable"]:
            if trigger["type"] == "scheduled" and trigger["at_tick"] > t:
                continue
            if trigger["type"] == "random":
                trigger["to_tick"] = min(trigger.get("to_tick") or t, t)
        kept.append(event)
    data["events"] = kept
    return ScenarioDefinition.model_validate(data)


PLAN: dict[int, DecisionInput] = {
    15: StartScienceActivity(opportunity_id="regolith_survey"),
    50: SetCrewLocation(location=CrewLocation.SHELTER),
    58: SetCrewLocation(location=CrewLocation.HABITAT),
    97: StartScienceActivity(opportunity_id="ice_core_sampling"),
}


def play(engine: SimulationEngine, seed: int, until: int) -> MissionState:
    state = engine.initial_state(seed)
    for tick in sorted(PLAN):
        if tick > until:
            break
        state = engine.advance(state, tick - state.tick).state
        state = engine.apply_decision(state, PLAN[tick], f"d{tick}").state
    return engine.advance(state, until - state.tick).state


def lens(engine: SimulationEngine, state: MissionState, policy: str) -> FutureLensResult:
    request = FutureLensRequest(
        candidates=[
            CandidateBranch(
                label="shelter", decisions=[SetCrewLocation(location=CrewLocation.SHELTER)]
            )
        ],
        horizon_ticks=48,
        samples=4,
        knowledge_policy=policy,
    )
    return FutureLens(engine).predict(state, request)


def lens_view(engine: SimulationEngine, result: FutureLensResult, state: MissionState) -> Any:
    return build_future_lens_view(
        engine,
        result,
        session_id="s",
        timeline_id="t",
        state_version=1,
        requested_ticks=48,
        entered=entered_phases(state),
    )


@pytest.fixture(scope="module")
def shipped() -> SimulationEngine:
    return SimulationEngine(get_scenario("luna-01"))


@pytest.mark.parametrize("t", TICKS)
@pytest.mark.parametrize("seed", SEEDS)
def test_projections_identical_without_future_hidden_events(
    shipped: SimulationEngine, seed: int, t: int
) -> None:
    variant = SimulationEngine(without_future_hidden_events(shipped.scenario, t))
    a, b = play(shipped, seed, t), play(variant, seed, t)
    assert a.state_hash() == b.state_hash()  # same past → same state

    assert build_snapshot(shipped, a, session_id="s", timeline=TIMELINE) == build_snapshot(
        variant, b, session_id="s", timeline=TIMELINE
    )
    assert build_radiation(shipped, a) == build_radiation(variant, b)
    assert build_objectives(shipped, a) == build_objectives(variant, b)
    assert build_decision_options(shipped, a) == build_decision_options(variant, b)
    known_a = lens_view(shipped, lens(shipped, a, "known_only"), a)
    known_b = lens_view(variant, lens(variant, b, "known_only"), b)
    assert known_a == known_b


@pytest.mark.parametrize("seed", SEEDS)
def test_power_check_hidden_events_do_change_omniscient_and_raw_results(
    shipped: SimulationEngine, seed: int
) -> None:
    """The comparison above is not vacuous: the storm at tick 122 is inside the 48-tick
    horizon from tick 100, and both the omniscient view and the raw engine result differ."""
    t = 100
    variant = SimulationEngine(without_future_hidden_events(shipped.scenario, t))
    a, b = play(shipped, seed, t), play(variant, seed, t)
    omni_a = lens_view(shipped, lens(shipped, a, "omniscient"), a)
    omni_b = lens_view(variant, lens(variant, b, "omniscient"), b)
    assert omni_a != omni_b
    raw_a, raw_b = lens(shipped, a, "known_only"), lens(variant, b, "known_only")
    # The raw engine result names excluded hidden events and lowers its confidence when any
    # remain; the frontend projection removes both signals.
    assert raw_a.model_dump(exclude={"request_hash"}) != raw_b.model_dump(exclude={"request_hash"})


def test_unopened_science_is_not_listed(shipped: SimulationEngine) -> None:
    state = shipped.initial_state(1)
    options = {o.option_id for o in build_decision_options(shipped, state).options}
    assert not any(o.startswith("start_science_activity:") for o in options)
    later = shipped.advance(state, 20).state  # regolith window opened at tick 14
    options = {o.option_id for o in build_decision_options(shipped, later).options}
    assert "start_science_activity:regolith_survey" in options
    assert "start_science_activity:ice_core_sampling" not in options  # opens at tick 96
