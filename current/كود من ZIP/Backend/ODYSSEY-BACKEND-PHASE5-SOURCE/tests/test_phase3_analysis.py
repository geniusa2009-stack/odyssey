"""Phase 3 behaviour under LUNA-01 v0.2.0: reserves, decision consequences, trade-offs, and the
analysis features (Future Lens, Black Box outcome analysis, Engineering Profile, Mission DNA).

Seeds and thresholds here are fixed so the tests are deterministic; the distributions behind
them are reported in docs/PHASE3_BALANCE_REPORT.md.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.simulation.analysis.balancing.quality import (
    _lens_signals,
    _record_plan,
    _sample_states,
    injected_failures,
    measure_profiles,
)
from app.simulation.analysis.balancing.runner import run_mission
from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.future_lens import FutureLens, FutureLensRequest
from app.simulation.analysis.mission_dna import build_mission_dna
from app.simulation.analysis.profile import build_profile
from app.simulation.analysis.reconstruct import counterfactual_factory, reconstruct
from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.enums import ObjectiveStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.replay import ReplayDecision, replay
from app.simulation.scenarios.loader import get_scenario

SC = get_scenario("luna-01")


@pytest.fixture(scope="module")
def eng() -> SimulationEngine:
    return SimulationEngine(SC)


# ------------------------------------------------------------------------------ resources
class TestResources:
    def test_good_play_ends_with_a_battery_reserve(self, eng: SimulationEngine) -> None:
        for strategy, minimum in (("survival_first", 0.3), ("reserve_keeper", 0.2)):
            m = run_mission(eng, strategy, 1).metrics
            assert m.battery_zero_ticks == 0, strategy
            assert m.battery_soc_final >= minimum, (strategy, m.battery_soc_final)

    def test_balanced_success_without_emptying_the_battery(self, eng: SimulationEngine) -> None:
        m = run_mission(eng, "balanced", 1).metrics
        assert m.outcome == "mission_complete"
        assert m.battery_zero_ticks == 0 and m.objectives["power_continuity"] == "achieved"

    def test_battery_depletion_fails_the_stability_pillar(self, eng: SimulationEngine) -> None:
        m = run_mission(eng, "science_first", 1).metrics
        assert m.battery_zero_ticks > 0
        assert m.objectives["power_continuity"] == "failed"
        assert m.outcome_class != "success"


# ------------------------------------------------------------------------------ decisions
def _without_oxygen_management(eng: SimulationEngine, seed: int, off_tick: int) -> MissionState:
    """Balanced play, but oxygen generation switched off at ``off_tick`` and never back on."""
    base = run_mission(eng, "balanced", seed)
    kept = [
        d.to_replay() for d in base.decisions if d.inputs.get("subsystem") != "oxygen_generation"
    ]
    off = parse_decision(
        {"type": "set_subsystem_mode", "subsystem": "oxygen_generation", "mode": "off"}
    )
    ordered = sorted([*kept, ReplayDecision("x", 0, off_tick, off)], key=lambda d: d.tick)
    plan = [ReplayDecision(d.decision_id, i, d.tick, d.decision) for i, d in enumerate(ordered)]
    return replay(eng, eng.initial_state(seed), plan, 240, skip_invalid=True).state


class TestDecisionConsequences:
    def test_oxygen_generation_is_not_optional(self, eng: SimulationEngine) -> None:
        """v0.2.0 stores ~7 days of oxygen: switching generation off has a consequence."""
        final = _without_oxygen_management(eng, 1, 30)
        assert final.objectives["life_support_stability"].status == ObjectiveStatus.FAILED
        assert final.outcome is not None
        assert final.outcome.code not in ("mission_complete", "mission_complete_exceptional")

    def test_science_ambition_costs_margins(self, eng: SimulationEngine) -> None:
        for seed in (1, 2, 3):
            sci = run_mission(eng, "science_first", seed).metrics
            safe = run_mission(eng, "survival_first", seed).metrics
            assert sci.science_points > safe.science_points
            assert sci.battery_soc_final < safe.battery_soc_final
            assert sci.objectives["radiation_safety"] == "failed"
            assert safe.objectives["radiation_safety"] == "achieved"

    def test_two_different_commanders_can_both_succeed(self, eng: SimulationEngine) -> None:
        """Pareto: more science on thin margins vs less science with large reserves."""
        bal = run_mission(eng, "balanced", 1).metrics
        safe = run_mission(eng, "survival_first", 1).metrics
        assert bal.outcome_class == safe.outcome_class == "success"
        assert bal.science_points > safe.science_points
        assert safe.battery_soc_final > bal.battery_soc_final


# ------------------------------------------------------------------------------ Future Lens
MAJOR_CANDIDATES: tuple[dict[str, Any], ...] = (
    {"type": "set_subsystem_mode", "subsystem": "oxygen_generation", "mode": "off"},
    {"type": "set_subsystem_mode", "subsystem": "water_recovery", "mode": "off"},
    {"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "eco"},
)


class TestFutureLensSeparation:
    @pytest.fixture(scope="class")
    def predictions(self, eng: SimulationEngine) -> list[Any]:
        state = _sample_states(eng, (1,), (100,))[0]
        req = FutureLensRequest.model_validate(
            {
                "candidates": [
                    {"label": f"c{i}", "decisions": [c]} for i, c in enumerate(MAJOR_CANDIDATES)
                ],
                "horizon_ticks": 24,
                "samples": 2,
            }
        )
        return list(FutureLens(eng).predict(state, req).predictions)

    def test_major_choices_show_a_different_future(self, predictions: list[Any]) -> None:
        base = predictions[0]
        assert base.is_baseline
        outlook = {o.objective: o.projected_status for o in base.objective_outlook}
        worst = {m.metric: m.worst for m in base.metrics}
        for p in predictions[1:]:
            distinct_end = any(abs(v) > 0.05 for v in p.vs_baseline.values())
            assert _lens_signals(p, distinct_end, outlook, worst), p.label

    def test_every_new_warning_is_explained_by_the_candidate(self, predictions: list[Any]) -> None:
        explained_any = False
        for p in predictions[1:]:
            if not p.new_warnings:
                continue
            node = f"decision:lens:{p.label}:0"
            traced = {
                t.target_metric for t in p.causal_explanation if node in {n.id for n in t.nodes}
            }
            assert traced, p.label
            explained_any = True
        assert explained_any

    def test_objective_outlook_covers_every_objective(self, predictions: list[Any]) -> None:
        for p in predictions:
            assert {o.objective for o in p.objective_outlook} == {o.id for o in SC.objectives}


# ------------------------------------------------------------------------------ Black Box
class TestOutcomeAnalysis:
    def test_crew_safe_mission_failure_is_explained_as_an_omission(
        self, eng: SimulationEngine
    ) -> None:
        case = _record_plan(eng, 1, {}, "passive")
        record = reconstruct(eng, case.initial, case.records, case.final.tick)
        analysis = build_black_box(eng, record).outcome_analysis
        assert analysis is not None and analysis.outcome_code == "mission_failed"
        chain = next(c for c in analysis.chains if c.objective == "science_return")
        assert chain.kind == "omission" and chain.facts
        assert not chain.root_decisions  # no decisions were made: none may be blamed

    def test_root_decisions_are_verified_by_counterfactual(self) -> None:
        case = next(c for c in injected_failures() if c.name == "scrubber_off")
        record = reconstruct(case.engine, case.initial, case.records, case.final.tick)
        cf = counterfactual_factory(case.engine, case.initial, case.records, case.final.tick)
        analysis = build_black_box(case.engine, record, counterfactual=cf).outcome_analysis
        assert analysis is not None
        blamed = [d for c in analysis.chains for d in c.root_decisions]
        assert blamed and all(d.verdict == "decision_worsened_target" for d in blamed)
        for chain in analysis.chains:
            blamed_ids = {d.decision_id for d in chain.root_decisions}
            assert not blamed_ids & {d.decision_id for d in chain.on_path_no_effect}


# ------------------------------------------------------------------------------ profile, DNA
class TestProfileSeparation:
    def test_profiles_derive_from_behaviour_and_separate_strategies(
        self, eng: SimulationEngine
    ) -> None:
        names = ["survival_first", "science_first", "balanced", "passive", "high_risk"]
        sep = measure_profiles(eng, names, (1, 2))
        assert sep.distances["survival_first"]["science_first"] >= 0.5
        assert sep.distances["balanced"]["passive"] >= 0.5
        means = sep.means
        assert means["high_risk"]["crew_safety"] < means["balanced"]["crew_safety"] - 0.3
        assert means["high_risk"]["risk_preference"] > means["balanced"]["risk_preference"] + 0.3

    def test_exceptional_missions_get_their_own_dna_tag(self, eng: SimulationEngine) -> None:
        run = run_mission(eng, "expert", 1)
        assert run.metrics.outcome == "mission_complete_exceptional"
        plan: dict[int, list[dict[str, Any]]] = {}
        for d in run.decisions:
            plan.setdefault(d.tick, []).append(dict(d.inputs))
        case = _record_plan(eng, 1, plan, "expert:1")
        record = reconstruct(eng, case.initial, case.records, case.final.tick)
        dna = build_mission_dna(eng, record, build_profile(eng, record))
        assert dna.code.startswith("LUNA01-MX-")
