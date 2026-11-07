"""Outcome distributions and summary statistics per strategy."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .runner import MissionMetrics

OUTCOME_CLASSES = ("exceptional", "success", "partial", "failure", "crew_loss")
# Full success or better (what "success rate" means in reports).
SUCCESS_CLASSES = ("exceptional", "success")
NUMERIC_FIELDS = (
    "duration_ticks",
    "battery_soc_min",
    "battery_soc_final",
    "battery_zero_ticks",
    "load_shed_ticks",
    "unmet_energy_kwh",
    "water_days_min",
    "water_days_final",
    "oxygen_days_min",
    "oxygen_days_final",
    "food_days_min",
    "co2_ppm_max",
    "habitat_temp_min",
    "cold_ticks",
    "crew_dose_max_msv",
    "crew_min_health",
    "science_points",
    "science_completion",
    "data_downlinked_mb",
    "objectives_achieved",
    "critical_alerts",
    "cascade_warnings",
    "comms_outage_ticks",
    "random_faults",
    "maintenance_completed",
    "rover_traverses",
    "risk_final",
    "risk_peak",
    "decisions_accepted",
    "decisions_rejected",
)


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Nearest-rank quantile on pre-sorted data (deterministic, no interpolation)."""
    if not sorted_values:
        return float("nan")
    idx = min(len(sorted_values) - 1, max(0, round(q * (len(sorted_values) - 1))))
    return float(sorted_values[idx])


@dataclass(frozen=True, slots=True)
class Stat:
    mean: float
    min: float
    p10: float
    p50: float
    p90: float
    max: float

    @classmethod
    def of(cls, values: Sequence[float]) -> Stat:
        v = sorted(float(x) for x in values)
        return cls(
            mean=sum(v) / len(v),
            min=v[0],
            p10=quantile(v, 0.1),
            p50=quantile(v, 0.5),
            p90=quantile(v, 0.9),
            max=v[-1],
        )


@dataclass(slots=True)
class StrategySummary:
    strategy: str
    missions: int
    outcome_rates: dict[str, float]
    success_rate: float
    outcome_codes: dict[str, int]
    battery_depletion_rate: float
    crew_incapacitation_rate: float
    rover_loss_rate: float
    objective_rates: dict[str, float]
    science_goal_rate: float
    radiation_goal_rate: float
    distinct_final_states: int
    alert_rates: dict[str, float]
    stats: dict[str, Stat] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "missions": self.missions,
            "outcome_rates": self.outcome_rates,
            "success_rate": self.success_rate,
            "outcome_codes": self.outcome_codes,
            "battery_depletion_rate": self.battery_depletion_rate,
            "crew_incapacitation_rate": self.crew_incapacitation_rate,
            "rover_loss_rate": self.rover_loss_rate,
            "objective_rates": self.objective_rates,
            "science_goal_rate": self.science_goal_rate,
            "radiation_goal_rate": self.radiation_goal_rate,
            "distinct_final_states": self.distinct_final_states,
            "alert_rates": self.alert_rates,
            "stats": {k: vars_of(s) for k, s in self.stats.items()},
        }


def vars_of(stat: Stat) -> dict[str, float]:
    return {
        "mean": stat.mean,
        "min": stat.min,
        "p10": stat.p10,
        "p50": stat.p50,
        "p90": stat.p90,
        "max": stat.max,
    }


def _fingerprint(r: MissionMetrics) -> tuple[Any, ...]:
    """Coarse identity of a mission's result (to count how many distinct outcomes seeds give)."""
    return (
        r.outcome,
        r.duration_ticks,
        round(r.crew_dose_max_msv, 6),
        round(r.science_points, 6),
        round(r.battery_soc_final, 6),
        round(r.crew_min_health, 6),
        tuple(sorted(r.objectives.items())),
    )


def summarize(rows: Iterable[MissionMetrics]) -> list[StrategySummary]:
    groups: dict[str, list[MissionMetrics]] = defaultdict(list)
    for r in rows:
        groups[r.strategy].append(r)
    out: list[StrategySummary] = []
    for name in sorted(groups):
        rs = groups[name]
        n = len(rs)
        classes = Counter(r.outcome_class for r in rs)
        objectives: dict[str, int] = Counter()
        for r in rs:
            for oid, status in r.objectives.items():
                objectives[oid] += status == "achieved"
        objective_ids = sorted({oid for r in rs for oid in r.objectives})
        alerts: Counter[str] = Counter()
        for r in rs:
            alerts.update(dict.fromkeys(r.alerts_raised, 1))
        obj_rates = {oid: objectives[oid] / n for oid in objective_ids}
        out.append(
            StrategySummary(
                strategy=name,
                missions=n,
                outcome_rates={c: classes[c] / n for c in OUTCOME_CLASSES},
                success_rate=sum(classes[c] for c in SUCCESS_CLASSES) / n,
                outcome_codes=dict(sorted(Counter(r.outcome for r in rs).items())),
                battery_depletion_rate=sum(1 for r in rs if r.battery_zero_events > 0) / n,
                crew_incapacitation_rate=sum(1 for r in rs if r.crew_incapacitated > 0) / n,
                rover_loss_rate=sum(1 for r in rs if r.rover_lost) / n,
                objective_rates=obj_rates,
                science_goal_rate=obj_rates.get("science_return", 0.0),
                radiation_goal_rate=obj_rates.get("radiation_safety", 0.0),
                distinct_final_states=len({_fingerprint(r) for r in rs}),
                alert_rates={k: v / n for k, v in sorted(alerts.items())},
                stats={f: Stat.of([float(getattr(r, f)) for r in rs]) for f in NUMERIC_FIELDS},
            )
        )
    return out


def _pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def format_summary(summary: StrategySummary) -> str:
    """Human-readable block in the shape the Phase 2 brief asks for."""
    s = summary
    lines = [
        f"Strategy: {s.strategy.upper()}  ({s.missions} missions, "
        f"{s.distinct_final_states} distinct results)",
        f"  Exceptional success:     {_pct(s.outcome_rates['exceptional'])}",
        f"  Success:                 {_pct(s.outcome_rates['success'])}",
        f"  Partial success:         {_pct(s.outcome_rates['partial'])}",
        f"  Mission failed:          {_pct(s.outcome_rates['failure'])}",
        f"  Critical failure (crew): {_pct(s.outcome_rates['crew_loss'])}",
        f"  Battery depletion:       {_pct(s.battery_depletion_rate)}",
        f"  Science goal achieved:   {_pct(s.science_goal_rate)}",
        f"  Radiation goal achieved: {_pct(s.radiation_goal_rate)}",
    ]
    for oid, rate in s.objective_rates.items():
        if oid not in ("science_return", "radiation_safety"):
            lines.append(f"  Objective {oid + ':':22}{_pct(rate)}")
    st = s.stats
    lines.append(
        f"  Dose max mSv  p10/p50/p90: {st['crew_dose_max_msv'].p10:.1f} / "
        f"{st['crew_dose_max_msv'].p50:.1f} / {st['crew_dose_max_msv'].p90:.1f}"
    )
    lines.append(
        f"  Science pts   p10/p50/p90: {st['science_points'].p10:.1f} / "
        f"{st['science_points'].p50:.1f} / {st['science_points'].p90:.1f}"
    )
    lines.append(
        f"  Min crew health p10/p50:   {st['crew_min_health'].p10:.2f} / "
        f"{st['crew_min_health'].p50:.2f}"
    )
    lines.append(
        f"  Battery SOC min / end p50: {st['battery_soc_min'].p50:.2f} / "
        f"{st['battery_soc_final'].p50:.2f}"
    )
    return "\n".join(lines)
