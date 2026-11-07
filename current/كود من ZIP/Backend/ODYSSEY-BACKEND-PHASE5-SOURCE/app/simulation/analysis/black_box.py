"""Black Box: post-mission (or mid-mission) flight-recorder report.

Everything in the report is derived from a deterministic reconstruction (initial state +
ledger + engine). Causal traces are produced by :mod:`root_cause` for:

* every *critical* alert (first occurrence per alert id), and
* crew loss (traced from ``crew.min_health``), or the peak of ``risk.mission`` otherwise;
* every failed objective, through :mod:`outcome_analysis` (root decision verified by
  counterfactual replay, intermediate effects, triggering condition, consequence).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.analysis.outcome_analysis import OutcomeAnalysis, analyse_outcome
from app.simulation.analysis.reconstruct import MissionRecord
from app.simulation.analysis.root_cause import Counterfactual, RootCauseTrace, trace_root_cause
from app.simulation.domain.enums import AlertSeverity, EventKind
from app.simulation.domain.state import OutcomeState
from app.simulation.engine.engine import SimulationEngine

TREND_METRICS = (
    "power.battery_soc",
    "power.generation_kw",
    "power.demand_kw",
    "thermal.habitat_temp_c",
    "life_support.oxygen_days",
    "life_support.co2_ppm",
    "life_support.water_days",
    "food.food_days",
    "crew.min_health",
    "crew.max_dose_msv",
    "science.points",
    "comms.data_downlinked_mb",
    "risk.mission",
)

_FAILURE_KINDS = {EventKind.SYSTEM_FAULT}
_FAILURE_KEY_PREFIXES = ("crew_incapacitated", "rover_lost")
_MILESTONE_KINDS = {EventKind.MILESTONE, EventKind.OBJECTIVE, EventKind.SCIENCE_OPPORTUNITY}


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tick: int
    category: str
    kind: str
    key: str
    severity: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DecisionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    sequence: int
    tick: int
    phase: str
    decision_type: str
    inputs: dict[str, Any]
    affected_systems: list[str]


class TrendSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    unit: str
    label: str
    ticks: list[int]
    values: list[float]
    min_value: float
    min_tick: int
    max_value: float
    max_tick: int


class BlackBoxReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    scenario_version: str
    final_tick: int
    status: str
    phase: str
    outcome: OutcomeState | None
    decisions: list[DecisionSummary]
    timeline: list[TimelineEntry]
    alerts: list[TimelineEntry]
    failures: list[TimelineEntry]
    milestones: list[TimelineEntry]
    phase_transitions: list[TimelineEntry]
    resource_trends: list[TrendSeries]
    causal_traces: list[RootCauseTrace]
    outcome_analysis: OutcomeAnalysis | None = None
    final_state_hash: str


def _category(kind: EventKind, key: str) -> str:
    if kind in (
        EventKind.ALERT_RAISED,
        EventKind.RESOURCE_WARNING,
        EventKind.ALERT_CLEARED,
        EventKind.CASCADE_WARNING,
    ):
        return "alert"
    if kind in _FAILURE_KINDS or key.startswith(_FAILURE_KEY_PREFIXES):
        return "failure"
    if kind == EventKind.PHASE_CHANGE:
        return "phase"
    if kind == EventKind.DECISION_APPLIED:
        return "decision"
    if kind == EventKind.OUTCOME:
        return "outcome"
    if kind in _MILESTONE_KINDS:
        return "milestone"
    return "event"


def build_black_box(
    engine: SimulationEngine,
    record: MissionRecord,
    *,
    trend_stride: int = 4,
    max_traces: int = 6,
    counterfactual: Counterfactual | None = None,
) -> BlackBoxReport:
    final = record.final_state
    history = record.history
    timeline = [
        TimelineEntry(
            tick=e.tick,
            category=_category(e.kind, e.key),
            kind=e.kind.value,
            key=e.key,
            severity=e.severity.value if e.severity else None,
            data=e.data,
        )
        for e in record.events
    ]

    def pick(cat: str) -> list[TimelineEntry]:
        return [t for t in timeline if t.category == cat]

    trends: list[TrendSeries] = []
    last = len(history) - 1
    idxs = sorted(set(range(0, len(history), max(1, trend_stride))) | {last})
    for metric in TREND_METRICS:
        spec = engine.metrics.spec(metric)
        all_values = [engine.metrics.value(metric, s) for s in history]
        min_i = min(range(len(all_values)), key=lambda i: (all_values[i], i))
        max_i = max(range(len(all_values)), key=lambda i: (all_values[i], -i))
        trends.append(
            TrendSeries(
                metric=metric,
                unit=spec.unit,
                label=spec.label,
                ticks=[history[i].tick for i in idxs],
                values=[all_values[i] for i in idxs],
                min_value=all_values[min_i],
                min_tick=history[min_i].tick,
                max_value=all_values[max_i],
                max_tick=history[max_i].tick,
            )
        )

    targets: list[tuple[str, int]] = []
    seen_alerts: set[str] = set()
    alert_rules = {a.id: a for a in engine.scenario.alerts}
    for e in record.events:
        if (
            e.kind in (EventKind.ALERT_RAISED, EventKind.RESOURCE_WARNING)
            and e.severity == AlertSeverity.CRITICAL
            and e.key not in seen_alerts
        ):
            seen_alerts.add(e.key)
            targets.append((alert_rules[e.key].metric, min(e.tick + 1, final.tick)))
    crew_lost = engine.metrics.value("crew.min_health", final) <= 0.0
    if final.outcome is not None and final.outcome.code.startswith("mission_failed") and crew_lost:
        targets.insert(0, ("crew.min_health", final.tick))
    elif len(history) > 1:
        risk = [engine.metrics.value("risk.mission", s) for s in history]
        peak = max(range(len(risk)), key=lambda i: (risk[i], -i))
        if risk[peak] >= 0.2:
            targets.append(("risk.mission", history[peak].tick))

    traces: list[RootCauseTrace] = []
    seen_targets: set[tuple[str, int]] = set()
    for metric, tick in targets:
        if (metric, tick) in seen_targets or len(traces) >= max_traces:
            continue
        seen_targets.add((metric, tick))
        traces.append(
            trace_root_cause(
                engine,
                history,
                metric,
                tick,
                start_tick=history[0].tick,
                decision_info=record.decision_info(),
                counterfactual=counterfactual,
            )
        )

    analysis = analyse_outcome(
        engine,
        list(history),
        list(record.events),
        record.decision_info(),
        counterfactual=counterfactual,
        traces=traces,
    )

    return BlackBoxReport(
        scenario_id=final.scenario_id,
        scenario_version=final.scenario_version,
        final_tick=final.tick,
        status=final.status.value,
        phase=final.phase,
        outcome=final.outcome,
        decisions=[
            DecisionSummary(
                decision_id=r.decision_id,
                sequence=r.sequence,
                tick=r.tick,
                phase=r.phase,
                decision_type=r.decision_type,
                inputs=r.inputs,
                affected_systems=list(r.affected_systems),
            )
            for r in record.records
        ],
        timeline=timeline,
        alerts=pick("alert"),
        failures=pick("failure")
        + [t for t in pick("outcome") if t.key.startswith("mission_failed")],
        milestones=pick("milestone"),
        phase_transitions=pick("phase"),
        resource_trends=trends,
        causal_traces=traces,
        outcome_analysis=analysis,
        final_state_hash=final.state_hash(),
    )
