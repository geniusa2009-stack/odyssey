"""Scenario data: LUNA-01 foundation and the declarative scenario schema."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.science.evidence import default_registry
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import (
    ScenarioNotFoundError,
    get_scenario,
    list_scenarios,
    load_yaml,
    scenario_content_hash,
)
from app.simulation.scenarios.schema import Condition, ScenarioDefinition
from tests.helpers import scenario_variant

REQUIRED_PHASES = [
    "landing",
    "base_setup",
    "initial_resource_management",
    "reduced_solar_availability",
    "power_management",
    "scientific_opportunity",
    "environmental_emergency",
    "communication_loss",
    "resource_cascade",
    "rover_decision",
    "final_low_power",
    "mission_conclusion",
    "post_mission_analysis",
]


def test_luna01_has_every_required_phase_in_order(scenario: ScenarioDefinition) -> None:
    assert [p.id for p in scenario.phases] == REQUIRED_PHASES
    assert scenario.phases[-2].kind == "conclusion"
    assert scenario.phases[-1].kind == "analysis"


def test_luna01_is_flagged_provisional(scenario: ScenarioDefinition) -> None:
    assert scenario.provisional is True


def test_registry_lookup() -> None:
    assert [s.id for s in list_scenarios()] == ["luna-01"]
    with pytest.raises(ScenarioNotFoundError):
        get_scenario("mars-99")


def test_content_hash_is_stable(scenario: ScenarioDefinition) -> None:
    again = ScenarioDefinition.model_validate(scenario.model_dump(mode="json", by_alias=True))
    assert scenario_content_hash(scenario) == scenario_content_hash(again)
    changed = scenario_variant(lambda d: d["time"].update(max_ticks=200))
    assert scenario_content_hash(changed) != scenario_content_hash(scenario)


def test_scenario_evidence_references_exist(scenario: ScenarioDefinition) -> None:
    ids = default_registry().ids()
    referenced = {e for refs in scenario.evidence.values() for e in refs}
    referenced |= set(scenario.environment.evidence)
    referenced |= {e for ev in scenario.events for e in ev.evidence}
    assert referenced <= ids, referenced - ids


def test_no_dialogue_only_message_keys(scenario: ScenarioDefinition) -> None:
    for ev in scenario.events:
        assert ev.message_key.startswith("event.")
        assert " " not in ev.message_key


class TestYaml12Loader:
    def test_off_on_yes_no_are_strings(self) -> None:
        data = load_yaml("a: off\nb: on\nc: yes\nd: no\ne: true\nf: false")
        assert data == {"a": "off", "b": "on", "c": "yes", "d": "no", "e": True, "f": False}

    def test_unsafe_tags_rejected(self) -> None:
        import yaml

        with pytest.raises(yaml.YAMLError):
            load_yaml("!!python/object/apply:os.system ['true']")


class TestSchemaValidation:
    @pytest.mark.parametrize(
        ("mutate", "message"),
        [
            (lambda d: d["crew"].append(dict(d["crew"][0])), "duplicate crew ids"),
            (lambda d: d["power"].update(heater_consumer="nope"), "unknown consumer 'nope'"),
            (
                lambda d: d["events"].append(
                    {
                        "id": "x",
                        "kind": "system_fault",
                        "message_key": "event.x",
                        "trigger": {"type": "scheduled", "at_tick": 1},
                        "effects": [
                            {"type": "damage_component", "component": "ghost", "amount": 0.1}
                        ],
                    }
                ),
                "unknown component 'ghost'",
            ),
            (lambda d: d["outcomes"].pop(), "catch-all"),
            (lambda d: d["phases"].pop(), "exactly one conclusion and one analysis"),
            (lambda d: d["environment"]["sink_temp_c"].reverse(), "strictly increasing"),
            (lambda d: d["events"].append(dict(d["events"][0])), "duplicate event ids"),
        ],
    )
    def test_invalid_scenarios_rejected(self, mutate: Any, message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            scenario_variant(mutate)

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            {"metric": "a", "op": "<", "value": 1, "all": []},
            {"metric": "a"},
        ],
    )
    def test_condition_needs_exactly_one_form(self, raw: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Condition.model_validate(raw)

    def test_condition_not_alias(self) -> None:
        cond = Condition.model_validate({"not": {"metric": "a.b", "op": ">", "value": 1}})
        assert cond.metrics() == {"a.b"}

    def test_engine_rejects_unknown_metric_references(self) -> None:
        bad = scenario_variant(
            lambda d: d["alerts"].append(
                {
                    "id": "z",
                    "metric": "power.flux_capacitor",
                    "op": "<",
                    "threshold": 1,
                    "clear_threshold": 2,
                    "severity": "warning",
                }
            )
        )
        with pytest.raises(ValueError, match="unknown metrics"):
            SimulationEngine(bad)

    def test_decision_balancing_limits_live_in_data(self) -> None:
        """Balancing constants are scenario data: changing them needs no code change."""
        tweaked = scenario_variant(lambda d: d["decisions"].update(eva_ticks=5))
        assert SimulationEngine(tweaked).scenario.decisions.eva_ticks == 5
