"""Resource calculations: each system checked against its documented equations."""

from __future__ import annotations

from typing import Any

import pytest

from app.simulation.domain.enums import CrewLocation, EventKind, RoverStatus, SubsystemMode
from app.simulation.domain.state import MissionState
from app.simulation.engine.context import RunOptions, TickContext
from app.simulation.engine.engine import SimulationEngine
from app.simulation.systems import (
    comms_science,
    crew,
    degradation,
    environment,
    life_support,
    power,
    thermal,
)
from tests.helpers import component, quiet, scenario_variant


@pytest.fixture(scope="module")
def qengine() -> SimulationEngine:
    """LUNA-01 with events, random faults and rover loss removed."""
    return SimulationEngine(scenario_variant(quiet))


def ctx_for(engine: SimulationEngine, state: MissionState) -> TickContext:
    return TickContext(
        scenario=engine.scenario,
        metrics=engine.metrics,
        state=state,
        options=RunOptions(),
        tick=state.tick,
    )


class TestEnvironment:
    def test_keyframe_interpolation(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        st.tick = 56  # halfway between (40, 0.85) and (72, 0.55)
        environment.update(ctx_for(qengine, st))
        assert st.environment.solar_availability == pytest.approx(0.70)

    def test_modifiers_apply_in_order_and_expire(self, qengine: SimulationEngine) -> None:
        from app.simulation.domain.state import ActiveModifier

        st = qengine.initial_state(1)
        st.modifiers = [
            ActiveModifier(
                event_id="b",
                target="env.radiation_dose_rate_msv_h",
                op="add",
                value=1.0,
                start_tick=0,
                end_tick=2,
            ),
            ActiveModifier(
                event_id="a",
                target="env.radiation_dose_rate_msv_h",
                op="multiply",
                value=10.0,
                start_tick=0,
                end_tick=5,
            ),
        ]
        environment.update(ctx_for(qengine, st))
        # sorted by (start_tick, event_id): multiply first, then add
        assert st.environment.radiation_dose_rate_msv_h == pytest.approx(0.057 * 10 + 1.0)
        st.tick = 3
        environment.update(ctx_for(qengine, st))
        assert [m.event_id for m in st.modifiers] == ["a"]
        assert st.environment.radiation_dose_rate_msv_h == pytest.approx(0.57)

    def test_solar_clamped(self, qengine: SimulationEngine) -> None:
        from app.simulation.domain.state import ActiveModifier

        st = qengine.initial_state(1)
        st.modifiers = [
            ActiveModifier(
                event_id="x",
                target="env.solar_availability",
                op="multiply",
                value=5.0,
                start_tick=0,
                end_tick=9,
            )
        ]
        environment.update(ctx_for(qengine, st))
        assert st.environment.solar_availability == 1.0


class TestPower:
    def test_generation_formula(self, qengine: SimulationEngine) -> None:
        sc = qengine.scenario
        st = qengine.initial_state(1)
        ctx = ctx_for(qengine, st)
        environment.update(ctx)
        power.update(ctx)
        dust = 1.0 - sc.power.dust_deposition_per_tick
        solar_perf = 1.0  # health 1
        expected = sc.power.solar_rated_kw * 0.85 * dust * solar_perf
        assert st.power.generation_kw == pytest.approx(expected)
        assert st.power.dust_factor == pytest.approx(dust)

    def test_priority_allocation_sheds_lowest_priority_first(
        self, qengine: SimulationEngine
    ) -> None:
        st = qengine.initial_state(1)
        st.environment.solar_availability = 0.0
        st.power.battery_charge_kwh = 0.5  # ~0.475 kW deliverable over one hour
        ctx = ctx_for(qengine, st)
        st.environment.sink_temp_c = -45.0
        power.update(ctx)
        cons = st.power.consumers
        assert cons["habitat_core"].supply_ratio < 1.0  # priority 0 gets everything there is
        for low in ("co2_scrubber", "oxygen_generation", "water_recovery", "comms"):
            assert cons[low].allocated_kw == 0.0
        assert st.power.unmet_kw > 0
        assert st.power.battery_charge_kwh == pytest.approx(0.0, abs=1e-9)

    def test_battery_discharge_uses_efficiency(self, qengine: SimulationEngine) -> None:
        sc = qengine.scenario
        st = qengine.initial_state(1)
        st.environment.solar_availability = 0.0
        e0 = st.power.battery_charge_kwh
        power.update(ctx_for(qengine, st))
        drawn_kw = st.power.allocated_kw
        expected = e0 - drawn_kw / sc.power.battery.discharge_efficiency * sc.time.tick_hours
        assert st.power.battery_charge_kwh == pytest.approx(expected)
        assert st.power.battery_net_kw == pytest.approx(
            -drawn_kw / sc.power.battery.discharge_efficiency
        )

    def test_battery_charging_limited_by_rate_and_capacity(self, qengine: SimulationEngine) -> None:
        sc = qengine.scenario
        st = qengine.initial_state(1)
        st.environment.solar_availability = 1.0
        st.power.battery_charge_kwh = sc.power.battery.capacity_kwh - 0.1
        power.update(ctx_for(qengine, st))
        assert st.power.battery_charge_kwh == pytest.approx(sc.power.battery.capacity_kwh)
        st.power.battery_charge_kwh = 10.0
        power.update(ctx_for(qengine, st))
        assert st.power.battery_net_kw <= sc.power.battery.max_charge_kw + 1e-9

    def test_degraded_battery_has_less_capacity(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        st.components["battery"].health = 0.5
        power.update(ctx_for(qengine, st))
        assert st.power.battery_charge_kwh <= qengine.scenario.power.battery.capacity_kwh * 0.5

    def test_science_and_rover_loads_only_when_active(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        power.update(ctx_for(qengine, st))
        assert st.power.consumers["science_payload"].demand_kw == 0.0
        assert st.power.consumers["rover_charger"].demand_kw > 0  # rover not full
        st.rover.battery_kwh = qengine.scenario.rover.battery_capacity_kwh
        power.update(ctx_for(qengine, st))
        assert st.power.consumers["rover_charger"].demand_kw == 0.0

    def test_rover_energy_transfer_feeds_bus(self, qengine: SimulationEngine) -> None:
        sc = qengine.scenario
        st = qengine.initial_state(1)
        st.environment.solar_availability = 0.0
        st.rover.transfer_active = True
        r0 = st.rover.battery_kwh
        power.update(ctx_for(qengine, st))
        assert st.rover.battery_kwh == pytest.approx(r0 - sc.rover.transfer_kw)
        st.rover.battery_kwh = 1.0
        power.update(ctx_for(qengine, st))
        assert st.rover.battery_kwh == 0.0 and st.rover.transfer_active is False


class TestThermalAndLifeSupport:
    def test_lumped_thermal_equation(self, qengine: SimulationEngine) -> None:
        th = qengine.scenario.thermal
        st = qengine.initial_state(1)
        st.environment.sink_temp_c = -100.0
        st.thermal.habitat_temp_c = 18.0
        st.thermal.setpoint_c = 25.0  # stays below setpoint → no overheat relaxation
        st.power.allocated_kw = 3.0
        st.power.consumers["thermal_heater"].allocated_kw = 1.0
        thermal.update(ctx_for(qengine, st))
        q_int = th.internal_heat_fraction * 2.0
        q_loss = th.conductance_kw_per_k * (18.0 + 100.0)
        expected = 18.0 + (1.0 + q_int - q_loss) / th.capacitance_kwh_per_k
        assert st.thermal.habitat_temp_c == pytest.approx(expected)

    def test_overheat_relaxes_toward_setpoint(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        st.thermal.habitat_temp_c = 30.0
        st.thermal.setpoint_c = 21.0
        st.power.allocated_kw = 10.0
        thermal.update(ctx_for(qengine, st))
        assert 21.0 <= st.thermal.habitat_temp_c <= 29.0

    def test_crew_resource_consumption(self, qengine: SimulationEngine) -> None:
        ls = qengine.scenario.life_support
        st = qengine.initial_state(1)
        for c in st.power.consumers.values():
            c.supply_ratio = 0.0  # nothing powered: pure consumption
        o2, food = st.life_support.oxygen_kg, st.food.food_kg
        life_support.update(ctx_for(qengine, st))
        assert st.life_support.oxygen_kg == pytest.approx(
            o2 - 4 * ls.o2_consumption_kg_per_crew_day / 24
        )
        assert st.food.food_kg == pytest.approx(
            food - 4 * qengine.scenario.food.consumption_kg_per_crew_day / 24
        )
        assert st.life_support.water_recovered_kg == 0.0
        assert st.life_support.co2_removed_kg == 0.0

    def test_cold_degrades_water_recovery(self, qengine: SimulationEngine) -> None:
        ls = qengine.scenario.life_support
        warm = qengine.initial_state(1)
        life_support.update(ctx_for(qengine, warm))
        assert warm.life_support.water_recovery_efficiency == pytest.approx(
            ls.water_recovery_nominal
        )
        cold = qengine.initial_state(1)
        cold.thermal.habitat_temp_c = 5.0  # halfway between zero (0 °C) and min (10 °C)
        life_support.update(ctx_for(qengine, cold))
        assert cold.life_support.water_recovery_efficiency == pytest.approx(
            ls.water_recovery_nominal * 0.5
        )

    def test_electrolysis_consumes_water(self, qengine: SimulationEngine) -> None:
        ls = qengine.scenario.life_support
        st = qengine.initial_state(1)
        st.life_support.oxygen_kg = 0.0  # plenty of storage headroom
        life_support.update(ctx_for(qengine, st))
        gen = st.life_support.o2_generated_kg
        assert gen == pytest.approx(ls.o2_generation_capacity_kg_per_hour)
        used = 4 * ls.water_use_kg_per_crew_day / 24
        expected_water = (
            ls.initial_water_kg - used + used * ls.water_recovery_nominal - gen * ls.water_per_kg_o2
        )
        assert st.life_support.water_kg == pytest.approx(expected_water)

    def test_no_water_means_no_oxygen(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        st.life_support.water_kg = 0.0
        life_support.update(ctx_for(qengine, st))
        assert st.life_support.o2_generated_kg == 0.0

    def test_scrubber_floor(self, qengine: SimulationEngine) -> None:
        ls = qengine.scenario.life_support
        st = qengine.initial_state(1)
        st.life_support.co2_kg = ls.co2_floor_kg
        st.power.consumers["co2_scrubber"].mode = SubsystemMode.BOOST
        life_support.update(ctx_for(qengine, st))
        assert st.life_support.co2_kg >= ls.co2_floor_kg - 1e-12


class TestCrew:
    def test_shielding_by_location(self, qengine: SimulationEngine) -> None:
        rad = qengine.scenario.radiation
        st = qengine.initial_state(1)
        st.environment.radiation_dose_rate_msv_h = 1.0
        st.crew[0].location = CrewLocation.SHELTER
        crew.update(ctx_for(qengine, st))
        assert st.crew[0].dose_msv == pytest.approx(rad.shelter_shielding_factor)
        assert st.crew[1].dose_msv == pytest.approx(rad.habitat_shielding_factor)

    def test_health_penalty_and_recovery(self, qengine: SimulationEngine) -> None:
        ch = qengine.scenario.crew_health
        st = qengine.initial_state(1)
        st.crew[0].health = 0.5
        crew.update(ctx_for(qengine, st))
        assert st.crew[0].health == pytest.approx(0.5 + ch.recovery_per_tick)
        st.food.food_kg = 0.0
        crew.update(ctx_for(qengine, st))
        assert st.crew[0].health == pytest.approx(
            0.5 + ch.recovery_per_tick - ch.starvation_penalty_per_tick
        )

    def test_incapacitation_emits_event_once(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        st.crew[0].health = 0.001
        st.life_support.water_kg = 0.0
        ctx = ctx_for(qengine, st)
        crew.update(ctx)
        crew.update(ctx)
        hits = [e for e in ctx.events if e.key == "crew_incapacitated:crew_cdr"]
        assert len(hits) == 1 and st.crew[0].health == 0.0


class TestCommsDegradation:
    def test_link_needs_geometry_and_power(self, qengine: SimulationEngine) -> None:
        st = qengine.initial_state(1)
        st.science.data_pending_mb = 500.0
        ctx = ctx_for(qengine, st)
        comms_science.update_comms(ctx)
        assert st.comms.link_up and st.comms.data_downlinked_mb == pytest.approx(120.0)
        st.environment.earth_visible = False
        comms_science.update_comms(ctx)
        assert not st.comms.link_up
        assert [e.key for e in ctx.events] == ["link_lost"]

    def test_boost_accelerates_wear(self, qengine: SimulationEngine) -> None:
        spec = qengine.scenario.component("oxygen_generator")
        st = qengine.initial_state(1)
        degradation.update(ctx_for(qengine, st))
        nominal_wear = 1.0 - st.components["oxygen_generator"].health
        st2 = qengine.initial_state(1)
        st2.power.consumers["oxygen_generation"].mode = SubsystemMode.BOOST
        degradation.update(ctx_for(qengine, st2))
        boosted_wear = 1.0 - st2.components["oxygen_generator"].health
        assert nominal_wear == pytest.approx(spec.wear_per_tick)
        assert boosted_wear == pytest.approx(spec.wear_per_tick * spec.boost_wear_multiplier)

    def test_seeded_faults_are_reproducible(self) -> None:
        def mutate(d: dict[str, Any]) -> None:
            quiet(d)
            component(d, "radio")["fault_probability_per_tick"] = 1.0

        eng = SimulationEngine(scenario_variant(mutate))
        st = eng.initial_state(9)
        st.components["radio"].health = 0.5
        ctx = ctx_for(eng, st)
        degradation.update(ctx)
        faults = [e for e in ctx.events if e.kind == EventKind.SYSTEM_FAULT]
        assert faults and st.components["radio"].fault_count == 1
        assert st.components["radio"].last_damage is not None
        assert st.components["radio"].last_damage.ref.startswith("fault:radio:")


class TestEvents:
    def test_scheduled_modifier_event_applies_same_tick(self, engine: SimulationEngine) -> None:
        out = engine.advance(engine.initial_state(42), 123)
        spe = [e for e in out.events if e.key == "solar_particle_event"]
        assert len(spe) == 1 and spe[0].tick == 122
        assert spe[0].data["effects"][0]["value"] == 40.0
        assert spe[0].data["evidence"] == ["donki_sep_events"]
        assert out.state.environment.radiation_dose_rate_msv_h == pytest.approx(0.057 * 40)

    def test_state_triggered_event(self) -> None:
        def mutate(d: dict[str, Any]) -> None:
            quiet(d)
            d["events"] = [
                {
                    "id": "freeze",
                    "kind": "system_fault",
                    "message_key": "event.freeze",
                    "trigger": {
                        "type": "state",
                        "condition": {"metric": "thermal.habitat_temp_c", "op": "<", "value": 3.0},
                    },
                    "effects": [
                        {"type": "damage_component", "component": "water_processor", "amount": 0.25}
                    ],
                }
            ]

        eng = SimulationEngine(scenario_variant(mutate))
        st = eng.initial_state(1)
        assert eng.step(st).state.components["water_processor"].health > 0.99
        st.thermal.habitat_temp_c = 1.0
        out = eng.advance(st, 3)
        fired = [e for e in out.events if e.key == "freeze"]
        assert len(fired) == 1  # max_fires = 1
        wp = out.state.components["water_processor"]
        assert wp.last_damage is not None and wp.last_damage.ref == "freeze"

    def test_random_event_is_seeded(self) -> None:
        def mutate(d: dict[str, Any]) -> None:
            quiet(d)
            d["events"] = [
                {
                    "id": "flare",
                    "kind": "space_weather",
                    "message_key": "event.flare",
                    "trigger": {"type": "random", "probability_per_tick": 0.2},
                    "effects": [],
                    "max_fires": 100,
                }
            ]

        eng = SimulationEngine(scenario_variant(mutate))
        ticks = [
            [e.tick for e in eng.advance(eng.initial_state(s), 100).events if e.key == "flare"]
            for s in (1, 1, 2)
        ]
        assert ticks[0] == ticks[1] and ticks[0] != ticks[2]
        assert 8 < len(ticks[0]) < 35

    def test_decision_triggered_event(self, engine: SimulationEngine) -> None:
        from app.simulation.domain.decisions import parse_decision
        from app.simulation.domain.enums import OpportunityStatus, ProvenanceKind
        from app.simulation.domain.state import OpportunityState, Provenance

        st = engine.initial_state(1)
        st.science.opportunities["far_crater_traverse"] = OpportunityState(
            id="far_crater_traverse",
            status=OpportunityStatus.OPEN,
            opened_tick=0,
            closes_tick=50,
            opened_by=Provenance(kind=ProvenanceKind.EVENT, ref="t", tick=0),
        )
        res = engine.apply_decision(
            st,
            parse_decision(
                {
                    "type": "rover_command",
                    "action": "traverse",
                    "opportunity_id": "far_crater_traverse",
                }
            ),
            "dec1",
        )
        fired = [e for e in res.events if e.key == "rover_departure"]
        assert fired and fired[0].data["trigger"] == {"type": "decision", "decision_id": "dec1"}
        assert res.state.rover.status == RoverStatus.TRAVERSING
