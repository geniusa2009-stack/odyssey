"""System dependency graph, cascade propagation, alerts (hysteresis) and objectives."""

from __future__ import annotations

import itertools
from collections import deque
from typing import Any

import pytest

from app.simulation.domain.enums import AlertSeverity, EventKind, ObjectiveStatus
from app.simulation.engine.context import RunOptions, TickContext
from app.simulation.engine.dependency_graph import DependencyGraph
from app.simulation.engine.engine import SimulationEngine
from app.simulation.engine.metrics import SeveritySpec, UnknownMetricError
from app.simulation.engine.mission_logic import evaluate_alerts, evaluate_cascades
from tests.helpers import consumer, quiet, scenario_variant


def _path_exists(graph: DependencyGraph, src: str, dst: str) -> bool:
    seen, queue = {src}, deque([src])
    while queue:
        node = queue.popleft()
        if node == dst:
            return True
        for edge in graph.children(node):
            if edge.target not in seen:
                seen.add(edge.target)
                queue.append(edge.target)
    return False


class TestDependencyGraph:
    def test_every_node_is_a_known_metric(self, engine: SimulationEngine) -> None:
        for node in engine.graph.nodes():
            assert engine.metrics.has(node)

    def test_edges_are_unique_and_explained(self, engine: SimulationEngine) -> None:
        keys = [e.key for e in engine.graph.edges]
        assert len(keys) == len(set(keys))
        assert all(e.mechanism for e in engine.graph.edges)

    def test_specified_conceptual_chain(self, engine: SimulationEngine) -> None:
        """solar → power → thermal → life support → water recovery → crew → mission risk."""
        g = engine.graph
        chain = [
            "env.solar_availability",
            "power.generation_ratio",
            "power.battery_soc",
            "power.supply_ratio.thermal_heater",
            "thermal.habitat_temp_c",
            "life_support.water_recovery_efficiency",
            "life_support.water_days",
            "crew.min_health",
            "risk.mission",
        ]
        for a, b in itertools.pairwise(chain):
            assert any(e.target == b for e in g.children(a)), f"missing edge {a} -> {b}"
        assert _path_exists(g, "env.solar_availability", "risk.mission")

    def test_controls_and_environment_are_roots(self, engine: SimulationEngine) -> None:
        for node in engine.graph.nodes():
            if DependencyGraph.is_root_namespace(node):
                assert engine.graph.parents(node) == []

    def test_graph_is_acyclic(self, engine: SimulationEngine) -> None:
        g = engine.graph
        indegree = {n: len(g.parents(n)) for n in g.nodes()}
        queue = deque(n for n, d in indegree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for edge in g.children(node):
                indegree[edge.target] -= 1
                if indegree[edge.target] == 0:
                    queue.append(edge.target)
        assert visited == len(indegree)


class TestMetrics:
    def test_severity_mapping(self) -> None:
        below = SeveritySpec("below", nominal=0.4, critical=0.0)
        assert below.severity(0.5) == 0.0
        assert below.severity(0.2) == pytest.approx(0.5)
        assert below.severity(-1) == 1.0
        above = SeveritySpec("above", nominal=5000, critical=10000)
        assert above.severity(7500) == pytest.approx(0.5)
        assert SeveritySpec("above", 1, 1).severity(3) == 0.0

    def test_unknown_metric(self, engine: SimulationEngine, initial: Any) -> None:
        with pytest.raises(UnknownMetricError):
            engine.metrics.value("power.nonexistent", initial)

    def test_risk_is_bounded_and_rises_with_degradation(self, engine: SimulationEngine) -> None:
        state = engine.initial_state(1)
        nominal = engine.metrics.value("risk.mission", state)
        state.life_support.oxygen_kg = 0.0
        degraded = engine.metrics.value("risk.mission", state)
        assert 0.0 <= nominal < degraded <= 1.0

    def test_frame_covers_all_metrics(self, engine: SimulationEngine, initial: Any) -> None:
        frame = engine.metric_frame(initial)
        assert set(frame) == set(engine.metrics.names())


class TestAlerts:
    def test_raise_update_and_clear_with_hysteresis(self, engine: SimulationEngine) -> None:
        st = engine.initial_state(1)
        ctx = TickContext(engine.scenario, engine.metrics, st, RunOptions(), 0)
        cap = engine.scenario.power.battery.capacity_kwh
        st.power.battery_charge_kwh = cap * 0.25
        evaluate_alerts(ctx)
        assert "battery_low" in st.alerts
        assert st.alerts["battery_low"].severity == AlertSeverity.WARNING
        st.power.battery_charge_kwh = cap * 0.32  # above threshold, below clear level
        evaluate_alerts(ctx)
        assert "battery_low" in st.alerts
        assert st.alerts["battery_low"].value == pytest.approx(0.32)
        st.power.battery_charge_kwh = cap * 0.36
        evaluate_alerts(ctx)
        assert "battery_low" not in st.alerts
        kinds = [(e.kind, e.key) for e in ctx.events]
        assert kinds == [
            (EventKind.RESOURCE_WARNING, "battery_low"),
            (EventKind.ALERT_CLEARED, "battery_low"),
        ]


class TestCascades:
    def test_cascade_warning_on_degraded_chain_then_quiet(self, engine: SimulationEngine) -> None:
        st = engine.initial_state(1)
        ctx = TickContext(engine.scenario, engine.metrics, st, RunOptions(), 0)
        cap = engine.scenario.power.battery.capacity_kwh
        st.power.generation_kw = engine.scenario.power.solar_rated_kw  # isolate the battery
        st.power.battery_charge_kwh = cap * 0.05  # battery severity 1.0
        st.power.consumers["thermal_heater"].supply_ratio = 0.2  # downstream degraded
        evaluate_cascades(ctx, engine.graph)
        warnings = [e for e in ctx.events if e.kind == EventKind.CASCADE_WARNING]
        assert [w.key for w in warnings] == ["cascade:power.battery_soc"]
        targets = {t["target"] for t in warnings[0].data["targets"]}
        assert "power.supply_ratio.thermal_heater" in targets
        assert "power.battery_soc->power.supply_ratio.thermal_heater" in st.cascade_edges_active
        evaluate_cascades(ctx, engine.graph)  # same edges still active → no repeat warning
        assert len([e for e in ctx.events if e.kind == EventKind.CASCADE_WARNING]) == 1

    def test_power_loss_propagates_to_life_support_and_crew(self) -> None:
        """End-to-end cascade: no generation → battery empty → load shed → CO2 → crew."""

        def mutate(d: dict[str, Any]) -> None:
            quiet(d)
            d["environment"]["solar_availability"] = [{"tick": 0, "value": 0.0}]
            d["power"]["battery"]["initial_soc"] = 0.15
            consumer(d, "co2_scrubber")["priority"] = 7  # first to be shed

        eng = SimulationEngine(scenario_variant(mutate))
        out = eng.advance(eng.initial_state(1), 120)
        sources = {e.data["source"] for e in out.events if e.kind == EventKind.CASCADE_WARNING}
        assert "power.battery_soc" in sources
        alerts = {
            e.key
            for e in out.events
            if e.kind in (EventKind.RESOURCE_WARNING, EventKind.ALERT_RAISED)
        }
        assert {"battery_low", "load_shedding", "co2_high"} <= alerts
        assert eng.metrics.value("crew.min_health", out.state) < 1.0


class TestObjectives:
    def test_threshold_objective_achieved_once(self, engine: SimulationEngine) -> None:
        st = engine.initial_state(1)
        st.science.points = 101.0  # science_quality: science.points >= 100
        out = engine.step(st)
        assert out.state.objectives["science_quality"].status == ObjectiveStatus.ACHIEVED
        assert out.state.objectives["science_quality"].resolved_tick == 0
        assert len([e for e in out.events if e.key == "science_quality"]) == 1
        again = engine.step(out.state)
        assert not [e for e in again.events if e.key == "science_quality"]

    def test_at_end_objective_resolved_only_at_end(self, engine: SimulationEngine) -> None:
        mid = engine.advance(engine.initial_state(1), 100).state
        assert mid.objectives["reserves_at_end"].status == ObjectiveStatus.PENDING
        end = engine.advance(mid, 500).state
        assert end.objectives["reserves_at_end"].status != ObjectiveStatus.PENDING
