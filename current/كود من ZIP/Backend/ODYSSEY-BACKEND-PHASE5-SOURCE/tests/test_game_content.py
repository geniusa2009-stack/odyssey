"""Game content: schema, cross-reference validation, engine bindings, provenance, hashing."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.game.content.loader import DATA_DIR, ContentError, default_content, load_content
from app.game.content.vocabulary import CAMPAIGN_PHASES
from app.simulation.scenarios.loader import list_scenarios


def _mutated(tmp_path: Path, file: str, edit: Callable[[str], str]) -> Path:
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    path = target / file
    original = path.read_text(encoding="utf-8")
    changed = edit(original)
    assert changed != original, "mutation did not apply"
    path.write_text(changed, encoding="utf-8")
    return target


def _replace(old: str, new: str, count: int = 1) -> Callable[[str], str]:
    def edit(text: str) -> str:
        assert old in text, old
        return text.replace(old, new, count)

    return edit


def test_shipped_content_is_valid_and_complete() -> None:
    c = default_content()
    assert c.version == "1.0.0"
    assert tuple(p.id for p in c.content.campaign.phases) == CAMPAIGN_PHASES
    authored = [p.id for p in c.content.campaign.phases if p.authored]
    assert authored == ["EARTH_COMMAND", "LUNA_01"]
    assert set(c.scenarios) == {"earth-command", "luna-01"}
    domains = {cap.domain for cap in c.content.progression.capabilities}
    assert len(domains) == 12, "capabilities span all 12 domains"
    assert {m.id for m in c.content.narrative.crew} == {"maya", "omar", "sofia", "jay"}


def test_content_hash_is_stable() -> None:
    a = load_content()
    b = load_content()
    assert a.content_hash == b.content_hash
    assert len(a.content_hash) == 64


def test_earth_command_scenario_is_not_in_the_v1_registry() -> None:
    # The game scenario must not leak into frozen API v1 (/missions, fixtures).
    assert "earth-command" not in {s.id for s in list_scenarios()}


@pytest.mark.parametrize(
    ("file", "old", "new", "expected"),
    [
        (
            "worlds/earth_command.yaml",
            "consumes_from: earth.command.engineering.spares_locker",
            "consumes_from: earth.command.engineering.no_such_locker",
            "unknown container earth.command.engineering.no_such_locker",
        ),
        (
            "worlds/earth_command.yaml",
            "subsystem: thermal_control, mode: $mode",
            "subsystem: reactor, mode: $mode",
            "has no consumer reactor",
        ),
        (
            "worlds/earth_command.yaml",
            "params: {mode: {enum: [eco, nominal]}}\n        engine:\n"
            "          - decision: {type: set_subsystem_mode, subsystem: air_handling",
            'params: {mode: {enum: ["off", eco, nominal]}}\n        engine:\n'
            "          - decision: {type: set_subsystem_mode, subsystem: air_handling",
            "consumer air_handling has no mode off",
        ),
        (
            "worlds/earth_command.yaml",
            "trigger: {sim_event: bus_b_breaker_fault}",
            "trigger: {sim_event: meteor_strike}",
            "unknown simulation event meteor_strike",
        ),
        (
            "worlds/earth_command.yaml",
            "{alert: critical_load_lost}\n            - {alert: battery_critical}",
            "{alert: invented_alert}\n            - {alert: battery_critical}",
            "unknown simulation alert invented_alert",
        ),
        (
            "worlds/earth_command.yaml",
            "{item: cargo.water_tank, quantity: 4}",
            "{item: cargo.water_tank, quantity: 40}",
            "exceeds max stack",
        ),
        (
            "worlds/luna_01.yaml",
            "installed_modules: {shielding: module.radiation_shelter_liner}",
            "installed_modules: {shielding: module.isru_oxygen_pilot}",
            "is not used by infra.radiation_shelter",
        ),
        (
            "worlds/luna_01.yaml",
            "maya: [{decision: {type: clean_solar_array, crew_id: crew_pwr}}]",
            "maya: [{decision: {type: clean_solar_array, crew_id: maya}}]",
            "scenario luna-01 has no crew maya",
        ),
        (
            "campaign.yaml",
            'when: {sim: {metric: rover.battery_kwh, op: ">=", value: 45.0}}',
            'when: {sim: {metric: rover.warp_core, op: ">=", value: 45.0}}',
            "unknown simulation metric rover.warp_core",
        ),
        (
            "campaign.yaml",
            "next: {phase: LUNA_01, mission: luna_01.the_last_light}",
            "next: {phase: LUNA_01, mission: luna_01.no_such_mission}",
            "unknown next mission luna_01.no_such_mission",
        ),
        (
            "progression.yaml",
            "prerequisites: [{capability: power.load_management, stage: DISCOVERED}]",
            "prerequisites: [{capability: power.load_management, stage: WARP_READY}]",
            "has no stage WARP_READY",
        ),
        (
            "progression.yaml",
            "provenance: {classification: verified_evidence, "
            "evidence_refs: [change4_lnd_dose_rate, donki_sep_events]}",
            "provenance: {classification: verified_evidence, "
            "evidence_refs: [lunar_polar_illumination]}",
            "verified_evidence cites unverified evidence lunar_polar_illumination",
        ),
        (
            "knowledge.yaml",
            "why_metric: power.unmet_kw",
            "why_metric: power.flux_capacitor",
            "unknown WHY? metric power.flux_capacitor",
        ),
        (
            "narrative.yaml",
            "speaker: omar\n    priority: 10",
            "speaker: hal\n    priority: 10",
            "unknown speaker hal",
        ),
        (
            "readiness.yaml",
            "requires: [{capability: transportation.planetary_return, stage: MARS_CERTIFIED}]",
            "requires: [{capability: transportation.teleporter, stage: MARS_CERTIFIED}]",
            "unknown capability transportation.teleporter",
        ),
        (
            "catalog.yaml",
            "qualification: {capability: isru.oxygen_extraction, stage: LAB_VALIDATED}",
            "qualification: {capability: isru.oxygen_extraction, stage: MARS_CERTIFIED_PLUS}",
            "has no stage MARS_CERTIFIED_PLUS",
        ),
    ],
)
def test_bad_references_fail_validation(
    tmp_path: Path, file: str, old: str, new: str, expected: str
) -> None:
    data = _mutated(tmp_path, file, _replace(old, new))
    with pytest.raises(ContentError) as exc:
        load_content(data)
    assert any(expected in p for p in exc.value.problems), exc.value.problems


def test_capability_prerequisite_cycles_are_rejected(tmp_path: Path) -> None:
    data = _mutated(
        tmp_path,
        "progression.yaml",
        _replace(
            "    domain: power\n",
            "    domain: power\n    prerequisites: "
            "[{capability: transportation.crew_launch_readiness, stage: PROTOTYPE_TESTED}]\n",
        ),
    )
    with pytest.raises(ContentError) as exc:
        load_content(data)
    assert any("prerequisite cycle" in p for p in exc.value.problems)


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    data = _mutated(tmp_path, "manifest.yaml", lambda t: t + "\nsecret_flag: true\n")
    with pytest.raises(ContentError) as exc:
        load_content(data)
    assert any("Extra inputs" in p for p in exc.value.problems)


def test_phase_order_must_match_the_campaign(tmp_path: Path) -> None:
    data = _mutated(
        tmp_path,
        "campaign.yaml",
        _replace("  - id: MARS_01\n    order: 8", "  - id: MARS_02\n    order: 8"),
    )
    with pytest.raises(ContentError) as exc:
        load_content(data)
    assert any("phases must be exactly" in p for p in exc.value.problems)


def test_yaml_errors_are_reported_as_content_errors(tmp_path: Path) -> None:
    data = _mutated(tmp_path, "knowledge.yaml", lambda t: t + "\n  - {broken: [\n")
    with pytest.raises(ContentError) as exc:
        load_content(data)
    assert "YAML error" in exc.value.problems[0]


def test_game_scenario_file_cannot_escape_its_directory(tmp_path: Path) -> None:
    data = _mutated(
        tmp_path,
        "campaign.yaml",
        _replace("file: earth-command.yaml", "file: ../../../../simulation/scenarios/luna.yaml"),
    )
    with pytest.raises(ContentError) as exc:
        load_content(data)
    assert any("not found" in p for p in exc.value.problems)


def test_every_interaction_combination_renders_valid_decisions() -> None:
    # load_content() already type-checks all combinations; spot-check the count is meaningful.
    from app.game.content.rendering import all_param_assignments, rendered_decisions

    c = default_content()
    rendered = 0
    for obj in c.index.objects.values():
        for inter in obj.interactions:
            for params in all_param_assignments(inter):
                rendered += len(rendered_decisions(inter, params))
    assert rendered >= 60
