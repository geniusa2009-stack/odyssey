"""Black Box reconstruction, root-cause traces, engineering profile and Mission DNA."""

from __future__ import annotations

import re

import pytest

from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.mission_dna import build_mission_dna, dna_similarity
from app.simulation.analysis.profile import (
    DIMENSIONS,
    ProfileWeights,
    build_profile,
    default_weights,
)
from app.simulation.analysis.reconstruct import (
    MissionRecord,
    counterfactual_factory,
    reconstruct,
)
from app.simulation.analysis.root_cause import trace_root_cause
from app.simulation.engine.engine import SimulationEngine
from app.simulation.engine.metrics import UnknownMetricError
from tests.helpers import PlayedMission, play

FAILING_PLAN = {5: [{"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "off"}]}
GOOD_PLAN = {
    15: [{"type": "start_science_activity", "opportunity_id": "regolith_survey"}],
    121: [{"type": "set_crew_location", "location": "shelter"}],
    131: [{"type": "set_crew_location", "location": "habitat"}],
}


@pytest.fixture(scope="module")
def failing(engine: SimulationEngine) -> tuple[PlayedMission, MissionRecord]:
    played = play(engine, 42, FAILING_PLAN, 400)
    return played, reconstruct(engine, played.initial, played.records, played.final.tick)


@pytest.fixture(scope="module")
def good(engine: SimulationEngine) -> tuple[PlayedMission, MissionRecord]:
    played = play(engine, 42, GOOD_PLAN, 400)
    return played, reconstruct(engine, played.initial, played.records, played.final.tick)


class TestReconstruction:
    def test_history_is_complete_and_matches_play(
        self, failing: tuple[PlayedMission, MissionRecord]
    ) -> None:
        played, record = failing
        assert [s.tick for s in record.history] == list(range(played.final.tick + 1))
        assert record.final_state.state_hash() == played.final.state_hash()


class TestBlackBox:
    def test_failure_is_traced_through_state_transitions(
        self, engine: SimulationEngine, failing: tuple[PlayedMission, MissionRecord]
    ) -> None:
        played, record = failing
        assert played.final.outcome is not None
        assert played.final.outcome.code == "mission_failed_crew_loss"
        cf = counterfactual_factory(engine, played.initial, played.records, played.final.tick)
        report = build_black_box(engine, record, counterfactual=cf)
        trace = report.causal_traces[0]
        assert trace.target_metric == "crew.min_health"
        decision_id = played.records[0].decision_id
        decision_node = f"decision:{decision_id}"
        # Not "decision X caused failure": an explicit chain of recorded transitions.
        expected = [
            decision_node,
            "metric:control.mode.co2_scrubber",
            "metric:life_support.co2_ppm",
            "metric:crew.min_health",
        ]
        assert expected in trace.chains
        node = next(n for n in trace.nodes if n.id == decision_node)
        assert node.details["decision_type"] == "set_subsystem_mode"
        assert node.details["counterfactual"]["verdict"] == "decision_worsened_target"
        co2 = next(n for n in trace.nodes if n.id == "metric:life_support.co2_ppm")
        assert co2.tick is not None and node.tick is not None
        assert node.tick <= co2.tick <= trace.target_tick  # causes precede effects
        edge = next(e for e in trace.edges if e.source == "metric:life_support.co2_ppm")
        assert {"source_onset_tick", "source_peak_severity"} <= set(edge.evidence)

    def test_trace_edges_follow_the_dependency_graph(
        self, engine: SimulationEngine, failing: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = failing
        report = build_black_box(engine, record)
        graph_keys = {(f"metric:{e.source}", f"metric:{e.target}") for e in engine.graph.edges}
        for trace in report.causal_traces:
            for edge in trace.edges:
                if edge.source.startswith("metric:"):
                    assert (edge.source, edge.target) in graph_keys
                else:  # provenance / baseline edges only point at metric nodes
                    assert edge.target.startswith("metric:")

    def test_report_sections(
        self, engine: SimulationEngine, failing: tuple[PlayedMission, MissionRecord]
    ) -> None:
        played, record = failing
        report = build_black_box(engine, record)
        assert report.final_state_hash == played.final.state_hash()
        assert [d.decision_id for d in report.decisions] == [r.decision_id for r in played.records]
        ticks = [t.tick for t in report.timeline]
        assert ticks == sorted(ticks)
        assert any(f.key.startswith("crew_incapacitated") for f in report.failures)
        assert any(f.key == "mission_failed_crew_loss" for f in report.failures)
        assert {"co2_high", "co2_critical"} <= {a.key for a in report.alerts}
        assert report.phase_transitions[0].key == "base_setup"
        risk = next(t for t in report.resource_trends if t.metric == "risk.mission")
        assert risk.ticks[-1] == played.final.tick and risk.max_value >= risk.min_value

    def test_black_box_is_deterministic(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = good
        a = build_black_box(engine, record)
        b = build_black_box(engine, record)
        assert a.model_dump(mode="json") == b.model_dump(mode="json")

    def test_trace_inputs_validated(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = good
        with pytest.raises(UnknownMetricError):
            trace_root_cause(engine, record.history, "power.flux", 10)
        with pytest.raises(ValueError, match="outside history"):
            trace_root_cause(engine, record.history, "power.battery_soc", 10_000)
        with pytest.raises(ValueError, match="empty"):
            trace_root_cause(engine, [], "power.battery_soc", 0)

    def test_nominal_target_resolves_to_baseline(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = good
        trace = trace_root_cause(engine, record.history, "life_support.oxygen_days", 3)
        assert trace.roots == ["baseline:life_support.oxygen_days"]


class TestProfile:
    def test_dimensions_bounded_and_deterministic(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = good
        a = build_profile(engine, record, lens_requests=2)
        b = build_profile(engine, record, lens_requests=2)
        assert a.model_dump() == b.model_dump()
        assert [d.dimension for d in a.dimensions] == list(DIMENSIONS)
        assert all(0.0 <= d.score <= 1.0 for d in a.dimensions)
        assert all(0.0 <= v <= 1.0 for v in a.features.values())
        assert a.provisional and a.weights_version == default_weights().version
        assert a.decision_count == 3

    def test_weights_are_configuration(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = good
        custom = ProfileWeights(
            version="test-1", dimensions={d: {"science_return": 1.0} for d in DIMENSIONS}
        )
        prof = build_profile(engine, record, weights=custom)
        assert prof.weights_version == "test-1"
        assert len({d.score for d in prof.dimensions}) == 1
        assert prof.dimensions[0].score == pytest.approx(prof.features["science_return"])

    def test_styles_differ(
        self,
        engine: SimulationEngine,
        good: tuple[PlayedMission, MissionRecord],
        failing: tuple[PlayedMission, MissionRecord],
    ) -> None:
        g = {d.dimension: d.score for d in build_profile(engine, good[1]).dimensions}
        f = {d.dimension: d.score for d in build_profile(engine, failing[1]).dimensions}
        assert g["crew_safety"] > f["crew_safety"]
        assert g["scientific_ambition"] > f["scientific_ambition"]

    def test_no_decisions(self, engine: SimulationEngine) -> None:
        played = play(engine, 1, {}, 30)
        prof = build_profile(engine, reconstruct(engine, played.initial, [], 30))
        assert prof.decision_count == 0 and len(prof.notes) == 2


class TestMissionDNA:
    def test_format_and_determinism(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        _, record = good
        prof = build_profile(engine, record)
        a = build_mission_dna(engine, record, prof)
        b = build_mission_dna(engine, record, prof)
        assert a == b
        assert re.fullmatch(r"LUNA01-(MX|MC|MP|MF|CL|IP)-[a-z2-7]{10}", a.code)

    def test_no_sensitive_or_identifying_data(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        played, record = good
        dna = build_mission_dna(engine, record, build_profile(engine, record))
        text = str(dna.model_dump())
        for secret in (
            str(played.initial.seed),
            "sess",
            "tl-main",
            *(r.decision_id for r in played.records),
        ):
            assert secret not in text

    def test_same_play_on_another_timeline_gives_same_dna(
        self, engine: SimulationEngine, good: tuple[PlayedMission, MissionRecord]
    ) -> None:
        other = play(engine, 42, GOOD_PLAN, 400, timeline_id="tl-other", session_id="s2")
        rec2 = reconstruct(engine, other.initial, other.records, other.final.tick)
        dna1 = build_mission_dna(engine, good[1], build_profile(engine, good[1]))
        dna2 = build_mission_dna(engine, rec2, build_profile(engine, rec2))
        assert dna1.code == dna2.code
        assert dna_similarity(dna1, dna2) == 1.0

    def test_different_missions_differ(
        self,
        engine: SimulationEngine,
        good: tuple[PlayedMission, MissionRecord],
        failing: tuple[PlayedMission, MissionRecord],
    ) -> None:
        d1 = build_mission_dna(engine, good[1], build_profile(engine, good[1]))
        d2 = build_mission_dna(engine, failing[1], build_profile(engine, failing[1]))
        assert d1.code != d2.code
        assert d2.code.startswith("LUNA01-CL-")
        assert 0.0 <= dna_similarity(d1, d2) < 1.0
