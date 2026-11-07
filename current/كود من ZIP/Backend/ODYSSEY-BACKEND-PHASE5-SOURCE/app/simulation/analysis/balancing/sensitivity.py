"""Bounded one-at-a-time sensitivity analysis and event ablation.

Sensitivity: vary ONE scenario parameter over a bounded list of values (everything else at
baseline), sweep strategies × seeds at each value, and report how outcomes, mission length,
resource minima and objective completion move.

Ablation: suppress ONE scenario event at a time and compare with the unmodified scenario —
answers "which events actually decide missions?".

Nothing here changes the shipped scenario; overrides live only inside the experiment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.simulation.scenarios.loader import get_scenario

from .aggregate import StrategySummary, summarize
from .overrides import get_path
from .sweep import SweepSpec, run_sweep

# Parameters that materially drive LUNA-01 outcomes (chosen from the energy, life-support,
# thermal, radiation and science paths). Values are bounded around the baseline; they are
# experiment points, NOT proposals. Centred on LUNA-01 v0.2.0 (battery 240 kWh, array 12 kW,
# 24 kg initial oxygen, cold penalty 0.0004), each list also reaching the v0.1.0 value.
DEFAULT_PARAMETERS: dict[str, tuple[float, ...]] = {
    "power.battery.capacity_kwh": (160.0, 200.0, 240.0, 280.0, 320.0),
    "power.solar_rated_kw": (9.0, 10.5, 12.0, 13.5, 15.0),
    "life_support.initial_oxygen_kg": (16.0, 20.0, 24.0, 32.0, 40.0),
    "crew_health.cold_penalty_per_k_tick": (0.0002, 0.0004, 0.0007, 0.001),
    "power.consumers.habitat_core.nominal_kw": (1.0, 1.25, 1.5, 1.75, 2.0),
    "power.consumers.oxygen_generation.nominal_kw": (0.75, 1.1, 1.5, 2.0, 2.5),
    "life_support.water_recovery_nominal": (0.80, 0.86, 0.93, 0.98),
    "food.initial_food_kg": (55.0, 62.0, 70.0, 80.0),
    "radiation.habitat_shielding_factor": (0.3, 0.45, 0.6, 0.8, 1.0),
    "objectives.radiation_safety.fail_when.value": (10.0, 12.5, 15.0, 20.0, 25.0),
    "thermal.conductance_kw_per_k": (0.010, 0.015, 0.020, 0.030, 0.040),
    "power.consumers.comms.nominal_kw": (0.2, 0.4, 0.8),
    "power.consumers.science_payload.nominal_kw": (0.6, 1.2, 1.8, 2.4),
    "events.solar_particle_event.trigger.at_tick": (60.0, 100.0, 122.0, 160.0, 200.0),
}
REPORT_FIELDS = (
    "battery_soc_min",
    "battery_zero_ticks",
    "oxygen_days_min",
    "water_days_min",
    "food_days_min",
    "habitat_temp_min",
    "crew_dose_max_msv",
    "crew_min_health",
    "science_points",
    "duration_ticks",
    "risk_final",
)


@dataclass(slots=True)
class SensitivityPoint:
    parameter: str
    value: Any
    is_baseline: bool
    summaries: list[StrategySummary]

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "is_baseline": self.is_baseline,
            "strategies": {s.strategy: _digest(s) for s in self.summaries},
        }


@dataclass(slots=True)
class SensitivityResult:
    parameter: str
    baseline: Any
    points: list[SensitivityPoint] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "baseline": self.baseline,
            "points": [p.as_dict() for p in self.points],
        }


def _digest(s: StrategySummary) -> dict[str, Any]:
    return {
        "missions": s.missions,
        "outcome_rates": s.outcome_rates,
        "battery_depletion_rate": s.battery_depletion_rate,
        "objective_rates": s.objective_rates,
        "median": {f: s.stats[f].p50 for f in REPORT_FIELDS},
        "mean": {f: s.stats[f].mean for f in REPORT_FIELDS},
    }


def _typed(value: float, baseline: Any) -> Any:
    return int(value) if isinstance(baseline, int) and not isinstance(baseline, bool) else value


def run_sensitivity(
    parameter: str,
    values: Sequence[float],
    *,
    scenario_id: str = "luna-01",
    strategies: Sequence[str] = ("balanced", "survival_first", "science_first"),
    seeds: Sequence[int] = tuple(range(1, 51)),
    workers: int = 1,
    progress: Callable[[str], None] | None = None,
) -> SensitivityResult:
    data = get_scenario(scenario_id).model_dump(mode="json", by_alias=True)
    baseline = get_path(data, parameter)
    result = SensitivityResult(parameter=parameter, baseline=baseline)
    ordered = sorted({*values, float(baseline)})
    for value in ordered:
        typed = _typed(value, baseline)
        spec = SweepSpec(
            scenario_id=scenario_id,
            strategies=tuple(strategies),
            seeds=tuple(seeds),
            overrides=((parameter, typed),),
        )
        res = run_sweep(spec, workers=workers)
        result.points.append(
            SensitivityPoint(parameter, typed, value == float(baseline), summarize(res.rows))
        )
        if progress is not None:
            progress(f"{parameter}={typed}")
    return result


@dataclass(slots=True)
class AblationRow:
    event_id: str
    strategy: str
    baseline: dict[str, Any]
    ablated: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "strategy": self.strategy,
            "baseline": self.baseline,
            "ablated": self.ablated,
        }


def run_ablation(
    *,
    scenario_id: str = "luna-01",
    strategies: Sequence[str] = ("balanced", "survival_first", "science_first", "passive"),
    seeds: Sequence[int] = tuple(range(1, 51)),
    events: Sequence[str] | None = None,
    workers: int = 1,
) -> list[AblationRow]:
    scenario = get_scenario(scenario_id)
    targets = (
        list(events)
        if events
        else [
            e.id
            for e in scenario.events
            if any(eff.type != "milestone" for eff in e.effects) and e.trigger.type != "decision"
        ]
    )
    base = {
        s.strategy: _digest(s)
        for s in summarize(
            run_sweep(
                SweepSpec(
                    scenario_id=scenario_id, strategies=tuple(strategies), seeds=tuple(seeds)
                ),
                workers=workers,
            ).rows
        )
    }
    rows: list[AblationRow] = []
    for event_id in targets:
        spec = SweepSpec(
            scenario_id=scenario_id,
            strategies=tuple(strategies),
            seeds=tuple(seeds),
            suppressed_events=(event_id,),
        )
        for s in summarize(run_sweep(spec, workers=workers).rows):
            rows.append(AblationRow(event_id, s.strategy, base[s.strategy], _digest(s)))
    return rows
