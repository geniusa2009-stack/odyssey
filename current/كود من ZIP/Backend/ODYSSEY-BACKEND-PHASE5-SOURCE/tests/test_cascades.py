"""Cascade and causal-trace validation on multi-system failures.

For each scenario below a cascade is *forced* through scenario data or decisions, then checked
against the recorded per-tick history:

* every cascade warning names a real dependency edge whose source and target severities, read
  back from the state at that tick, really are past the thresholds;
* traces are acyclic, follow declared edges, and causes never start after their effects;
* traces and counterfactual verdicts are stable across runs and agree with an independent
  re-run without the decision.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.simulation.analysis.reconstruct import counterfactual_factory, reconstruct
from app.simulation.analysis.root_cause import RootCauseTrace, trace_root_cause
from app.simulation.domain.enums import EventKind
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.replay import ReplayDecision, replay
from app.simulation.scenarios.loader import get_scenario
from tests.helpers import Plan, consumer, play, quiet, scenario_variant


def _night(d: dict[str, Any]) -> None:
    quiet(d)
    d["environment"]["solar_availability"] = [{"tick": 0, "value": 0.0}]
    d["power"]["battery"]["initial_soc"] = 0.25


def _deep_cold(d: dict[str, Any]) -> None:
    quiet(d)
    d["environment"]["sink_temp_c"] = [{"tick": 0, "value": -185.0}]
    d["thermal"]["initial_temp_c"] = 12.0
    d["thermal"]["internal_heat_fraction"] = 0.2


def _thirsty(d: dict[str, Any]) -> None:
    quiet(d)
    d["life_support"]["initial_water_kg"] = 12.0
    d["life_support"]["initial_oxygen_kg"] = 4.0


def _pump(d: dict[str, Any]) -> None:
    quiet(d)
    d["events"] = [
        {
            "id": "pump_fault",
            "kind": "system_fault",
            "message_key": "event.pump",
            "trigger": {"type": "scheduled", "at_tick": 5},
            "effects": [
                {"type": "damage_component", "component": "water_processor", "amount": 0.9}
            ],
        }
    ]


def _storm(d: dict[str, Any]) -> None:
    quiet(d)
    d["events"] = [
        {
            "id": "storm",
            "kind": "space_weather",
            "message_key": "event.storm",
            "trigger": {"type": "scheduled", "at_tick": 3},
            "effects": [
                {
                    "type": "modifier",
                    "target": "env.radiation_dose_rate_msv_h",
                    "op": "multiply",
                    "value": 200.0,
                    "duration_ticks": 30,
                }
            ],
        }
    ]


def _comms_last(d: dict[str, Any]) -> None:
    _night(d)
    consumer(d, "comms")["priority"] = 9


# name → (scenario mutation, decision plan, target metric, metrics that must appear on a chain)
CASES: dict[str, tuple[Callable[[dict[str, Any]], None], Plan, str, set[str]]] = {
    "night_power_to_water": (
        _night,
        {},
        "life_support.water_recovery_efficiency",
        {"power.generation_ratio", "power.supply_ratio.water_recovery"},
    ),
    "heater_off_to_water_recovery": (
        _deep_cold,
        {1: [{"type": "set_subsystem_mode", "subsystem": "thermal_heater", "mode": "off"}]},
        "life_support.water_recovery_efficiency",
        {"control.mode.thermal_heater", "thermal.habitat_temp_c"},
    ),
    "power_to_comms": (_comms_last, {}, "comms.link_up", {"power.supply_ratio.comms"}),
    "water_to_oxygen_to_crew": (
        _thirsty,
        {1: [{"type": "set_subsystem_mode", "subsystem": "water_recovery", "mode": "off"}]},
        "crew.min_health",
        {"life_support.water_days", "life_support.o2_generation_ratio"},
    ),
    "pump_fault_to_water": (
        _pump,
        {},
        "life_support.water_days",
        {"life_support.water_recovery_efficiency", "component.water_processor.health"},
    ),
    "storm_to_crew": (
        _storm,
        {},
        "crew.min_health",
        {"env.radiation_dose_rate_msv_h", "crew.received_dose_rate_msv_h"},
    ),
}


def _run(name: str) -> tuple[SimulationEngine, Any, Any, RootCauseTrace]:
    mutate, plan, target, _ = CASES[name]
    eng = SimulationEngine(scenario_variant(mutate))
    played = play(eng, 7, plan, 120)
    record = reconstruct(eng, played.initial, played.records, played.final.tick)
    sev = [eng.metrics.severity(target, s) for s in record.history]
    tick = record.history[max(range(len(sev)), key=lambda i: (sev[i], -i))].tick
    cf = counterfactual_factory(eng, played.initial, played.records, played.final.tick)
    trace = trace_root_cause(
        eng, record.history, target, tick, decision_info=record.decision_info(), counterfactual=cf
    )
    return eng, played, record, trace


@pytest.mark.parametrize("name", sorted(CASES))
class TestMultiSystemCascades:
    def test_trace_reaches_through_the_expected_systems(self, name: str) -> None:
        _, _, _, trace = _run(name)
        on_chains = {n.removeprefix("metric:") for chain in trace.chains for n in chain}
        assert trace.target_severity > 0.2
        assert CASES[name][3] <= on_chains, (CASES[name][3] - on_chains, trace.chains)

    def test_trace_is_acyclic_ordered_and_declared(self, name: str) -> None:
        eng, _, _, trace = _run(name)
        declared = {(f"metric:{e.source}", f"metric:{e.target}") for e in eng.graph.edges}
        nodes = {n.id: n for n in trace.nodes}
        for chain in trace.chains:
            assert len(chain) == len(set(chain)), f"cycle in {chain}"
            assert chain[-1] == f"metric:{trace.target_metric}"
        for e in trace.edges:
            if e.source.startswith("metric:"):
                assert (e.source, e.target) in declared
                assert e.evidence["source_onset_tick"] <= e.evidence["target_anchor_tick"]
            src, dst = nodes[e.source], nodes[e.target]
            if (
                not (
                    e.source.startswith("metric:") and src.tick is not None and dst.tick is not None
                )
                or dst.id == f"metric:{trace.target_metric}"
            ):
                continue
            # A cause starts no later than its effect's onset — or, for an effect already
            # degraded at the start of the record, no later than the effect's worst point.
            initial = f"scenario:initial:{dst.metric}" in nodes
            limit = dst.worst_tick if initial and dst.worst_tick is not None else dst.tick
            assert src.tick <= limit, (e.source, e.target)

    def test_cascade_warnings_match_recorded_state(self, name: str) -> None:
        eng, _, record, _ = _run(name)
        an = eng.scenario.analysis
        edges = {(e.source, e.target) for e in eng.graph.system_edges()}
        warnings = [e for e in record.events if e.kind == EventKind.CASCADE_WARNING]
        for w in warnings:
            after = record.history[w.tick + 1 - record.history[0].tick]  # state after that step
            source = w.data["source"]
            assert eng.metrics.severity(source, after) >= an.cascade_parent_threshold - 1e-9
            for t in w.data["targets"]:
                assert (source, t["target"]) in edges
                assert eng.metrics.severity(t["target"], after) >= an.cascade_child_threshold - 1e-9

    def test_trace_is_stable(self, name: str) -> None:
        assert _run(name)[3].model_dump(mode="json") == _run(name)[3].model_dump(mode="json")

    def test_counterfactual_verdicts_match_independent_replay(self, name: str) -> None:
        eng, played, _, trace = _run(name)
        for node in trace.nodes:
            cf = node.details.get("counterfactual")
            if node.kind != "decision" or not cf:
                continue
            kept = [
                ReplayDecision.from_record(r) for r in played.records if r.decision_id != node.ref
            ]
            alt = replay(
                eng, played.initial, kept, trace.target_tick, record_history=True, skip_invalid=True
            )
            value = eng.metrics.value(trace.target_metric, alt.history[-1])
            assert value == pytest.approx(cf["without_decision_value"])


def test_decision_cascade_blames_the_decision() -> None:
    """Heater off → cold habitat → water processor degraded: the decision is the verified root."""
    _, played, _, trace = _run("heater_off_to_water_recovery")
    roots = [n for n in trace.nodes if n.id in trace.roots and n.kind == "decision"]
    assert roots, trace.roots
    assert roots[0].ref == played.records[0].decision_id
    assert roots[0].details["counterfactual"]["verdict"] == "decision_worsened_target"
    assert roots[0].details["decision_type"] == "set_subsystem_mode"


def test_initial_condition_does_not_hide_a_later_decision() -> None:
    """Regression (Phase 2): resources low from the start used to mask the decision."""
    _, played, _, trace = _run("water_to_oxygen_to_crew")
    decision = f"decision:{played.records[0].decision_id}"
    assert decision in trace.roots
    assert "scenario:initial:life_support.water_days" in trace.roots
    assert any(
        c[0] == decision and "metric:life_support.o2_generation_ratio" in c for c in trace.chains
    )


def test_acute_radiation_death_is_attributed() -> None:
    """Regression (Phase 2): dose *rate* harms the crew; the graph now carries that edge."""
    _, _, _, trace = _run("storm_to_crew")
    assert trace.roots == ["event:storm"]
    assert [
        "event:storm",
        "metric:env.radiation_dose_rate_msv_h",
        "metric:crew.received_dose_rate_msv_h",
        "metric:crew.min_health",
    ] in trace.chains


def test_harmless_flare_is_not_blamed_for_crew_loss() -> None:
    """Regression (Phase 2): a flare below the acute harm threshold must not be a cause."""
    from app.simulation.analysis.black_box import build_black_box

    eng = SimulationEngine(get_scenario("luna-01"))
    played = play(
        eng,
        42,
        {5: [{"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "off"}]},
        400,
    )
    record = reconstruct(eng, played.initial, played.records, played.final.tick)
    assert any(e.key == "minor_flare" for e in record.events)  # the flare did happen
    trace = build_black_box(eng, record).causal_traces[0]
    assert trace.target_metric == "crew.min_health"
    assert not [r for r in trace.roots if r.startswith("event:minor_flare")]
    assert [r for r in trace.roots if r.startswith("decision:")]


def test_natural_cascade_has_no_decision_roots() -> None:
    """No decisions were made: the trace must not invent one."""
    _, _, _, trace = _run("pump_fault_to_water")
    assert not [n for n in trace.nodes if n.kind == "decision"]
    assert "event:pump_fault" in trace.roots
