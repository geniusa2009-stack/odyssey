"""Future Lens: isolation (never mutates the real mission), determinism, honesty, branches."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.simulation.analysis.future_lens import FutureLens, FutureLensRequest
from app.simulation.domain.state import MissionState
from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import SimulationEngine

SCRUBBER_OFF = {
    "label": "scrubber_off",
    "decisions": [{"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "off"}],
}


@pytest.fixture(scope="module")
def mid(engine: SimulationEngine) -> MissionState:
    return engine.advance(engine.initial_state(42), 100).state


def _req(**kw: object) -> FutureLensRequest:
    base: dict[str, object] = {"candidates": [SCRUBBER_OFF], "horizon_ticks": 24, "samples": 3}
    base.update(kw)
    return FutureLensRequest.model_validate(base)


class TestIsolation:
    def test_real_state_is_never_mutated(self, engine: SimulationEngine, mid: MissionState) -> None:
        before_dump = mid.model_dump(mode="json")
        before_hash = mid.state_hash()
        result = FutureLens(engine).predict(mid, _req(samples=4, horizon_ticks=48))
        assert mid.model_dump(mode="json") == before_dump
        assert mid.state_hash() == before_hash == result.base_state_hash

    def test_mutating_results_cannot_reach_the_mission(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        before = mid.state_hash()
        result = FutureLens(engine).predict(mid, _req())
        for p in result.predictions:
            p.metrics.clear()
            p.risk["end_risk"] = 99.0
        assert mid.state_hash() == before

    @given(horizon=st.integers(1, 60), samples=st.integers(1, 4))
    def test_property_isolation_for_any_request(
        self, engine: SimulationEngine, mid: MissionState, horizon: int, samples: int
    ) -> None:
        before = mid.state_hash()
        FutureLens(engine).predict(mid, _req(horizon_ticks=horizon, samples=samples, explain=False))
        assert mid.state_hash() == before


class TestDeterminism:
    def test_same_inputs_same_prediction(self, engine: SimulationEngine, mid: MissionState) -> None:
        a = FutureLens(engine).predict(mid, _req())
        b = FutureLens(SimulationEngine(engine.scenario)).predict(mid.clone(), _req())
        assert a.model_dump(mode="json") == b.model_dump(mode="json")
        assert a.request_hash == b.request_hash

    def test_request_hash_changes_with_request(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        lens = FutureLens(engine)
        assert (
            lens.predict(mid, _req()).request_hash
            != lens.predict(mid, _req(horizon_ticks=25)).request_hash
        )


class TestContent:
    def test_baseline_and_candidate_branches(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        result = FutureLens(engine).predict(mid, _req())
        assert [p.label for p in result.predictions] == ["baseline", "scrubber_off"]
        base, cand = result.predictions
        assert base.is_baseline and base.valid and cand.valid
        assert cand.ticks_projected == 24
        co2 = next(m for m in cand.metrics if m.metric == "life_support.co2_ppm")
        assert co2.end > co2.start and co2.worst == pytest.approx(co2.end_max, rel=0.2)
        assert cand.vs_baseline["life_support.co2_ppm"] > 0
        assert {w.alert_id for w in cand.warnings} >= {"co2_high"}
        assert all(0.0 <= w.sample_fraction <= 1.0 for w in cand.warnings)
        assert cand.risk["end_risk"] > base.risk["end_risk"]
        assert cand.assumptions and "No further decisions" in cand.assumptions[0]

    def test_causal_explanation_cites_the_candidate_decision(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        cand = FutureLens(engine).predict(mid, _req()).predictions[1]
        assert cand.causal_explanation
        trace = next(
            t for t in cand.causal_explanation if t.target_metric == "life_support.co2_ppm"
        )
        decision_nodes = [n for n in trace.nodes if n.kind == "decision"]
        assert decision_nodes and decision_nodes[0].id == "decision:lens:scrubber_off:0"
        assert any(chain[0] == "decision:lens:scrubber_off:0" for chain in trace.chains)

    def test_confidence_metadata(self, engine: SimulationEngine, mid: MissionState) -> None:
        for p in FutureLens(engine).predict(mid, _req()).predictions:
            c = p.confidence
            assert c is not None and c.provisional
            assert 0.0 <= c.score <= 1.0 and c.samples == 3
            assert c.level == ("high" if c.score >= 0.6 else "medium" if c.score >= 0.35 else "low")
        short = FutureLens(engine).predict(mid, _req(horizon_ticks=6)).predictions[0]
        long = FutureLens(engine).predict(mid, _req(horizon_ticks=96)).predictions[0]
        assert short.confidence and long.confidence
        assert short.confidence.horizon_factor > long.confidence.horizon_factor

    def test_invalid_candidate_is_reported_not_raised(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        req = _req(
            candidates=[
                {
                    "label": "bad",
                    "decisions": [{"type": "schedule_maintenance", "component": "warp_core"}],
                }
            ]
        )
        bad = FutureLens(engine).predict(mid, req).predictions[1]
        assert not bad.valid and bad.rejection == {
            "code": "unknown_component",
            "message": "unknown component 'warp_core'",
        }

    def test_known_only_hides_unforeseeable_future_events(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        lens = FutureLens(engine)
        result = lens.predict(mid, _req(horizon_ticks=30))
        assert "solar_particle_event" in result.excluded_events  # scheduled at 122, hidden
        dose = next(m for m in result.predictions[0].metrics if m.metric == "crew.max_dose_msv")
        omni = lens.predict(mid, _req(horizon_ticks=30, knowledge_policy="omniscient"))
        dose_omni = next(m for m in omni.predictions[0].metrics if m.metric == "crew.max_dose_msv")
        assert omni.excluded_events == []
        assert dose_omni.end_max > dose.end_max  # only the omniscient lens sees the SPE

    def test_omniscient_sample_zero_matches_reality(
        self, engine: SimulationEngine, mid: MissionState
    ) -> None:
        result = FutureLens(engine).predict(
            mid, _req(knowledge_policy="omniscient", samples=1, horizon_ticks=40)
        )
        real = engine.advance(mid, 40, RunOptions()).state
        base = result.predictions[0]
        for m in base.metrics:
            assert m.end == pytest.approx(engine.metrics.value(m.metric, real))

    def test_horizon_clipped_at_mission_end(self, engine: SimulationEngine) -> None:
        late = engine.advance(engine.initial_state(1), 230).state
        p = FutureLens(engine).predict(late, _req(horizon_ticks=48)).predictions[0]
        assert p.ticks_projected == 10 and p.concludes
        assert p.projected_outcome is not None
        assert any("clipped" in a for a in p.assumptions)

    def test_concluded_mission(self, engine: SimulationEngine) -> None:
        done = engine.advance(engine.initial_state(1), 400).state
        p = FutureLens(engine).predict(done, _req()).predictions[0]
        assert not p.valid and p.rejection is not None
        assert p.rejection["code"] == "mission_concluded"

    def test_request_limits(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _req(horizon_ticks=0)
        with pytest.raises(ValidationError):
            _req(samples=17)
        with pytest.raises(ValidationError):
            _req(candidates=[])
