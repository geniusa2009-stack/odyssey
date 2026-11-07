"""State invariants and property-based fuzzing of the engine, ledger, replay and forks.

Run deeper locally with ``HYPOTHESIS_PROFILE=fuzz uv run pytest tests/test_invariants_and_fuzz.py``
(500 examples per property instead of the default).
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine
from app.simulation.engine.invariants import InvariantViolationError, check_state
from app.simulation.replay.ledger import GENESIS_HASH, record_decision, verify_chain
from app.simulation.replay.replay import ReplayDecision, replay
from app.simulation.replay.timeline import plan_fork
from app.simulation.scenarios.loader import get_scenario
from tests.helpers import scenario_variant

SC = get_scenario("luna-01")
CONSUMERS = [c.id for c in SC.power.consumers] + ["warp_drive"]
COMPONENTS = [c.id for c in SC.degradation.components] + ["flux_capacitor"]
OPPS = [o.id for o in SC.science.opportunities] + ["ghost_site"]
CREW = [c.id for c in SC.crew] + ["crew_ghost"]

# Every decision shape the API accepts, including values the engine must reject.
decisions = st.one_of(
    st.builds(
        lambda s, m: {"type": "set_subsystem_mode", "subsystem": s, "mode": m},
        st.sampled_from(CONSUMERS),
        st.sampled_from(["off", "eco", "nominal", "boost"]),
    ),
    st.builds(
        lambda t: {"type": "set_thermal_setpoint", "target_c": t},
        st.floats(-50, 50, allow_nan=False),
    ),
    st.builds(
        lambda v: {"type": "set_ration_level", "level": v}, st.floats(0.01, 1.0, allow_nan=False)
    ),
    st.builds(
        lambda c: {"type": "schedule_maintenance", "component": c}, st.sampled_from(COMPONENTS)
    ),
    st.builds(
        lambda loc: {"type": "set_crew_location", "location": loc},
        st.sampled_from(["habitat", "shelter"]),
    ),
    st.builds(
        lambda o: {"type": "start_science_activity", "opportunity_id": o}, st.sampled_from(OPPS)
    ),
    st.just({"type": "stop_science_activity"}),
    st.builds(
        lambda a, o: {"type": "rover_command", "action": a, "opportunity_id": o},
        st.sampled_from(["traverse", "recall", "transfer_energy", "stow", "unstow"]),
        st.one_of(st.none(), st.sampled_from(OPPS)),
    ),
    st.builds(lambda c: {"type": "clean_solar_array", "crew_id": c}, st.sampled_from(CREW)),
)
plans = st.dictionaries(
    st.integers(0, 239), st.lists(decisions, min_size=1, max_size=3), max_size=25
)
MAX_STATE_JSON_BYTES = 64_000


def _play(
    engine: SimulationEngine, seed: int, plan: dict[int, list[dict[str, Any]]]
) -> tuple[MissionState, MissionState, list[Any]]:
    initial = engine.initial_state(seed)
    records: list[Any] = []
    state, prev = initial, GENESIS_HASH
    assert check_state(engine, state) == []
    for _ in range(engine.scenario.time.max_ticks + 1):
        for raw in plan.get(state.tick, []):
            try:
                rec, res = record_decision(
                    engine,
                    state,
                    parse_decision(raw),
                    session_id="s",
                    timeline_id="t",
                    sequence=len(records) + 1,
                    prev_record_hash=prev,
                )
            except DecisionRejectedError:
                continue
            assert check_state(engine, res.state) == []
            records.append(rec)
            prev, state = rec.record_hash, res.state
        if state.status == MissionStatus.CONCLUDED:
            break
        nxt = engine.step(state).state
        problems = check_state(engine, nxt, previous=state)
        if problems:
            raise InvariantViolationError(problems)
        state = nxt
        assert len(json.dumps(state.model_dump(mode="json"))) < MAX_STATE_JSON_BYTES
    assert state.status == MissionStatus.CONCLUDED  # never stuck
    return initial, state, records


class TestInvariantChecker:
    def test_valid_states_pass(self, engine: SimulationEngine) -> None:
        state = engine.initial_state(1)
        assert check_state(engine, state) == []
        nxt = engine.step(state).state
        assert check_state(engine, nxt, previous=state) == []

    @pytest.mark.parametrize(
        ("mutate", "needle"),
        [
            (lambda s: setattr(s.life_support, "water_kg", -1.0), "water_kg"),
            (lambda s: setattr(s.food, "food_kg", -0.5), "food_kg"),
            (lambda s: setattr(s.power, "battery_charge_kwh", 1e6), "battery_charge_kwh"),
            (lambda s: setattr(s.power, "battery_charge_kwh", -1.0), "battery_charge_kwh"),
            (lambda s: setattr(s.crew[0], "health", 1.5), "health"),
            (lambda s: setattr(s.thermal, "habitat_temp_c", math.nan), "not finite"),
            (lambda s: setattr(s.life_support, "co2_kg", math.inf), "not finite"),
            (lambda s: setattr(s, "phase", "warp"), "unknown phase"),
            (lambda s: setattr(s, "tick", 9999), "tick"),
            (
                lambda s: setattr(s.science, "active_opportunity", "regolith_survey"),
                "not ACTIVE",
            ),
            (lambda s: setattr(s.crew[0], "eva_remaining_ticks", 2), "EVA flag"),
        ],
    )
    def test_corrupted_states_are_flagged(
        self, engine: SimulationEngine, mutate: Any, needle: str
    ) -> None:
        state = engine.initial_state(1)
        mutate(state)
        problems = check_state(engine, state)
        assert any(needle in p for p in problems), problems

    def test_transition_invariants(self, engine: SimulationEngine) -> None:
        a = engine.advance(engine.initial_state(1), 130).state
        b = engine.step(a).state
        b.crew[0].dose_msv = a.crew[0].dose_msv - 1.0
        b.tick = a.tick + 2
        problems = check_state(engine, b, previous=a)
        assert any("dose decreased" in p for p in problems)
        assert any("tick went" in p for p in problems)

    def test_regression_battery_never_exceeds_faded_capacity(self) -> None:
        """Bug fixed in Phase 2: capacity fade after the power step left E > capacity."""
        eng = SimulationEngine(
            scenario_variant(lambda d: d["degradation"]["components"][1].update(wear_per_tick=0.01))
        )
        state = eng.initial_state(1)
        state.power.battery_charge_kwh = eng.scenario.power.battery.capacity_kwh
        for _ in range(30):
            nxt = eng.step(state).state
            assert check_state(eng, nxt, previous=state) == []
            state = nxt


class TestFuzz:
    @given(seed=st.integers(0, 2**53 - 1), plan=plans)
    def test_any_decision_sequence_keeps_the_engine_sound(
        self, engine: SimulationEngine, seed: int, plan: dict[int, list[dict[str, Any]]]
    ) -> None:
        initial, final, records = _play(engine, seed, plan)
        # Determinism: the same inputs give the same mission.
        _, again, records2 = _play(engine, seed, plan)
        assert again.state_hash() == final.state_hash()
        assert [r.record_hash for r in records] == [r.record_hash for r in records2]
        # Ledger integrity and replay.
        verify_chain(records)
        res = replay(
            engine,
            initial,
            [ReplayDecision.from_record(r) for r in records],
            final.tick,
            verify_hashes=True,
        )
        assert res.state.state_hash() == final.state_hash()
        # Any fork point reproduces the recorded "state before".
        if records:
            target = records[len(records) // 2]
            fork = plan_fork(records, target.decision_id)
            forked = replay(
                engine,
                initial,
                [ReplayDecision.from_record(r) for r in fork.inherited],
                fork.fork_tick,
            )
            assert forked.state.state_hash() == target.state_before_hash

    @given(
        seed=st.integers(0, 10**9),
        capacity=st.floats(5.0, 2000.0),
        solar=st.floats(0.5, 60.0),
        food=st.floats(0.0, 300.0),
        conductance=st.floats(0.001, 0.2),
        tick_hours=st.sampled_from([0.25, 0.5, 1.0, 2.0, 6.0]),
        fault=st.floats(0.0, 1.0),
        shielding=st.floats(0.0, 1.0),
    )
    def test_parameter_perturbations_keep_states_valid(
        self,
        seed: int,
        capacity: float,
        solar: float,
        food: float,
        conductance: float,
        tick_hours: float,
        fault: float,
        shielding: float,
    ) -> None:
        def mutate(d: dict[str, Any]) -> None:
            d["power"]["battery"]["capacity_kwh"] = capacity
            d["power"]["solar_rated_kw"] = solar
            d["food"]["initial_food_kg"] = food
            d["thermal"]["conductance_kw_per_k"] = conductance
            d["time"]["tick_hours"] = tick_hours
            d["radiation"]["habitat_shielding_factor"] = shielding
            for comp in d["degradation"]["components"]:
                comp["fault_probability_per_tick"] = fault

        eng = SimulationEngine(scenario_variant(mutate))
        _play(
            eng,
            seed,
            {
                0: [{"type": "start_science_activity", "opportunity_id": "regolith_survey"}],
                20: [
                    {
                        "type": "set_subsystem_mode",
                        "subsystem": "oxygen_generation",
                        "mode": "boost",
                    }
                ],
            },
        )
