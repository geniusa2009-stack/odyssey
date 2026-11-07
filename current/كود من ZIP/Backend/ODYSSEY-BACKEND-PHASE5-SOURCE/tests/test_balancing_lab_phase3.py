"""Balancing Lab tools added in Phase 3: trajectories, decision audit, search, outcome tiers."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from app.simulation.analysis.balancing.__main__ import main
from app.simulation.analysis.balancing.aggregate import OUTCOME_CLASSES, summarize
from app.simulation.analysis.balancing.decision_audit import audit
from app.simulation.analysis.balancing.overrides import (
    OverrideError,
    apply_overrides,
    parse_override,
)
from app.simulation.analysis.balancing.runner import run_mission
from app.simulation.analysis.balancing.search import (
    ENVELOPES,
    SearchSpace,
    deviation,
    report_markdown,
    run_search,
)
from app.simulation.analysis.balancing.trajectory import COLUMNS, play_trajectory
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario

SC = get_scenario("luna-01")


@pytest.fixture(scope="module")
def eng() -> SimulationEngine:
    return SimulationEngine(SC)


class TestOutcomeClasses:
    def test_tiers_map_to_classes_and_success_rate(self, eng: SimulationEngine) -> None:
        assert OUTCOME_CLASSES == ("exceptional", "success", "partial", "failure", "crew_loss")
        rows = [
            run_mission(eng, "expert", 1).metrics,
            run_mission(eng, "balanced", 1).metrics,
            run_mission(eng, "passive", 1).metrics,
        ]
        assert [r.outcome_class for r in rows] == ["exceptional", "success", "failure"]
        by = {s.strategy: s for s in summarize(rows)}
        assert by["expert"].success_rate == 1.0  # exceptional counts as success
        assert by["passive"].success_rate == 0.0
        assert by["passive"].outcome_rates["failure"] == 1.0


class TestTrajectory:
    def test_rows_cover_every_tick_and_required_columns(self, eng: SimulationEngine) -> None:
        t = play_trajectory(eng, "balanced", 1)
        assert len(t.rows) == SC.time.max_ticks + 1 and t.rows[0]["tick"] == 0
        required = {
            "hours",
            "generation_kw",
            "battery_soc",
            "oxygen_days",
            "water_days",
            "food_days",
            "habitat_temp_c",
            "dose_rate_msv_h",
            "min_health",
            "science_points",
            "projected_dose_margin_msv",
        }
        assert required <= set(t.rows[0]) and {c for c, _ in COLUMNS} <= set(t.rows[0])
        assert {"phase", "decisions", "events", "alerts"} <= set(t.rows[0])
        decided = [r for r in t.rows if r["decisions"]]
        assert decided and all(isinstance(d, str) for r in decided for d in r["decisions"])
        assert any("space_weather" in e for r in t.rows for e in r["events"])

    def test_csv_and_json_exports(self, eng: SimulationEngine, tmp_path: Path) -> None:
        t = play_trajectory(eng, "passive", 1)
        rows = list(csv.DictReader(io.StringIO(t.to_csv())))
        assert len(rows) == len(t.rows) and rows[-1]["phase"] == "post_mission_analysis"
        assert (
            main(
                [
                    "trajectory",
                    "--strategy",
                    "passive",
                    "--seed",
                    "1",
                    "--format",
                    "json",
                    "--output",
                    str(tmp_path / "p.json"),
                ]
            )
            == 0
        )
        doc = json.loads((tmp_path / "p.json").read_text())
        assert doc["outcome"] == "mission_failed" and len(doc["rows"]) == 241


class TestDecisionAudit:
    def test_classifies_from_measured_consequences(self, eng: SimulationEngine) -> None:
        catalogue = (
            (
                "oxygen_generation off",
                {"type": "set_subsystem_mode", "subsystem": "oxygen_generation", "mode": "off"},
            ),
            (
                "rover_charger off",
                {"type": "set_subsystem_mode", "subsystem": "rover_charger", "mode": "off"},
            ),
        )
        classes, rows = audit(
            eng, reference="balanced", seeds=(1,), ticks=(30,), catalogue=catalogue
        )
        by = {c.label: c for c in classes}
        assert by["oxygen_generation off"].classification == "HIGH"
        assert by["rover_charger off"].classification == "REDUNDANT"
        assert all(r.valid for r in rows)


class TestSearch:
    def test_protected_paths_are_refused(self) -> None:
        with pytest.raises(OverrideError, match="EVIDENCE_LOCKED"):
            SearchSpace((("life_support.water_recovery_nominal", (0.9,)),)).validate()
        with pytest.raises(OverrideError, match="protected"):
            SearchSpace((("events.minor_flare.trigger.probability_per_tick", (0.0,)),)).validate()

    def test_deviation_is_zero_for_the_shipped_values(self) -> None:
        assert deviation((("power.battery.capacity_kwh", 240.0),)) == 0.0
        assert deviation((("power.battery.capacity_kwh", 480.0),)) > 0.69

    def test_search_never_modifies_the_scenario_and_explains_its_ranking(self) -> None:
        before = SC.model_dump(mode="json")
        space = SearchSpace((("power.battery.capacity_kwh", (240.0, 160.0)),))
        screened, refined = run_search(space, seeds=(1, 2), refine_seeds=(), top=1)
        assert get_scenario("luna-01").model_dump(mode="json") == before
        assert len(screened) == 2 and not refined
        assert screened[0].score >= screened[1].score
        text = report_markdown(space, screened, refined)
        assert "not** modified" in text and "power.battery.capacity_kwh" in text
        assert len(ENVELOPES) == 13


class TestOverridesPhase3:
    def test_wildcard_and_scale(self) -> None:
        sc = apply_overrides(SC, [parse_override("degradation.components.*.wear_per_tick*=2")])
        for new, old in zip(sc.degradation.components, SC.degradation.components, strict=True):
            assert new.wear_per_tick == pytest.approx(2 * old.wear_per_tick)
        sc2 = apply_overrides(SC, [parse_override("degradation.components.*.fault_damage=0.2")])
        assert {c.fault_damage for c in sc2.degradation.components} == {0.2}


class TestProbeHygiene:
    @pytest.mark.parametrize(
        "strategy",
        [
            "survival_first",
            "science_first",
            "balanced",
            "power_conservative",
            "high_risk",
            "naive_beginner",
            "reserve_keeper",
            "expert",
        ],
    )
    def test_no_setting_flips_back_and_forth(self, eng: SimulationEngine, strategy: str) -> None:
        """Regression (Phase 3): two rules of one probe must not fight over the same control.

        power_conservative once set comms to eco every tick while its night plan set it off,
        flipping the mode 219 times in three missions.
        """
        run = run_mission(eng, strategy, 1)
        history: dict[str, list[tuple[int, object]]] = {}
        for d in run.decisions:
            inp = d.inputs
            if inp["type"] == "set_subsystem_mode":
                k, v = f"mode:{inp['subsystem']}", inp["mode"]
            elif inp["type"] == "set_thermal_setpoint":
                k, v = "setpoint", inp["target_c"]
            elif inp["type"] == "set_crew_location":
                k, v = "location", inp["location"]
            else:
                continue
            history.setdefault(k, []).append((d.tick, v))
        for k, seq in history.items():
            for (t0, a), (_, b), (t2, c) in zip(seq, seq[1:], seq[2:], strict=False):
                assert not (a == c != b and t2 - t0 <= 2), (strategy, k, t0)
