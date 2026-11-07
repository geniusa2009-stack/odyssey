"""Phase 3 outcome model: objective pillars and tiered outcome rules (LUNA-01 v0.2.0).

Surviving is not completing, and completing is not excelling:

* crew loss                        → critical failure (``mission_failed_crew_loss``)
* a primary objective failed        → mission failed (``mission_failed``), crew may be safe
* primary achieved                  → partial
* primary + safety + stability      → success (``mission_complete``)
* + efficiency + science            → exceptional (``mission_complete_exceptional``)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.enums import ObjectiveStatus, OpportunityStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario
from app.simulation.scenarios.schema import OBJECTIVE_CATEGORIES, ScenarioDefinition

SC = get_scenario("luna-01")
PILLARS = ("primary", "safety", "stability", "efficiency", "science", "discovery")


def _by_category(scenario: ScenarioDefinition) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for o in scenario.objectives:
        out.setdefault(o.effective_category, []).append(o.id)
    return out


class TestObjectiveCategories:
    def test_every_objective_has_a_declared_pillar(self) -> None:
        assert all(o.category in OBJECTIVE_CATEGORIES for o in SC.objectives)
        assert set(_by_category(SC)) == set(PILLARS)

    def test_primary_objectives_are_exactly_the_required_ones(self) -> None:
        for o in SC.objectives:
            assert (o.category == "primary") == o.required, o.id

    def test_primary_needs_more_than_one_science_action(self) -> None:
        """Science return needs two completed campaigns, so no single action completes it."""
        science = SC.objective("science_return")
        assert science.achieve_when is not None
        assert science.achieve_when.metric == "science.opportunities_completed"
        assert (science.achieve_when.value or 0) >= 2
        assert {"crew_survival", "science_return", "data_return"} == set(
            _by_category(SC)["primary"]
        )

    def test_required_must_match_primary(self) -> None:
        data = SC.model_dump(mode="json", by_alias=True)
        for o in data["objectives"]:
            if o["id"] == "radiation_safety":
                o["required"] = True
        with pytest.raises(ValueError, match="primary"):
            ScenarioDefinition.model_validate(data)

    def test_outcome_rules_must_reference_existing_pillars(self) -> None:
        data = SC.model_dump(mode="json", by_alias=True)
        for r in data["outcomes"]:
            if r["id"] == "complete":
                r["requires_categories"] = ["primary", "morale"]
        with pytest.raises(ValueError, match="morale"):
            ScenarioDefinition.model_validate(data)


class TestOutcomeRules:
    def test_rule_order_and_tiers(self) -> None:
        tiers = [(r.id, r.effective_tier) for r in SC.outcomes]
        assert tiers[0] == ("crew_loss", "critical_failure")
        assert tiers[-1][1] == "mission_failed"  # catch-all
        assert dict(tiers)["primary_failed"] == "mission_failed"

    def test_no_single_pillar_gives_full_success(self) -> None:
        for rule in SC.outcomes:
            if rule.effective_tier in ("success", "exceptional"):
                assert len(set(rule.requires_categories or [])) >= 3, rule.id
                assert "primary" in (rule.requires_categories or [])

    @staticmethod
    def _conclude(statuses: dict[str, ObjectiveStatus], **state: Any) -> MissionState:
        """Resolve objectives as given just before the last tick, then let the engine finish."""
        engine = SimulationEngine(SC)
        st = engine.advance(engine.initial_state(1), SC.time.max_ticks - 1).state
        for oid, status in statuses.items():
            st.objectives[oid].status = status
            st.objectives[oid].resolved_tick = st.tick
        for member in st.crew:
            member.health = state.get("health", member.health)
        return engine.step(st).state

    @staticmethod
    def _all(status: ObjectiveStatus = ObjectiveStatus.ACHIEVED) -> dict[str, ObjectiveStatus]:
        return {o.id: status for o in SC.objectives}

    def test_everything_achieved_is_exceptional(self) -> None:
        final = self._conclude(self._all())
        assert final.outcome is not None and final.outcome.code == "mission_complete_exceptional"

    def test_missing_efficiency_is_success_not_exceptional(self) -> None:
        statuses = self._all() | {"reserves_at_end": ObjectiveStatus.FAILED}
        final = self._conclude(statuses)
        assert final.outcome is not None and final.outcome.code == "mission_complete"

    @pytest.mark.parametrize("failed", ["radiation_safety", "crew_health", "power_continuity"])
    def test_safety_or_stability_failure_is_partial(self, failed: str) -> None:
        final = self._conclude(self._all() | {failed: ObjectiveStatus.FAILED})
        assert final.outcome is not None and final.outcome.code == "mission_complete_partial"

    @pytest.mark.parametrize("failed", ["science_return", "data_return"])
    def test_primary_failure_with_a_safe_crew_is_mission_failed(self, failed: str) -> None:
        final = self._conclude(self._all() | {failed: ObjectiveStatus.FAILED})
        assert final.outcome is not None
        assert (final.outcome.code, final.outcome.rule_id) == ("mission_failed", "primary_failed")
        assert min(c.health for c in final.crew) > 0.5

    def test_crew_loss_is_critical_failure(self) -> None:
        final = self._conclude(self._all(), health=0.0)
        assert final.outcome is not None and final.outcome.code == "mission_failed_crew_loss"


class TestPassiveAndSingleActions:
    def test_passive_play_fails_the_mission_with_a_safe_crew(self) -> None:
        engine = SimulationEngine(SC)
        for seed in (1, 2, 3):
            final = engine.advance(engine.initial_state(seed), 500).state
            assert final.outcome is not None and final.outcome.code == "mission_failed"
            assert final.objectives["crew_survival"].status == ObjectiveStatus.ACHIEVED
            assert final.objectives["science_return"].status == ObjectiveStatus.FAILED

    @pytest.mark.parametrize("opportunity", [o.id for o in SC.science.opportunities])
    def test_no_single_science_action_gives_full_success(self, opportunity: str) -> None:
        """Start one science campaign as soon as it opens, do nothing else."""
        engine = SimulationEngine(SC)
        spec = SC.opportunity(opportunity)
        if spec.requires_rover:
            raw: dict[str, Any] = {
                "type": "rover_command",
                "action": "traverse",
                "opportunity_id": opportunity,
            }
        else:
            raw = {"type": "start_science_activity", "opportunity_id": opportunity}
        st, started = engine.initial_state(1), False
        while st.status.value == "active":
            opp = st.science.opportunities.get(opportunity)
            if not started and opp is not None and opp.status == OpportunityStatus.OPEN:
                st = engine.apply_decision(st, parse_decision(raw), "single").state
                started = True
            st = engine.step(st).state
        assert started
        assert st.outcome is not None
        assert st.outcome.code not in ("mission_complete", "mission_complete_exceptional")
        assert st.objectives["science_return"].status == ObjectiveStatus.FAILED
