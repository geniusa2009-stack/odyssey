"""Game domain (pure core + in-memory runtime): Earth Command flow, rules, clock, progression."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from app.game.actions.errors import GameRuleError
from app.game.application.memory import InMemoryGame
from app.game.campaign.campaign import check_can_start, new_campaign
from app.game.content.loader import default_content
from app.game.progression.capabilities import commit_evidence, derive_stages, readiness
from app.game.runtime import clock as clockmod
from app.game.world.state import ClockState

E = "earth.command."
HANGAR_STORAGE = E + "hangar.storage"
LUNA01 = E + "hangar.luna01"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def game(seed: int = 7) -> InMemoryGame:
    return InMemoryGame(default_content(), seed=seed)


async def _to_incident(g: InMemoryGame) -> None:
    await g.act("world.zone_entered", E + "engineering")
    await g.wait(30)


async def _resolve_incident(g: InMemoryGame) -> None:
    await g.act("system.inspect", E + "engineering.power_bus_b")
    await g.act("world.zone_entered", E + "training")
    await g.act("system.set_mode", E + "training.simulator", mode="off")
    await g.act("world.zone_entered", E + "engineering")
    await g.act("repair.perform", E + "engineering.power_bus_b")
    await g.act("mission.clock_set", mode="ACCELERATED")
    for _ in range(4):
        await g.wait(5)


async def _prepare_spacecraft(g: InMemoryGame) -> None:
    await g.act("world.zone_entered", E + "hangar")
    for sub in ("power", "life_support", "comms", "radiation_protection"):
        await g.act("system.inspect", f"{LUNA01}.{sub}")
    await g.act("system.inspect", LUNA01 + ".cargo_hold")
    await g.act(
        "module.install",
        LUNA01,
        slot="radiation_protection",
        item="module.radiation_shelter_liner",
        **{"from": HANGAR_STORAGE},
    )
    await g.act(
        "cargo.transfer",
        LUNA01 + ".cargo_hold",
        item="cargo.water_tank",
        quantity=2,
        **{"from": HANGAR_STORAGE},
    )
    await g.act(
        "cargo.transfer",
        LUNA01 + ".cargo_hold",
        item="spare.habitat_spares_kit",
        quantity=1,
        **{"from": HANGAR_STORAGE},
    )


def _reason(exc: pytest.ExceptionInfo[GameRuleError]) -> str:
    return exc.value.reason


# ------------------------------------------------------------------ Earth Command flow
def test_earth_command_full_flow_transitions_to_luna01() -> None:
    async def scenario() -> None:
        g = game()
        assert g.doc.mission_id == "earth_command.station_readiness"
        assert not g.doc.clock.started
        assert g.doc.clock.pause_reason == "not_started"
        await _to_incident(g)
        assert g.doc.clock.mode == "DECISION_PAUSED"
        assert g.doc.incidents[E + "power_incident"].stage == "active"
        await _resolve_incident(g)
        assert g.doc.incidents[E + "power_incident"].stage == "resolved"
        assert g.doc.objects[LUNA01].access == "inspection_ready"
        await _prepare_spacecraft(g)
        while g.sim.metric("rover.battery_kwh") < 45:
            await g.wait(5)
        result = await g.act("mission.authorize", LUNA01)
        assert result.completion is not None
        assert g.meta.phases["EARTH_COMMAND"] == "completed"
        assert g.meta.phases["LUNA_01"] == "active"
        assert g.doc.mission_id == "luna_01.the_last_light"
        assert "cert.earth_command.station_operations" in g.meta.certifications
        assert g.meta.capabilities["power.load_management"] in {"DISCOVERED", "PROTOTYPE_TESTED"}
        assert g.doc.containers["luna.asteria.lander.cargo_hold"] == {
            "cargo.water_tank": 2,
            "spare.habitat_spares_kit": 1,
        }
        types = [e.type for e in g.events]
        for expected in (
            "incident.started",
            "incident.resolved",
            "cargo.changed",
            "capability.progressed",
            "certification.granted",
            "mission.transitioned",
        ):
            assert expected in types

    run(scenario())


def test_strategies_have_different_costs() -> None:
    """No 'correct answer': repairing immediately without shedding costs station stability
    (the bus is offline during maintenance) while shedding first protects it."""

    async def strategy(shed: bool) -> tuple[bool, str]:
        g = game()
        await _to_incident(g)
        await g.act("system.inspect", E + "engineering.power_bus_b")
        if shed:
            await g.act("world.zone_entered", E + "training")
            await g.act("system.set_mode", E + "training.simulator", mode="off")
            await g.act("world.zone_entered", E + "laboratory")
            await g.act("system.set_mode", E + "laboratory.sample_analyzer", mode="off")
            await g.act("world.zone_entered", E + "engineering")
        await g.act("repair.perform", E + "engineering.power_bus_b")
        await g.act("mission.clock_set", mode="ACCELERATED")
        for _ in range(4):
            await g.wait(5)
        stability = g.sim.state.objectives["station_stability"].status.value
        return "load_shed" in g.doc.incidents[E + "power_incident"].facts, stability

    shed_fact_a, stability_a = run(strategy(shed=False))
    _, stability_b = run(strategy(shed=True))
    assert stability_a == "failed"
    assert stability_b != "failed"
    assert shed_fact_a


def test_incident_is_invisible_before_it_happens() -> None:
    g = game()
    snap = g.snapshot()
    assert snap.world.incidents == []
    dumped = snap.world.model_dump_json() + snap.mission.model_dump_json()
    for secret in ("bus_b_breaker_fault", "power_incident", "seed"):
        assert secret not in dumped
    gate = snap.mission.authorization
    assert gate is not None
    assert {r.id for r in gate.requirements} >= {"station_power_nominal", "spacecraft_charged"}
    assert next(r for r in gate.requirements if r.id == "station_power_nominal").met


# ------------------------------------------------------------------ action validation
def test_actions_are_validated_against_world_state() -> None:
    async def scenario() -> None:
        g = game()
        with pytest.raises(GameRuleError) as exc:
            await g.act("repair.perform", E + "engineering.power_bus_b")
        assert _reason(exc) == "not_at_location"
        await g.act("world.zone_entered", E + "engineering")
        with pytest.raises(GameRuleError) as exc:
            await g.act("repair.perform", E + "engineering.power_bus_b")
        assert _reason(exc) == "fault_not_diagnosed"
        with pytest.raises(GameRuleError) as exc:
            await g.act("system.set_mode", E + "engineering.air_handling", mode="off")
        assert _reason(exc) == "invalid_parameter"
        with pytest.raises(GameRuleError) as exc:
            await g.act("system.set_mode", E + "engineering.air_handling", mode="eco", power=9)
        assert _reason(exc) == "unknown_parameter"
        with pytest.raises(GameRuleError) as exc:
            await g.act("world.zone_entered", E + "airlock")
        assert _reason(exc) == "location_locked"
        with pytest.raises(GameRuleError) as exc:
            await g.act("system.inspect", "earth.command.nowhere")
        assert exc.value.kind == "not_found"
        with pytest.raises(GameRuleError) as exc:
            await g.act("teleport", E + "hangar")
        assert _reason(exc) == "unknown_action"
        with pytest.raises(GameRuleError) as exc:
            await g.act("world.zone_entered", E + "hangar", actor="maya")
        assert exc.value.kind == "invalid"

    run(scenario())


def test_spacecraft_is_restricted_until_station_power_is_restored() -> None:
    async def scenario() -> None:
        g = game()
        await g.act("world.zone_entered", E + "hangar")
        with pytest.raises(GameRuleError) as exc:
            await g.act("system.inspect", LUNA01 + ".power")
        assert _reason(exc) == "spacecraft_not_inspection_ready"
        with pytest.raises(GameRuleError) as exc:
            await g.act(
                "module.install",
                LUNA01,
                slot="radiation_protection",
                item="module.radiation_shelter_liner",
                **{"from": HANGAR_STORAGE},
            )
        assert _reason(exc) == "host_not_accessible"
        with pytest.raises(GameRuleError) as exc:
            await g.act("mission.authorize", LUNA01)
        assert exc.value.details["unmet"]

    run(scenario())


def test_failed_action_leaves_no_partial_state() -> None:
    async def scenario() -> None:
        g = game()
        await _to_incident(g)
        await _resolve_incident(g)
        await g.act("world.zone_entered", E + "hangar")
        before = g.doc.state_hash()
        version = g.version
        with pytest.raises(GameRuleError) as exc:
            await g.act(
                "cargo.transfer",
                LUNA01 + ".cargo_hold",
                item="cargo.water_tank",
                quantity=8,
                **{"from": HANGAR_STORAGE},
            )
        assert _reason(exc) == "insufficient_quantity"
        with pytest.raises(GameRuleError) as exc:
            await g.act(
                "module.install",
                LUNA01,
                slot="external_payload",
                item="module.isru_oxygen_pilot",
                **{"from": HANGAR_STORAGE},
            )
        reasons = {p["reason"] for p in exc.value.details["incompatible"]}
        assert {"mission_rating_mismatch", "module_qualification_missing"} <= reasons
        assert g.doc.state_hash() == before
        assert g.version == version

    run(scenario())


def test_cargo_mass_budget_is_enforced() -> None:
    async def scenario() -> None:
        g = game()
        await _to_incident(g)
        await _resolve_incident(g)
        await g.act("world.zone_entered", E + "hangar")
        hold = LUNA01 + ".cargo_hold"
        await g.act(
            "cargo.transfer", hold, item="cargo.water_tank", quantity=4, **{"from": HANGAR_STORAGE}
        )  # 224 kg
        await g.act(
            "cargo.transfer", hold, item="cargo.food_pack", quantity=6, **{"from": HANGAR_STORAGE}
        )  # +72 kg = 296 kg of 300
        with pytest.raises(GameRuleError) as exc:
            await g.act(
                "cargo.transfer",
                hold,
                item="spare.habitat_spares_kit",
                quantity=1,
                **{"from": HANGAR_STORAGE},
            )
        assert _reason(exc) == "container_mass_limit_exceeded"
        assert exc.value.details["limit_kg"] == 300

    run(scenario())


def test_repeated_discovery_and_sample_do_not_duplicate() -> None:
    async def scenario() -> None:
        g = game()
        await g.act("world.poi_discovered", E + "observation_deck.lunar_telescope")
        version = g.version
        r = await g.act("world.poi_discovered", E + "observation_deck.lunar_telescope")
        assert r.outcome is not None and r.outcome.result == "no_change"
        assert [d.id for d in g.doc.discoveries] == ["discovery.earth.shackleton_rim_illumination"]
        assert g.version == version
        assert "power.polar_illumination" in g.meta.insights

    run(scenario())


def test_repair_consumes_exactly_one_spare() -> None:
    async def scenario() -> None:
        g = game()
        await _to_incident(g)
        locker = E + "engineering.spares_locker"
        assert g.doc.containers[locker]["spare.breaker_module"] == 2
        await g.act("system.inspect", E + "engineering.power_bus_b")
        await g.act("repair.perform", E + "engineering.power_bus_b")
        assert g.doc.containers[locker]["spare.breaker_module"] == 1
        assert len(g.port.decisions) == 1

    run(scenario())


# ------------------------------------------------------------------ clock
def _clock(**kw: Any) -> ClockState:
    base: dict[str, Any] = {
        "realtime_ticks_per_second": 0.2,
        "accelerated_multiplier": 4.0,
        "max_catchup_ticks": 24,
    }
    return ClockState(**(base | kw))


def test_clock_due_ticks_and_no_double_advancement() -> None:
    c = _clock()
    clockmod.start(c, 1000, 0)
    assert clockmod.due_ticks(c, 1000, 0) == 0
    assert clockmod.due_ticks(c, 11_000, 0) == 2
    assert clockmod.due_ticks(c, 11_000, 2) == 0  # already applied: nothing more owed
    clockmod.set_mode(c, "ACCELERATED", 11_000, 2)
    assert clockmod.due_ticks(c, 16_000, 2) == 4
    clockmod.set_mode(c, "PAUSED", 16_000, 6)
    assert clockmod.due_ticks(c, 999_999, 6) == 0


def test_sync_twice_at_same_instant_advances_once() -> None:
    async def scenario() -> None:
        g = game()
        await g.act("world.zone_entered", E + "engineering")
        g.clock.advance(10)
        await g.sync()
        tick = g.sim.tick
        await g.sync()
        assert g.sim.tick == tick == 2

    run(scenario())


def test_unattended_catch_up_is_capped_and_pauses() -> None:
    async def scenario() -> None:
        g = game()
        await g.act("world.zone_entered", E + "engineering")
        await g.wait(30)  # incident pause at tick 5
        await g.act("mission.clock_set", mode="REALTIME")
        await g.wait(10_000)
        assert g.sim.tick == 5 + 24
        assert g.doc.clock.mode == "PAUSED"
        assert g.doc.clock.pause_reason == "unattended_limit"

    run(scenario())


def test_clock_cannot_run_before_the_mission_starts() -> None:
    async def scenario() -> None:
        g = game()
        with pytest.raises(GameRuleError) as exc:
            await g.act("mission.clock_set", mode="REALTIME")
        assert _reason(exc) == "clock_not_started"

    run(scenario())


# ------------------------------------------------------------------ progression and campaign
def test_capability_stages_require_evidence_and_prerequisites() -> None:
    content = default_content()
    # launch readiness evidence alone cannot qualify it: its power prerequisite is missing
    stages = derive_stages(content, ["evidence.transportation.launch_authorized"])
    assert "transportation.crew_launch_readiness" not in stages
    stages = derive_stages(
        content,
        ["evidence.transportation.launch_authorized", "evidence.power.station_incident_resolved"],
    )
    assert stages["transportation.crew_launch_readiness"] == "PROTOTYPE_TESTED"
    # stages are cumulative: later-stage evidence without earlier-stage evidence does nothing
    assert "power.load_management" not in derive_stages(
        content, ["evidence.power.lunar_night_power_managed"]
    )


def test_certification_is_granted_once() -> None:
    content = default_content()
    meta = new_campaign(content)
    ev = ["evidence.power.station_incident_resolved"]
    first = commit_evidence(content, meta, ev, completed_mission="earth_command.station_readiness")
    second = commit_evidence(content, meta, ev, completed_mission="earth_command.station_readiness")
    assert first.certifications == ["cert.earth_command.station_operations"]
    assert second.certifications == [] and second.evidence_added == []
    assert meta.certifications.count("cert.earth_command.station_operations") == 1


def test_mars_stays_locked_with_missing_critical_gates() -> None:
    content = default_content()
    meta = new_campaign(content)
    # grant every non-critical requirement artificially: the profile must stay locked
    for cap in content.content.progression.capabilities:
        meta.capabilities[cap.id] = cap.stages[-1]
    meta.capabilities["transportation.planetary_return"] = "DISCOVERED"
    status = readiness(content, meta, "mars_01_human_mission")
    assert status.locked
    assert status.percent >= 90
    assert status.missing_capability_ids == ["transportation.planetary_return"]
    meta.phases["PATH_TO_MARS"] = "completed"
    with pytest.raises(GameRuleError) as exc:
        check_can_start(content, meta, "luna_01.the_last_light")
    assert exc.value.reason in {"mission_not_available", "mission_already_active"}


def test_campaign_phases_cannot_be_skipped() -> None:
    content = default_content()
    meta = new_campaign(content)
    assert meta.phases["EARTH_COMMAND"] == "available"
    assert all(s == "locked" for p, s in meta.phases.items() if p != "EARTH_COMMAND")
    with pytest.raises(GameRuleError) as exc:
        check_can_start(content, meta, "luna_01.the_last_light")
    assert exc.value.reason == "mission_not_available"
    assert exc.value.details["missing"]["missions"] == ["earth_command.station_readiness"]


def test_unauthored_phase_cannot_start() -> None:
    content = default_content()
    meta = new_campaign(content)
    with pytest.raises(GameRuleError) as exc:
        check_can_start(content, meta, "no.such.mission")
    assert exc.value.kind == "not_found"


def test_runs_are_deterministic_for_the_same_inputs() -> None:
    async def scenario() -> tuple[str, str, int]:
        g = game(seed=11)
        await _to_incident(g)
        await _resolve_incident(g)
        return g.doc.state_hash(), g.meta.state_hash(), g.sim.state.tick

    assert run(scenario()) == run(scenario())
