"""Balancing Lab: overrides, strategies, runner telemetry, sweeps, reports, impact, CLI."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from app.simulation.analysis.balancing import diagnostics
from app.simulation.analysis.balancing.__main__ import main
from app.simulation.analysis.balancing.aggregate import Stat, quantile, summarize
from app.simulation.analysis.balancing.impact import (
    Continuation,
    decision_impact,
    summarize_impact,
)
from app.simulation.analysis.balancing.overrides import (
    OverrideError,
    apply_overrides,
    get_path,
    parse_override,
)
from app.simulation.analysis.balancing.report import (
    mission_rows_csv,
    summary_rows_csv,
    sweep_json,
)
from app.simulation.analysis.balancing.runner import run_mission
from app.simulation.analysis.balancing.sensitivity import run_ablation, run_sensitivity
from app.simulation.analysis.balancing.strategies import (
    DIAGNOSTIC_PROBES,
    PROBE_STRATEGIES,
    make_strategy,
)
from app.simulation.analysis.balancing.sweep import SweepSpec, resolve_scenario_id, run_sweep
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario
from app.simulation.scenarios.schema import ScenarioDefinition

REQUIRED = {
    "survival_first",
    "science_first",
    "balanced",
    "power_conservative",
    "high_risk",
    "naive_beginner",
    "random_valid",
}


class TestOverrides:
    def test_parse(self) -> None:
        assert parse_override("a.b=1.5") == ("a.b", 1.5)
        assert parse_override("a=true") == ("a", True)
        assert parse_override("a=nominal") == ("a", "nominal")
        with pytest.raises(OverrideError):
            parse_override("no-equals")

    def test_paths_by_key_id_and_index(self, scenario: ScenarioDefinition) -> None:
        sc = apply_overrides(
            scenario,
            {
                "power.battery.capacity_kwh": 200.0,
                "power.consumers.habitat_core.nominal_kw": 1.2,
                "events.solar_particle_event.trigger.at_tick": 100,
                "objectives.radiation_safety.fail_when.value": 20.0,
                "environment.solar_availability.0.value": 0.9,
            },
        )
        assert sc.power.battery.capacity_kwh == 200.0
        assert sc.consumer("habitat_core").nominal_kw == 1.2
        spe = next(e for e in sc.events if e.id == "solar_particle_event")
        assert getattr(spe.trigger, "at_tick", None) == 100
        assert sc.environment.solar_availability[0].value == 0.9
        assert scenario.power.battery.capacity_kwh == 240.0  # shipped scenario untouched

    @pytest.mark.parametrize(
        ("path", "value"),
        [
            ("power.battery.nope", 1),
            ("power.consumers.warp_core.nominal_kw", 1),
            ("power.battery.capacity_kwh", -5),
            ("time.tick_hours", "soon"),
        ],
    )
    def test_invalid_overrides_rejected(
        self, scenario: ScenarioDefinition, path: str, value: object
    ) -> None:
        with pytest.raises(OverrideError):
            apply_overrides(scenario, {path: value})

    def test_get_path(self, scenario: ScenarioDefinition) -> None:
        data = scenario.model_dump(mode="json", by_alias=True)
        assert get_path(data, "power.consumers.comms.nominal_kw") == 0.4


class TestStrategies:
    def test_registry(self) -> None:
        assert set(PROBE_STRATEGIES) >= REQUIRED
        assert "passive" in PROBE_STRATEGIES
        assert set(DIAGNOSTIC_PROBES) == {"reserve_keeper", "always_shelter", "expert"}
        with pytest.raises(KeyError):
            make_strategy("telepathic", 1)
        assert make_strategy("Balanced", 1).name == "balanced"

    @pytest.mark.parametrize("name", [*PROBE_STRATEGIES, *DIAGNOSTIC_PROBES])
    def test_every_strategy_completes_with_invariants_and_is_deterministic(
        self, engine: SimulationEngine, name: str
    ) -> None:
        a = run_mission(engine, name, 7, check_invariants=True)
        b = run_mission(engine, name, 7, check_invariants=True)
        assert a.metrics == b.metrics
        assert a.final.state_hash() == b.final.state_hash()
        assert a.metrics.concluded and a.metrics.invariant_violations == 0
        assert a.metrics.decisions_rejected == 0  # strategies only propose valid decisions

    def test_random_valid_differs_by_seed_but_not_by_rerun(self, engine: SimulationEngine) -> None:
        runs = {seed: run_mission(engine, "random_valid", seed).decisions for seed in (1, 2)}
        assert runs[1] != runs[2]
        assert run_mission(engine, "random_valid", 1).decisions == runs[1]

    def test_strategies_cannot_see_the_future(self) -> None:
        """Strategy code never reads scenario events (fairness rule)."""
        import ast
        import inspect

        from app.simulation.analysis.balancing import strategies

        tree = ast.parse(inspect.getsource(strategies))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "events" not in attrs and "event_fire_counts" not in attrs

    def test_shelter_order_is_reissued_for_a_member_back_from_eva(
        self, engine: SimulationEngine
    ) -> None:
        """Regression: the probe used to treat "anyone in the shelter" as "everyone".

        A crew member on EVA is skipped by the shelter order and comes back to the habitat; the
        policy must re-issue the order for them while the dose rate is still high.
        """
        from app.simulation.analysis.balancing.strategies import Observation, shelter_policy
        from app.simulation.domain.enums import CrewLocation

        state = engine.initial_state(1).model_copy(deep=True)
        state.environment.radiation_dose_rate_msv_h = 5.0
        for member in state.crew:
            member.location = CrewLocation.SHELTER
        state.crew[0].location = CrewLocation.HABITAT  # just back from EVA
        obs = Observation(engine, state, 1)
        assert obs.anyone_sheltered() and not obs.sheltered()
        assert shelter_policy(obs) == [{"type": "set_crew_location", "location": "shelter"}]

        state.crew[0].location = CrewLocation.EVA  # still outside: nothing more to order
        assert obs.sheltered() and shelter_policy(obs) == []

        state.environment.radiation_dose_rate_msv_h = 0.057  # storm over: everyone returns
        assert shelter_policy(obs) == [{"type": "set_crew_location", "location": "habitat"}]


class TestRunnerTelemetry:
    def test_metrics_are_consistent(self, engine: SimulationEngine) -> None:
        run = run_mission(engine, "balanced", 1)
        m = run.metrics
        assert m.outcome_class == "success" and m.outcome == "mission_complete"
        assert m.duration_ticks == run.final.tick == 240
        assert m.ending_phase == "post_mission_analysis"
        assert 0.0 <= m.battery_soc_min <= m.battery_soc_final <= 1.0
        assert m.battery_zero_events <= m.battery_zero_ticks
        assert m.objectives_total == 10 == len(m.objectives)
        assert 0.0 <= m.science_completion <= 1.0
        assert m.decisions_accepted == len(run.decisions) == sum(m.decisions_by_type.values())
        assert m.crew_dose_max_msv == pytest.approx(
            engine.metrics.value("crew.max_dose_msv", run.final)
        )

    def test_recorded_decisions_replay_to_the_same_mission(self, engine: SimulationEngine) -> None:
        from app.simulation.replay.replay import replay

        run = run_mission(engine, "balanced", 5)
        res = replay(engine, run.initial, [d.to_replay() for d in run.decisions], run.final.tick)
        assert res.state.state_hash() == run.final.state_hash()

    def test_crew_loss_is_classified(self, engine: SimulationEngine) -> None:
        m = run_mission(engine, "high_risk", 2).metrics
        assert m.outcome_class == "crew_loss" and m.crew_incapacitated >= 1
        assert m.duration_ticks < 240


class TestSweepAndReports:
    def test_parallel_equals_serial(self) -> None:
        spec = SweepSpec(strategies=("balanced", "random_valid"), seeds=tuple(range(1, 9)))
        serial = run_sweep(spec, workers=1)
        parallel = run_sweep(spec, workers=2)
        assert [r.as_dict() for r in serial.rows] == [r.as_dict() for r in parallel.rows]
        assert [(r.strategy, r.seed) for r in serial.rows] == sorted(
            (r.strategy, r.seed) for r in serial.rows
        )

    def test_overrides_and_suppression_flow_through(self) -> None:
        spec = SweepSpec(
            strategies=("passive",),
            seeds=(1, 2),
            overrides=(("power.battery.capacity_kwh", 400.0),),
            suppressed_events=("solar_particle_event",),
        )
        rows = run_sweep(spec).rows
        assert all(r.overrides == {"power.battery.capacity_kwh": 400.0} for r in rows)
        assert all(r.crew_dose_max_msv < 15 for r in rows)  # no SPE

    def test_summary_rates_and_reports(self) -> None:
        res = run_sweep(SweepSpec(strategies=("passive", "balanced"), seeds=(1, 2, 3)))
        summaries = summarize(res.rows)
        for s in summaries:
            assert sum(s.outcome_rates.values()) == pytest.approx(1.0)
            assert s.missions == 3
        doc = sweep_json(res)
        text = json.dumps(doc, allow_nan=False)
        assert json.loads(text)["seed_count"] == 3 and len(doc["missions"]) == 6
        rows = list(csv.DictReader(io.StringIO(mission_rows_csv(res.rows))))
        assert len(rows) == 6 and rows[0]["objective.crew_survival"] == "achieved"
        srows = list(csv.DictReader(io.StringIO(summary_rows_csv(summaries))))
        assert [r["strategy"] for r in srows] == ["balanced", "passive"]

    def test_stats(self) -> None:
        assert quantile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
        s = Stat.of([5, 1, 3])
        assert (s.min, s.p50, s.max, s.mean) == (1.0, 3.0, 5.0, 3.0)

    def test_scenario_name_resolution(self) -> None:
        assert resolve_scenario_id("luna01") == resolve_scenario_id("LUNA-01") == "luna-01"
        with pytest.raises(KeyError):
            resolve_scenario_id("mars01")


class TestImpactSensitivityAblation:
    @pytest.mark.parametrize("continuation", ["replay", "strategy"])
    def test_identity_fork_reproduces_baseline(
        self, engine: SimulationEngine, continuation: Continuation
    ) -> None:
        rows = decision_impact(
            engine,
            "balanced",
            1,
            alternatives=lambda d: [dict(d.inputs)],
            continuation=continuation,
        )
        assert rows and all(r.no_effect and not r.outcome_changed for r in rows)

    def test_omitting_shelter_raises_dose(self, engine: SimulationEngine) -> None:
        rows = decision_impact(
            engine,
            "balanced",
            1,
            continuation="replay",
            select=lambda d: d.inputs.get("location") == "shelter",
        )
        # Every shelter order lowers the dose; the one at the solar particle event decides the
        # radiation objective (v0.2.0 balanced play also shelters for its dose budget).
        assert rows and all(r.deltas["crew_dose_max_msv"] > 0.0 for r in rows)
        assert max(r.deltas["crew_dose_max_msv"] for r in rows) > 5.0
        assert any("radiation_safety" in r.objectives_changed["lost"] for r in rows)
        summary = summarize_impact(rows)[0]
        assert summary.no_effect_rate == 0.0 and summary.forks == len(rows)

    def test_sensitivity_includes_baseline(self) -> None:
        res = run_sensitivity(
            "power.battery.capacity_kwh", [250.0], strategies=("passive",), seeds=(1, 2)
        )
        values = [p.value for p in res.points]
        assert values == [240.0, 250.0] and res.points[0].is_baseline
        doc = res.as_dict()
        assert doc["points"][1]["strategies"]["passive"]["missions"] == 2

    def test_ablation_rows(self) -> None:
        rows = run_ablation(strategies=("passive",), seeds=(1, 2), events=["solar_particle_event"])
        assert len(rows) == 1
        assert (
            rows[0].ablated["median"]["crew_dose_max_msv"]
            < rows[0].baseline["median"]["crew_dose_max_msv"]
        )


class TestDiagnostics:
    def test_detectors_fire_on_known_patterns(self, scenario: ScenarioDefinition) -> None:
        res = run_sweep(SweepSpec(strategies=("passive", "balanced"), seeds=(1, 3)))
        summaries = summarize(res.rows)
        found = {
            (f.detector, f.subject)
            for f in [
                *diagnostics.objectives(summaries),
                *diagnostics.outcomes(scenario, res.rows),
                *diagnostics.alerts(scenario, summaries),
                *diagnostics.systems(summaries),
            ]
        }
        assert ("objective_never_achieved", "reserves_at_end") in found
        assert ("objective_always_achieved", "crew_survival") in found
        assert ("alert_never_fires", "oxygen_critical") in found
        # v0.2.0: passive play reaches mission_failed, so the fallback is no longer unreachable.
        assert ("outcome_unreachable", "mission_failed") not in found
        assert ("outcome_unreachable", "mission_failed_crew_loss") in found


class TestCli:
    def test_sweep_formats(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert (
            main(
                ["--scenario", "luna01", "--strategy", "passive", "--seeds", "2", "--workers", "1"]
            )
            == 0
        )
        assert "Strategy: PASSIVE" in capsys.readouterr().out
        out = tmp_path / "s.json"
        assert (
            main(
                [
                    "sweep",
                    "--strategy",
                    "passive,balanced",
                    "--seeds",
                    "2",
                    "--workers",
                    "1",
                    "--format",
                    "json",
                    "--output",
                    str(out),
                    "--strict",
                ]
            )
            == 0
        )
        assert len(json.loads(out.read_text())["missions"]) == 4
        csv_out = tmp_path / "m.csv"
        assert (
            main(
                [
                    "sweep",
                    "--strategy",
                    "passive",
                    "--seeds",
                    "2",
                    "--workers",
                    "1",
                    "--set",
                    "power.battery.capacity_kwh=300",
                    "--format",
                    "csv",
                    "--output",
                    str(csv_out),
                ]
            )
            == 0
        )
        assert '"power.battery.capacity_kwh"": 300' in csv_out.read_text()

    def test_analysis_commands(self, tmp_path: Path) -> None:
        sens = tmp_path / "sens.json"
        assert (
            main(
                [
                    "sensitivity",
                    "--parameter",
                    "power.solar_rated_kw",
                    "--values",
                    "13",
                    "--strategy",
                    "passive",
                    "--seeds",
                    "1",
                    "--workers",
                    "1",
                    "--output",
                    str(sens),
                ]
            )
            == 0
        )
        assert json.loads(sens.read_text())["results"][0]["parameter"] == "power.solar_rated_kw"
        imp = tmp_path / "imp.json"
        assert (
            main(
                [
                    "impact",
                    "--strategy",
                    "balanced",
                    "--seeds",
                    "1",
                    "--continuation",
                    "replay",
                    "--output",
                    str(imp),
                ]
            )
            == 0
        )
        assert json.loads(imp.read_text())["summaries"]
        abl = tmp_path / "abl.json"
        assert (
            main(
                [
                    "ablation",
                    "--strategy",
                    "passive",
                    "--seeds",
                    "1",
                    "--event",
                    "relay_outage",
                    "--workers",
                    "1",
                    "--output",
                    str(abl),
                ]
            )
            == 0
        )
        assert json.loads(abl.read_text())["rows"][0]["event_id"] == "relay_outage"

    def test_bad_input(self) -> None:
        with pytest.raises(KeyError):
            main(["--strategy", "nope", "--seeds", "1", "--workers", "1"])
        with pytest.raises(OverrideError):
            main(
                ["--strategy", "passive", "--seeds", "1", "--workers", "1", "--set", "power.nope=1"]
            )


def test_shipped_scenario_is_never_modified_by_the_lab() -> None:
    before = get_scenario("luna-01").model_dump(mode="json")
    run_sweep(
        SweepSpec(
            strategies=("passive",), seeds=(1,), overrides=(("power.battery.capacity_kwh", 1.0),)
        )
    )
    assert get_scenario("luna-01").model_dump(mode="json") == before
