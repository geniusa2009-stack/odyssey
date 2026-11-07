"""Future Lens quality properties measured across many mission states (Phase 2).

These pin *guarantees* (determinism, isolation, surprise-blindness, confidence behaviour,
explanations naming the candidate). Balance-dependent observations (e.g. which decisions are
currently indistinguishable) are reported by ``balancing.quality.measure_future_lens`` and
documented in docs/BALANCING_FINDINGS.md instead of being frozen in tests.
"""

from __future__ import annotations

import pytest

from app.simulation.analysis.balancing.quality import _sample_states, measure_future_lens
from app.simulation.analysis.future_lens import FutureLens, FutureLensRequest
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine


@pytest.fixture(scope="module")
def states(engine: SimulationEngine) -> list[MissionState]:
    return _sample_states(engine, (1, 2), (20, 100, 115, 155, 200))


def _noop(horizon: int, policy: str = "known_only", samples: int = 2) -> FutureLensRequest:
    return FutureLensRequest.model_validate(
        {
            "candidates": [{"label": "noop", "decisions": []}],
            "include_baseline": False,
            "horizon_ticks": horizon,
            "samples": samples,
            "knowledge_policy": policy,
            "explain": False,
        }
    )


def test_measurement_reports_determinism_and_isolation(engine: SimulationEngine) -> None:
    q = measure_future_lens(engine, seeds=(1,), ticks=(60, 115), samples=2)
    s = q.summary()
    assert s["deterministic"] and s["isolated"]
    assert s["states"] == 2 and s["candidate_cases"] == 20
    assert 0.0 <= s["indistinguishable_rate"] <= 1.0


def test_confidence_falls_with_horizon(
    engine: SimulationEngine, states: list[MissionState]
) -> None:
    lens = FutureLens(engine)
    for st in states[:3]:
        scores = []
        for h in (6, 24, 72):
            conf = lens.predict(st, _noop(h)).predictions[0].confidence
            assert conf is not None
            scores.append(conf.score)
        assert scores == sorted(scores, reverse=True)


def test_known_only_is_blind_to_the_scheduled_storm(
    engine: SimulationEngine, states: list[MissionState]
) -> None:
    lens = FutureLens(engine)
    before_storm = [s for s in states if s.tick == 115]
    assert before_storm
    for st in before_storm:
        known = lens.predict(st, _noop(24)).predictions[0]
        # samples=1: sample 0 *is* the real future. (With more samples the headline value is
        # a median across real + derived samples — documented in BALANCING_FINDINGS.md.)
        omni = lens.predict(st, _noop(24, "omniscient", samples=1)).predictions[0]
        dose_known = next(m.end for m in known.metrics if m.metric == "crew.max_dose_msv")
        dose_omni = next(m.end for m in omni.metrics if m.metric == "crew.max_dose_msv")
        assert dose_omni > dose_known + 5.0  # the storm is real but not foreseeable
        real = engine.advance(st, 24).state
        assert dose_omni == pytest.approx(engine.metrics.value("crew.max_dose_msv", real))


def test_sampling_never_changes_the_median_wildly(
    engine: SimulationEngine, states: list[MissionState]
) -> None:
    lens = FutureLens(engine)
    for st in states[:4]:
        one = lens.predict(st, _noop(48, samples=1)).predictions[0].risk["end_risk"]
        many = lens.predict(st, _noop(48, samples=8)).predictions[0].risk["end_risk"]
        assert abs(one - many) < 0.1


def test_explanation_names_the_candidate_when_it_causes_the_first_warning(
    engine: SimulationEngine, states: list[MissionState]
) -> None:
    st = next(s for s in states if s.tick == 100)
    req = FutureLensRequest.model_validate(
        {
            "candidates": [
                {
                    "label": "scrub_off",
                    "decisions": [
                        {"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "off"}
                    ],
                }
            ],
            "horizon_ticks": 24,
            "samples": 2,
        }
    )
    cand = FutureLens(engine).predict(st, req).predictions[1]
    assert cand.warnings and cand.warnings[0].alert_id == "co2_high"
    assert any(
        "decision:lens:scrub_off:0" in {n.id for n in t.nodes} for t in cand.causal_explanation
    )
