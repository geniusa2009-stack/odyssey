"""Engine contract: determinism, purity, replayability, decisions, phases, outcomes."""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.simulation.canonical import sha256_hex
from app.simulation.domain.decisions import DECISION_TYPES, parse_decision
from app.simulation.domain.enums import (
    CrewLocation,
    EventKind,
    MissionStatus,
    ObjectiveStatus,
    OpportunityStatus,
    ProvenanceKind,
    RoverStatus,
    SubsystemMode,
)
from app.simulation.domain.state import MissionState
from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import (
    DecisionRejectedError,
    MissionConcludedError,
    SimulationEngine,
)
from tests.helpers import consumer, play, quiet, scenario_variant


def _fingerprint(engine: SimulationEngine, seed: int, ticks: int) -> tuple[str, str]:
    result = engine.advance(engine.initial_state(seed), ticks)
    return result.state.state_hash(), sha256_hex([e.model_dump(mode="json") for e in result.events])


class TestDeterminism:
    def test_same_inputs_same_result(self, engine: SimulationEngine) -> None:
        assert _fingerprint(engine, 7, 240) == _fingerprint(engine, 7, 240)

    def test_fresh_engine_instances_agree(self, engine: SimulationEngine) -> None:
        other = SimulationEngine(engine.scenario)
        assert _fingerprint(engine, 99, 150) == _fingerprint(other, 99, 150)

    def test_seed_matters(self, engine: SimulationEngine) -> None:
        hashes = {_fingerprint(engine, seed, 240)[0] for seed in range(6)}
        assert len(hashes) > 1  # random faults/flares differ by seed

    def test_step_by_step_equals_advance(self, engine: SimulationEngine) -> None:
        state = engine.initial_state(3)
        for _ in range(60):
            state = engine.step(state).state
        assert state.state_hash() == engine.advance(engine.initial_state(3), 60).state.state_hash()

    def test_split_advance_equals_single_advance(self, engine: SimulationEngine) -> None:
        mid = engine.advance(engine.initial_state(5), 77).state
        split = engine.advance(mid, 100).state
        whole = engine.advance(engine.initial_state(5), 177).state
        assert split.state_hash() == whole.state_hash()

    def test_serialization_round_trip_preserves_hash(self, engine: SimulationEngine) -> None:
        state = engine.advance(engine.initial_state(11), 130).state
        reloaded = MissionState.model_validate(state.model_dump(mode="json"))
        assert reloaded.state_hash() == state.state_hash()
        assert engine.step(reloaded).state.state_hash() == engine.step(state).state.state_hash()

    @given(seed=st.integers(0, 2**31), plan_seed=st.integers(0, 10**6))
    def test_property_random_decision_sequences_replay_identically(
        self, engine: SimulationEngine, seed: int, plan_seed: int
    ) -> None:
        import random

        r = random.Random(plan_seed)  # only builds the test plan, never used by the engine
        choices: list[dict[str, Any]] = [
            {"type": "set_subsystem_mode", "subsystem": "comms", "mode": "eco"},
            {"type": "set_subsystem_mode", "subsystem": "oxygen_generation", "mode": "boost"},
            {"type": "set_thermal_setpoint", "target_c": 15.0},
            {"type": "set_ration_level", "level": 0.8},
            {"type": "set_crew_location", "location": "shelter"},
            {"type": "set_crew_location", "location": "habitat"},
            {"type": "schedule_maintenance", "component": "battery"},
        ]
        plan = {t: [r.choice(choices)] for t in sorted(r.sample(range(0, 90), 4))}
        first = _play_tolerant(engine, seed, plan)
        second = _play_tolerant(engine, seed, plan)
        assert first == second


def _play_tolerant(
    engine: SimulationEngine, seed: int, plan: dict[int, list[dict[str, Any]]]
) -> str:
    state = engine.initial_state(seed)
    for _ in range(100):
        for raw in plan.get(state.tick, []):
            with contextlib.suppress(DecisionRejectedError):
                state = engine.apply_decision(state, parse_decision(raw), f"d{state.tick}").state
        state = engine.step(state).state
    return state.state_hash()


class TestPurity:
    def test_step_does_not_mutate_input(
        self, engine: SimulationEngine, initial: MissionState
    ) -> None:
        before = initial.model_dump(mode="json")
        engine.step(initial)
        engine.advance(initial, 50)
        assert initial.model_dump(mode="json") == before

    def test_apply_decision_does_not_mutate_input(
        self, engine: SimulationEngine, initial: MissionState
    ) -> None:
        before = initial.state_hash()
        engine.apply_decision(
            initial,
            parse_decision({"type": "set_subsystem_mode", "subsystem": "comms", "mode": "off"}),
            "d1",
        )
        assert initial.state_hash() == before

    def test_validate_decision_has_no_side_effects(
        self, engine: SimulationEngine, initial: MissionState
    ) -> None:
        before = initial.state_hash()
        engine.validate_decision(
            initial, parse_decision({"type": "set_ration_level", "level": 0.7})
        )
        assert initial.state_hash() == before

    def test_history_entries_are_independent_copies(
        self, engine: SimulationEngine, initial: MissionState
    ) -> None:
        result = engine.advance(initial, 5, record_history=True)
        assert result.history is not None and len(result.history) == 5
        result.history[0].power.battery_charge_kwh = -1.0
        assert result.history[1].power.battery_charge_kwh != -1.0
        assert result.state.power.battery_charge_kwh != -1.0


class TestDecisions:
    def test_decision_types_are_complete(self) -> None:
        assert len(DECISION_TYPES) == len(set(DECISION_TYPES)) == 9

    @pytest.mark.parametrize(
        "raw",
        [
            {"type": "teleport"},
            {"type": "set_thermal_setpoint", "target_c": 900},
            {"type": "set_ration_level", "level": 0},
            {"type": "set_subsystem_mode", "subsystem": "Comms!", "mode": "eco"},
            {"type": "set_subsystem_mode", "subsystem": "comms", "mode": "turbo"},
            {"type": "set_crew_location", "location": "eva"},
            {"type": "rover_command", "action": "self_destruct"},
            {"type": "set_ration_level", "level": 0.5, "extra": 1},
        ],
    )
    def test_malformed_decisions_fail_validation(self, raw: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            parse_decision(raw)

    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            (
                {"type": "set_subsystem_mode", "subsystem": "warp_drive", "mode": "eco"},
                "unknown_subsystem",
            ),
            (
                {"type": "set_subsystem_mode", "subsystem": "habitat_core", "mode": "off"},
                "mode_not_supported",
            ),
            ({"type": "set_thermal_setpoint", "target_c": 30}, "setpoint_out_of_range"),
            ({"type": "set_ration_level", "level": 0.2}, "ration_out_of_range"),
            ({"type": "schedule_maintenance", "component": "flux"}, "unknown_component"),
            (
                {"type": "start_science_activity", "opportunity_id": "regolith_survey"},
                "opportunity_unavailable",
            ),
            ({"type": "stop_science_activity"}, "no_active_science"),
            ({"type": "rover_command", "action": "recall"}, "rover_not_traversing"),
            ({"type": "rover_command", "action": "unstow"}, "rover_not_stowed"),
            (
                {
                    "type": "rover_command",
                    "action": "traverse",
                    "opportunity_id": "regolith_survey",
                },
                "opportunity_unavailable",
            ),
            ({"type": "clean_solar_array", "crew_id": "crew_ghost"}, "crew_unavailable"),
        ],
    )
    def test_rejections_carry_codes(
        self, engine: SimulationEngine, initial: MissionState, raw: dict[str, Any], code: str
    ) -> None:
        with pytest.raises(DecisionRejectedError) as exc:
            engine.apply_decision(initial, parse_decision(raw), "d")
        assert exc.value.code == code

    def test_mode_change_records_provenance_and_event(
        self, engine: SimulationEngine, initial: MissionState
    ) -> None:
        res = engine.apply_decision(
            initial,
            parse_decision(
                {"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "boost"}
            ),
            "dX",
        )
        cs = res.state.power.consumers["co2_scrubber"]
        assert cs.mode == SubsystemMode.BOOST
        assert cs.mode_set_by.kind == ProvenanceKind.DECISION and cs.mode_set_by.ref == "dX"
        assert res.affected_systems == ("power", "life_support")
        assert res.state.decisions_applied == 1
        applied = [e for e in res.events if e.kind == EventKind.DECISION_APPLIED]
        assert applied and applied[0].id.startswith("dX/")

    def test_maintenance_takes_component_offline_then_restores(
        self, engine: SimulationEngine
    ) -> None:
        state = engine.advance(engine.initial_state(1), 10).state
        state.components["radio"].health = 0.5
        res = engine.apply_decision(
            state, parse_decision({"type": "schedule_maintenance", "component": "radio"}), "m1"
        )
        with pytest.raises(DecisionRejectedError, match="already under maintenance"):
            engine.apply_decision(
                res.state,
                parse_decision({"type": "schedule_maintenance", "component": "radio"}),
                "m2",
            )
        after_one = engine.step(res.state).state
        assert after_one.power.consumers["comms"].demand_kw == 0.0  # offline
        assert after_one.comms.link_up is False
        done = engine.advance(res.state, 3)
        assert any(e.key == "maintenance_complete:radio" for e in done.events)
        assert done.state.components["radio"].health == pytest.approx(0.8)

    def test_shelter_moves_crew_except_eva(
        self, engine: SimulationEngine, initial: MissionState
    ) -> None:
        eva = engine.apply_decision(
            initial, parse_decision({"type": "clean_solar_array", "crew_id": "crew_pwr"}), "e1"
        ).state
        with pytest.raises(DecisionRejectedError, match="EVA is already"):
            engine.apply_decision(
                eva, parse_decision({"type": "clean_solar_array", "crew_id": "crew_cdr"}), "e2"
            )
        sheltered = engine.apply_decision(
            eva, parse_decision({"type": "set_crew_location", "location": "shelter"}), "s1"
        ).state
        locations = {c.id: c.location for c in sheltered.crew}
        assert locations["crew_pwr"] == CrewLocation.EVA
        assert sum(1 for loc in locations.values() if loc == CrewLocation.SHELTER) == 3

    def test_concluded_mission_rejects_decisions_and_steps(self, engine: SimulationEngine) -> None:
        final = engine.advance(engine.initial_state(2), 1000).state
        assert final.status == MissionStatus.CONCLUDED
        with pytest.raises(DecisionRejectedError) as exc:
            engine.apply_decision(
                final, parse_decision({"type": "set_ration_level", "level": 0.9}), "late"
            )
        assert exc.value.code == "mission_concluded"
        with pytest.raises(MissionConcludedError):
            engine.step(final)
        assert engine.advance(final, 5).ticks_run == 0

    def test_negative_ticks_rejected(self, engine: SimulationEngine, initial: MissionState) -> None:
        with pytest.raises(ValueError, match="ticks"):
            engine.advance(initial, -1)


class TestScienceAndRover:
    def test_habitat_science_completes_and_scores(self, engine: SimulationEngine) -> None:
        played = play(
            engine,
            42,
            {15: [{"type": "start_science_activity", "opportunity_id": "regolith_survey"}]},
            40,
        )
        opp = played.final.science.opportunities["regolith_survey"]
        assert opp.status == OpportunityStatus.COMPLETED
        assert opp.started_by is not None and opp.started_by.kind == ProvenanceKind.DECISION
        assert played.final.science.points == pytest.approx(20.0, rel=0.05)
        assert played.final.science.active_opportunity is None

    def test_opportunity_missed_after_window(self, engine: SimulationEngine) -> None:
        state = engine.advance(engine.initial_state(42), 80).state
        assert state.science.opportunities["regolith_survey"].status == OpportunityStatus.MISSED

    def test_rover_traverse_lifecycle(self) -> None:
        sc = scenario_variant(quiet)
        eng = SimulationEngine(sc)
        state = eng.initial_state(1)
        from app.simulation.domain.state import OpportunityState, Provenance

        state.science.opportunities["far_crater_traverse"] = OpportunityState(
            id="far_crater_traverse",
            status=OpportunityStatus.OPEN,
            opened_tick=0,
            closes_tick=100,
            opened_by=Provenance(kind=ProvenanceKind.EVENT, ref="t", tick=0),
        )
        res = eng.apply_decision(
            state,
            parse_decision(
                {
                    "type": "rover_command",
                    "action": "traverse",
                    "opportunity_id": "far_crater_traverse",
                }
            ),
            "r1",
        )
        assert res.state.rover.status == RoverStatus.TRAVERSING
        out = eng.advance(res.state, 40)
        keys = [e.key for e in out.events if e.kind == EventKind.ROVER]
        assert keys[:2] == ["rover_on_site", "rover_docked"]
        assert (
            out.state.science.opportunities["far_crater_traverse"].status
            == OpportunityStatus.COMPLETED
        )
        assert out.state.rover.status == RoverStatus.DOCKED

    def test_rover_stranded_when_battery_runs_out(self) -> None:
        def mutate(d: dict[str, Any]) -> None:
            quiet(d)
            d["rover"]["initial_battery_kwh"] = 4.0

        eng = SimulationEngine(scenario_variant(mutate))
        state = eng.initial_state(1)
        from app.simulation.domain.state import OpportunityState, Provenance

        state.science.opportunities["far_crater_traverse"] = OpportunityState(
            id="far_crater_traverse",
            status=OpportunityStatus.OPEN,
            opened_tick=0,
            closes_tick=100,
            opened_by=Provenance(kind=ProvenanceKind.EVENT, ref="t", tick=0),
        )
        state = eng.apply_decision(
            state,
            parse_decision(
                {
                    "type": "rover_command",
                    "action": "traverse",
                    "opportunity_id": "far_crater_traverse",
                }
            ),
            "r1",
        ).state
        out = eng.advance(state, 10)
        assert out.state.rover.status == RoverStatus.LOST
        assert any(
            e.key == "rover_lost" and e.data["cause"] == "battery_depleted" for e in out.events
        )
        with pytest.raises(DecisionRejectedError, match="lost"):
            eng.apply_decision(
                out.state, parse_decision({"type": "rover_command", "action": "stow"}), "r2"
            )

    def test_rover_cannot_traverse_without_link(self) -> None:
        eng = SimulationEngine(scenario_variant(quiet))
        state = eng.initial_state(1)
        from app.simulation.domain.state import OpportunityState, Provenance

        state.science.opportunities["far_crater_traverse"] = OpportunityState(
            id="far_crater_traverse",
            status=OpportunityStatus.OPEN,
            opened_tick=0,
            closes_tick=100,
            opened_by=Provenance(kind=ProvenanceKind.EVENT, ref="t", tick=0),
        )
        state.comms.link_up = False
        with pytest.raises(DecisionRejectedError) as exc:
            eng.apply_decision(
                state,
                parse_decision(
                    {
                        "type": "rover_command",
                        "action": "traverse",
                        "opportunity_id": "far_crater_traverse",
                    }
                ),
                "r1",
            )
        assert exc.value.code == "no_link"

    def test_array_cleaning_eva_restores_dust_and_records_decision(
        self, engine: SimulationEngine
    ) -> None:
        state = engine.advance(engine.initial_state(4), 100).state
        dusty = state.power.dust_factor
        assert dusty < 0.97
        res = engine.apply_decision(
            state, parse_decision({"type": "clean_solar_array", "crew_id": "crew_pwr"}), "clean1"
        )
        out = engine.advance(res.state, 3)
        assert out.state.power.dust_factor > dusty
        assert out.state.power.dust_set_by.ref == "clean1"
        member = next(c for c in out.state.crew if c.id == "crew_pwr")
        assert member.location == CrewLocation.HABITAT and member.fatigue > 0


class TestPhasesAndOutcome:
    def test_full_mission_visits_every_phase_once(self, engine: SimulationEngine) -> None:
        final = engine.advance(engine.initial_state(42), 300).state
        visited = [p.phase for p in final.phase_history]
        assert visited == [p.id for p in engine.scenario.phases]
        assert final.phase == "post_mission_analysis"
        assert final.tick == engine.scenario.time.max_ticks
        # No decisions: the crew survives but the mission's science is never done (v0.2.0).
        assert final.outcome is not None and final.outcome.rule_id == "primary_failed"
        assert final.outcome.code == "mission_failed"
        assert final.objectives["crew_survival"].status == ObjectiveStatus.ACHIEVED
        assert all(o.status != ObjectiveStatus.PENDING for o in final.objectives.values())

    def test_crew_loss_concludes_early(self) -> None:
        def mutate(d: dict[str, Any]) -> None:
            quiet(d)
            consumer(d, "co2_scrubber")["initial_mode"] = "off"
            d["crew_health"]["co2_penalty_per_tick"] = 0.05

        eng = SimulationEngine(scenario_variant(mutate))
        final = eng.advance(eng.initial_state(1), 500).state
        assert final.status == MissionStatus.CONCLUDED
        assert final.outcome is not None and final.outcome.code == "mission_failed_crew_loss"
        assert final.tick < eng.scenario.time.max_ticks
        assert final.objectives["crew_survival"].status == ObjectiveStatus.FAILED

    def test_suppressed_events_do_not_fire(self, engine: SimulationEngine) -> None:
        opts = RunOptions(suppressed_events=frozenset({"solar_particle_event"}))
        out = engine.advance(engine.initial_state(42), 140, opts)
        assert "solar_particle_event" not in out.state.event_fire_counts
        normal = engine.advance(engine.initial_state(42), 140)
        assert normal.state.event_fire_counts["solar_particle_event"] == 1
