"""Phase 4: unit tests of the frontend-safe read models (app/read_models)."""

from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from app.read_models.common import UNIT_PRECISION, rnd
from app.read_models.decisions import (
    _catalogue,
    build_decision_options,
    command_to_decision,
    decision_parameters,
    decision_to_option_id,
    impact_of,
)
from app.read_models.events import event_view
from app.read_models.mission import TimelineRef, build_hud, build_snapshot
from app.read_models.radiation import build_radiation
from app.read_models.resources import build_resources
from app.simulation.domain.decisions import SetCrewLocation, StartScienceActivity
from app.simulation.domain.enums import CrewLocation
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

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


def states(engine: SimulationEngine) -> list[MissionState]:
    """A few representative states of one played mission (day, science, storm, night, end)."""
    s = engine.initial_state(5)
    out = [s]
    s = engine.advance(s, 20).state
    s = engine.apply_decision(s, StartScienceActivity(opportunity_id="regolith_survey"), "d1").state
    out.append(s)
    s = engine.advance(s, 105).state  # tick 125: solar particle event under way
    s = engine.apply_decision(s, SetCrewLocation(location=CrewLocation.SHELTER), "d2").state
    out.append(s)
    s = engine.advance(s, 90).state  # night
    out.append(s)
    out.append(engine.advance(s, 240).state)  # concluded
    return out


def test_static_affected_systems_match_the_engine(engine: SimulationEngine) -> None:
    """Unavailable options report a static list; it must equal what the engine reports when
    the same option is available."""
    seen = 0
    for state in states(engine)[:-1]:
        catalogue = {o.option_id: o for o in _catalogue(engine, state, include_unopened=False)}
        for view in build_decision_options(engine, state).options:
            if view.available:
                static = catalogue[view.option_id].static_affected
                assert sorted(view.affected_systems) == sorted(static), view.option_id
                seen += 1
    assert seen > 50


@pytest.mark.parametrize(
    ("option_id", "impact"),
    [
        ("set_subsystem_mode:co2_scrubber:eco", "major"),  # HIGH in the Phase 3 audit
        ("set_subsystem_mode:oxygen_generation:off", "major"),
        ("set_subsystem_mode:water_recovery:eco", "major"),
        ("set_subsystem_mode:comms:off", "major"),  # MEDIUM
        ("set_subsystem_mode:comms:eco", "local"),  # LOCAL
        ("set_subsystem_mode:heater:eco", "local"),
        ("set_crew_location:shelter", "major"),
        ("start_science_activity:regolith_survey", "major"),
        ("rover_command:traverse:far_crater", "major"),
        ("schedule_maintenance:water_processor", "local"),  # D24: LOCAL / CUMULATIVE
        ("clean_solar_array:cdr", "local"),
        ("set_thermal_setpoint", "local"),
    ],
)
def test_impact_classes_follow_the_phase3_measurements(option_id: str, impact: str) -> None:
    assert impact_of(option_id) == impact


def test_option_ids_round_trip(engine: SimulationEngine) -> None:
    state = engine.advance(engine.initial_state(1), 100).state
    for view in build_decision_options(engine, state).options:
        params = {p.name: (p.min + p.max) / 2 for p in view.parameters}
        decision = command_to_decision(engine, view.option_id, view.decision_type, params)
        assert decision_to_option_id(decision) == view.option_id
        assert decision_parameters(decision) == params


def test_projections_never_mutate_state(engine: SimulationEngine) -> None:
    for state in states(engine):
        before = state.state_hash()
        dump = state.model_dump(mode="json")
        build_snapshot(engine, state, session_id="s", timeline=TIMELINE, previous=None)
        build_radiation(engine, state)
        assert state.state_hash() == before
        assert state.model_dump(mode="json") == dump


def rounded(value: float, unit: str) -> bool:
    return value == round(value, UNIT_PRECISION.get(unit, 3))


def test_numbers_are_rounded_to_display_precision(engine: SimulationEngine) -> None:
    for state in states(engine):
        for res in build_resources(engine, state):
            assert rounded(res.value, res.unit), res.id
            assert res.display_precision == UNIT_PRECISION.get(res.unit, 3)
            for d in res.details:
                assert rounded(d.value, d.unit), d.id
        hud = build_hud(engine, state)
        assert rounded(hud.battery_soc, "fraction") and rounded(hud.co2_ppm, "ppm")


def test_rounding_never_returns_negative_zero_or_nan() -> None:
    assert math.copysign(1.0, rnd(-0.0001, 2)) == 1.0
    assert rnd(float("nan"), 2) == 0.0 and rnd(float("inf"), 2) == 0.0


def test_read_models_are_closed_and_immutable(engine: SimulationEngine) -> None:
    hud = build_hud(engine, engine.initial_state(1))
    with pytest.raises(ValidationError):
        hud.model_copy(update={}).__class__.model_validate({**hud.model_dump(), "extra": 1})
    with pytest.raises(ValidationError):
        hud.tick = 5  # type: ignore[misc]


def test_radiation_budget_during_the_storm(engine: SimulationEngine) -> None:
    storm = states(engine)[2]
    rad = build_radiation(engine, storm)
    assert rad.exposure_status == "elevated"
    assert rad.surface_dose_rate_msv_h > (rad.background_dose_rate_msv_h or 0)
    assert rad.crew_in_shelter == len(rad.crew) - len(rad.crew_on_eva)
    assert rad.received_dose_rate_msv_h < rad.surface_dose_rate_msv_h  # shielded
    assert rad.dose_limit_msv == 15.0
    margin = rad.dose_margin_msv
    assert margin is not None
    assert margin == pytest.approx(15.0 - rad.max_dose_msv, abs=0.011)


def test_event_view_strips_scenario_internals(engine: SimulationEngine) -> None:
    result = engine.advance(engine.initial_state(2), 200)
    keys: set[str] = set()
    for e in result.events:
        data: dict[str, Any] = event_view(e).data
        keys |= set(data)
    assert not keys & {"trigger", "effects", "random"}
    assert "opened_opportunities" in keys  # science windows say what they opened
