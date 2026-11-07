"""Parameter governance (Phase 3): science is not rewritten to improve balance.

* Every scenario value linked to evidence that states a numeric value must equal it.
* The balance search refuses EVIDENCE_LOCKED and protected paths.
* docs/PARAMETER_GOVERNANCE.md lists every EVIDENCE_LOCKED path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.science.evidence import default_registry
from app.simulation.analysis.balancing.overrides import OverrideError, get_path
from app.simulation.analysis.balancing.search import (
    EVIDENCE_LOCKED_PATHS,
    PROTECTED_PATHS,
    SearchSpace,
)
from app.simulation.scenarios.loader import get_scenario

DOC = Path(__file__).resolve().parents[1] / "docs" / "PARAMETER_GOVERNANCE.md"


def _scenario_value(path: str) -> float:
    data = get_scenario("luna-01").model_dump(mode="json", by_alias=True)
    value = get_path(data, path)
    if isinstance(value, list):  # environment keyframes: the anchored baseline is the first one
        return float(value[0]["value"])
    return float(value)


def test_evidence_values_are_unchanged() -> None:
    reg = default_registry()
    checked = 0
    for path, ids in get_scenario("luna-01").evidence.items():
        for evidence_id in ids:
            ev = reg.get(evidence_id)
            if ev.value is None:
                continue
            assert _scenario_value(path) == pytest.approx(ev.value), (path, evidence_id)
            checked += 1
    assert checked >= 7


def test_every_numeric_evidence_link_is_evidence_locked() -> None:
    reg = default_registry()
    for path, ids in get_scenario("luna-01").evidence.items():
        if any(reg.get(i).value is not None for i in ids):
            assert path in EVIDENCE_LOCKED_PATHS, path


@pytest.mark.parametrize(
    "path",
    [
        "life_support.o2_consumption_kg_per_crew_day",
        "environment.radiation_dose_rate_msv_h.0.value",
        "environment.solar_availability.3.value",
        "events.solar_particle_event.trigger.at_tick",
    ],
)
def test_search_refuses_protected_parameters(path: str) -> None:
    with pytest.raises(OverrideError):
        SearchSpace(((path, (1.0,)),)).validate()


def test_search_accepts_gameplay_parameters() -> None:
    SearchSpace((("power.battery.capacity_kwh", (200.0,)),)).validate()


def test_governance_document_lists_locked_and_protected_paths() -> None:
    text = DOC.read_text(encoding="utf-8")
    for path in sorted(PROTECTED_PATHS):
        assert f"`{path}`" in text, path
    for label in ("EVIDENCE_LOCKED", "EDUCATIONAL_ABSTRACTION", "GAMEPLAY_PARAMETER", "UNVERIFIED"):
        assert label in text
