"""Per-tick resource trajectories of one mission (backend-only CSV/JSON exports, no charts).

A trajectory is produced by playing a mission with a strategy (or replaying recorded
decisions), then reading every tick of the reconstructed history. Each row is one tick *after*
it was simulated, with the decisions applied at that tick and the notable events it produced.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.simulation.domain.enums import EventKind
from app.simulation.domain.events import MissionEvent
from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.replay import replay

from .runner import MissionRun, run_mission

# Metric columns, in order: (column name, metric id).
COLUMNS: tuple[tuple[str, str], ...] = (
    ("hours", "time.hours"),
    ("solar_availability", "env.solar_availability"),
    ("generation_kw", "power.generation_kw"),
    ("demand_kw", "power.demand_kw"),
    ("unmet_kw", "power.unmet_kw"),
    ("battery_kwh", "power.battery_charge_kwh"),
    ("battery_soc", "power.battery_soc"),
    ("oxygen_kg", "life_support.oxygen_kg"),
    ("oxygen_days", "life_support.oxygen_days"),
    ("co2_ppm", "life_support.co2_ppm"),
    ("water_kg", "life_support.water_kg"),
    ("water_days", "life_support.water_days"),
    ("food_kg", "food.food_kg"),
    ("food_days", "food.food_days"),
    ("habitat_temp_c", "thermal.habitat_temp_c"),
    ("sink_temp_c", "env.sink_temp_c"),
    ("dose_rate_msv_h", "env.radiation_dose_rate_msv_h"),
    ("received_dose_rate_msv_h", "crew.received_dose_rate_msv_h"),
    ("max_dose_msv", "crew.max_dose_msv"),
    ("min_health", "crew.min_health"),
    ("science_points", "science.points"),
    ("science_completed", "science.opportunities_completed"),
    ("data_downlinked_mb", "comms.data_downlinked_mb"),
    ("link_up", "comms.link_up"),
    ("rover_battery_kwh", "rover.battery_kwh"),
    ("risk", "risk.mission"),
)
# Included only when the scenario defines the metric (e.g. a mission dose limit, v0.2.0).
OPTIONAL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("projected_dose_margin_msv", "crew.projected_dose_margin_msv"),
)
# Event kinds worth listing per tick (alerts are listed only when raised).
MAJOR_EVENT_KINDS = {
    EventKind.SPACE_WEATHER,
    EventKind.SYSTEM_FAULT,
    EventKind.COMMUNICATION,
    EventKind.SCIENCE_OPPORTUNITY,
    EventKind.MILESTONE,
    EventKind.OBJECTIVE,
    EventKind.OUTCOME,
    EventKind.PHASE_CHANGE,
    EventKind.MAINTENANCE,
    EventKind.ALERT_RAISED,
    EventKind.RESOURCE_WARNING,
    EventKind.ROVER,
}


@dataclass(slots=True)
class Trajectory:
    label: str
    strategy: str
    seed: int
    outcome: str
    outcome_class: str
    rows: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "strategy": self.strategy,
            "seed": self.seed,
            "outcome": self.outcome,
            "outcome_class": self.outcome_class,
            "rows": self.rows,
        }

    def to_csv(self) -> str:
        if not self.rows:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(self.rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in self.rows:
            writer.writerow(
                {k: (";".join(v) if isinstance(v, list) else v) for k, v in row.items()}
            )
        return buf.getvalue()


def _event_label(e: MissionEvent) -> str:
    return f"{e.kind.value}:{e.key}"


def build_trajectory(
    engine: SimulationEngine,
    run: MissionRun,
    *,
    label: str | None = None,
    options: RunOptions | None = None,
) -> Trajectory:
    """Reconstruct ``run`` tick by tick from its recorded decisions."""
    seed = run.metrics.seed
    decisions = [d.to_replay() for d in run.decisions]
    final_tick = run.metrics.duration_ticks
    res = replay(
        engine,
        engine.initial_state(seed),
        decisions,
        final_tick,
        record_history=True,
        options=options,
    )
    by_tick_decisions: dict[int, list[str]] = defaultdict(list)
    for d in run.decisions:
        inputs = {k: v for k, v in d.inputs.items() if k != "type" and v is not None}
        args = ",".join(f"{k}={inputs[k]}" for k in sorted(inputs))
        by_tick_decisions[d.tick].append(f"{d.inputs['type']}({args})")
    by_tick_events: dict[int, list[str]] = defaultdict(list)
    for e in res.events:
        if e.kind in MAJOR_EVENT_KINDS:
            by_tick_events[e.tick].append(_event_label(e))
    m = engine.metrics
    rows: list[dict[str, Any]] = []
    for st in res.history:
        sim_tick = st.tick - 1  # events/decisions of the tick that produced this state
        row: dict[str, Any] = {"tick": st.tick, "phase": st.phase}
        for col, metric in COLUMNS:
            row[col] = round(m.value(metric, st), 6)
        for col, metric in OPTIONAL_COLUMNS:
            if m.has(metric):
                row[col] = round(m.value(metric, st), 6)
        row["active_science"] = st.science.active_opportunity or ""
        row["crew_locations"] = ",".join(sorted({c.location.value for c in st.crew}))
        row["alerts"] = sorted(st.alerts)
        row["decisions"] = by_tick_decisions.get(sim_tick, [])
        row["events"] = by_tick_events.get(sim_tick, [])
        rows.append(row)
    return Trajectory(
        label=label or f"{run.metrics.strategy}:{seed}",
        strategy=run.metrics.strategy,
        seed=seed,
        outcome=run.metrics.outcome,
        outcome_class=run.metrics.outcome_class,
        rows=rows,
    )


def play_trajectory(
    engine: SimulationEngine, strategy: str, seed: int, *, label: str | None = None
) -> Trajectory:
    return build_trajectory(engine, run_mission(engine, strategy, seed), label=label)


# Representative missions (Phase 3 brief §25): (label, strategy, accepted outcome classes).
# The first seed (from 1 upward) whose outcome class matches is exported, so the selection is
# deterministic and reproducible.
REPRESENTATIVE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("balanced_success", "balanced", ("success", "exceptional")),
    ("science_heavy_success", "expert", ("exceptional", "success")),
    ("survival_first_success", "survival_first", ("success", "exceptional")),
    # Phase 3 brief asks for a survival-first *partial*; in v0.2.0 survival-first never ends
    # partial, its non-success mode is mission_failed (science campaigns not completed).
    ("survival_first_science_sacrificed", "survival_first", ("partial", "failure")),
    ("beginner_recovery", "naive_beginner", ("partial",)),
    ("high_risk_failure", "high_risk", ("crew_loss", "failure")),
    ("passive_mission_failure", "passive", ("failure",)),
    ("random_failure", "random_valid", ("crew_loss", "failure")),
)


def representative_trajectories(
    engine: SimulationEngine, *, max_seed: int = 200
) -> list[Trajectory]:
    out: list[Trajectory] = []
    for label, strategy, classes in REPRESENTATIVE:
        for seed in range(1, max_seed + 1):
            run = run_mission(engine, strategy, seed)
            if run.metrics.outcome_class in classes:
                out.append(build_trajectory(engine, run, label=f"{label}:{strategy}:{seed}"))
                break
    return out
