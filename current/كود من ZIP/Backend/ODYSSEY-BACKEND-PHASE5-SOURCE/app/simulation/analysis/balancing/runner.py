"""Run one mission with a scripted strategy and collect balancing telemetry.

No HTTP, database or ledger hashing: the engine is driven directly. Every decision the
strategy makes goes through the same ``SimulationEngine.apply_decision`` validation a player's
would, and accepted decisions are kept (with ids and ticks) so any run can be replayed or forked
by :mod:`app.simulation.analysis.replay`-based tools.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.enums import (
    AlertSeverity,
    EventKind,
    MissionStatus,
    ObjectiveStatus,
    RoverStatus,
)
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine
from app.simulation.engine.invariants import InvariantViolationError, check_state
from app.simulation.replay.replay import ReplayDecision

from .strategies import Observation, Strategy, make_strategy

# Outcome class per scenario outcome tier (OutcomeRule.effective_tier).
TIER_CLASS = {
    "exceptional": "exceptional",
    "success": "success",
    "partial": "partial",
    "mission_failed": "failure",
    "critical_failure": "crew_loss",
}
# Codes of scenarios that declare no tiers (v0.1.0).
OUTCOME_CLASS = {
    "mission_complete": "success",
    "mission_complete_partial": "partial",
    "mission_failed": "failure",
    "mission_failed_crew_loss": "crew_loss",
}


def outcome_class(engine: SimulationEngine, state: MissionState) -> str:
    if state.outcome is None:
        return "in_progress"
    try:
        tier = engine.scenario.outcome_rule(state.outcome.rule_id).effective_tier
    except KeyError:
        tier = None
    if tier is not None:
        return TIER_CLASS[tier]
    return OUTCOME_CLASS.get(state.outcome.code, "in_progress")


EMPTY_KWH = 1e-6


@dataclass(frozen=True, slots=True)
class AppliedDecision:
    decision_id: str
    sequence: int
    tick: int
    inputs: dict[str, Any]

    def to_replay(self) -> ReplayDecision:
        return ReplayDecision(
            self.decision_id, self.sequence, self.tick, parse_decision(self.inputs)
        )


@dataclass(slots=True)
class MissionMetrics:
    """One row of balancing data. Flat scalars (CSV-friendly) plus a few small dicts."""

    scenario_id: str
    strategy: str
    seed: int
    outcome: str
    outcome_class: str
    ending_phase: str
    concluded: bool
    duration_ticks: int
    duration_hours: float
    # power
    battery_soc_min: float
    battery_soc_final: float
    battery_kwh_final: float
    battery_zero_events: int
    battery_zero_ticks: int
    load_shed_ticks: int
    unmet_energy_kwh: float
    # life support / food
    oxygen_days_min: float
    oxygen_kg_min: float
    water_days_min: float
    water_kg_min: float
    food_days_min: float
    food_kg_min: float
    oxygen_days_final: float
    water_days_final: float
    food_days_final: float
    co2_ppm_max: float
    # thermal
    habitat_temp_min: float
    cold_ticks: int
    processor_cold_ticks: int
    # crew
    crew_dose_max_msv: float
    crew_min_health: float
    crew_min_health_final: float
    crew_incapacitated: int
    # science
    science_points: float
    science_completed: int
    science_opportunities: int
    science_completion: float
    data_downlinked_mb: float
    # objectives
    objectives_achieved: int
    objectives_total: int
    # events and alerts
    emergency_events: int
    critical_alerts: int
    warning_alerts: int
    cascade_warnings: int
    comms_outage_events: int
    comms_outage_ticks: int
    space_weather_events: int
    random_faults: int
    scripted_faults: int
    maintenance_completed: int
    rover_traverses: int
    rover_successes: int
    rover_lost: bool
    risk_final: float
    risk_peak: float
    # decisions
    decisions_accepted: int
    decisions_rejected: int
    invariant_violations: int
    objectives: dict[str, str] = field(default_factory=dict)
    alerts_raised: dict[str, int] = field(default_factory=dict)
    decisions_by_type: dict[str, int] = field(default_factory=dict)
    rejections_by_code: dict[str, int] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MissionRun:
    metrics: MissionMetrics
    initial: MissionState
    final: MissionState
    decisions: list[AppliedDecision]
    events: list[MissionEvent]


class _Telemetry:
    """Streaming accumulator: sees every state after each step (and the initial one)."""

    def __init__(self, engine: SimulationEngine) -> None:
        self.e = engine
        self.m = engine.metrics
        sc = engine.scenario
        self.cold_c = sc.crew_health.cold_threshold_c
        self.processor_min_c = sc.life_support.water_recovery_min_temp_c
        self.dt = sc.time.tick_hours
        self.inf = math.inf
        self.mins: dict[str, float] = {}
        self.maxs: dict[str, float] = {}
        self.battery_empty = False
        self.counts: Counter[str] = Counter()

    def _min(self, key: str, value: float) -> None:
        self.mins[key] = min(self.mins.get(key, self.inf), value)

    def _max(self, key: str, value: float) -> None:
        self.maxs[key] = max(self.maxs.get(key, -self.inf), value)

    def observe(self, s: MissionState, stepped: bool) -> None:
        m = self.m
        soc = m.value("power.battery_soc", s)
        self._min("soc", soc)
        for name in (
            "life_support.oxygen_days",
            "life_support.water_days",
            "food.food_days",
            "crew.min_health",
            "thermal.habitat_temp_c",
        ):
            self._min(name, m.value(name, s))
        self._min("oxygen_kg", s.life_support.oxygen_kg)
        self._min("water_kg", s.life_support.water_kg)
        self._min("food_kg", s.food.food_kg)
        self._max("co2", m.value("life_support.co2_ppm", s))
        self._max("risk", m.value("risk.mission", s))
        if not stepped:
            return
        empty = s.power.battery_charge_kwh <= EMPTY_KWH
        if empty:
            self.counts["battery_zero_ticks"] += 1
            if not self.battery_empty:
                self.counts["battery_zero_events"] += 1
        self.battery_empty = empty
        if s.power.unmet_kw > 0.05:
            self.counts["load_shed_ticks"] += 1
        self.counts["unmet_wh"] += round(s.power.unmet_kw * self.dt * 1000)
        if s.thermal.habitat_temp_c < self.cold_c:
            self.counts["cold_ticks"] += 1
        if s.thermal.habitat_temp_c < self.processor_min_c:
            self.counts["processor_cold_ticks"] += 1
        if not s.comms.link_up:
            self.counts["comms_outage_ticks"] += 1

    def events(self, events: list[MissionEvent]) -> None:
        c = self.counts
        for e in events:
            k = e.kind
            if e.severity == AlertSeverity.CRITICAL:
                c["emergency_events"] += 1
            if k in (EventKind.ALERT_RAISED, EventKind.RESOURCE_WARNING):
                c[f"alert:{e.key}"] += 1
                if e.severity == AlertSeverity.CRITICAL:
                    c["critical_alerts"] += 1
                elif e.severity == AlertSeverity.WARNING:
                    c["warning_alerts"] += 1
            elif k == EventKind.CASCADE_WARNING:
                c["cascade_warnings"] += 1
            elif k == EventKind.COMMUNICATION and e.key == "link_lost":
                c["comms_outage_events"] += 1
            elif k == EventKind.SPACE_WEATHER:
                c["space_weather_events"] += 1
            elif k == EventKind.SYSTEM_FAULT:
                c["random_faults" if e.data.get("random") else "scripted_faults"] += 1
            elif k == EventKind.MAINTENANCE and e.key.startswith("maintenance_complete"):
                c["maintenance_completed"] += 1
            elif k == EventKind.MILESTONE and e.key.startswith("crew_incapacitated"):
                c["crew_incapacitated"] += 1
            elif (
                k == EventKind.DECISION_APPLIED
                and e.data.get("inputs", {}).get("action") == "traverse"
            ):
                c["rover_traverses"] += 1


def run_mission(
    engine: SimulationEngine,
    strategy: str | Strategy,
    seed: int,
    *,
    overrides: dict[str, Any] | None = None,
    options: RunOptions | None = None,
    check_invariants: bool = False,
    keep_events: bool = False,
) -> MissionRun:
    """Play one full mission (until it concludes) with a scripted strategy."""
    sc = engine.scenario
    policy = make_strategy(strategy, seed) if isinstance(strategy, str) else strategy
    opts = options or RunOptions()
    state = engine.initial_state(seed)
    initial = state
    tel = _Telemetry(engine)
    tel.observe(state, stepped=False)
    decisions: list[AppliedDecision] = []
    rejections: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    all_events: list[MissionEvent] = []
    violations = 0
    previous = state
    guard = sc.time.max_ticks + 2  # a mission always concludes at max_ticks

    for _ in range(guard):
        if state.status == MissionStatus.CONCLUDED:
            break
        for raw in policy.decide(Observation(engine, state, seed)):
            decision = parse_decision(raw)
            seq = len(decisions) + 1
            did = f"{policy.name}:{seq}"
            try:
                res = engine.apply_decision(state, decision, did)
            except DecisionRejectedError as exc:
                rejections[exc.code] += 1
                continue
            state = res.state
            decisions.append(
                AppliedDecision(did, seq, state.tick, decision.model_dump(mode="json"))
            )
            by_type[decision.type] += 1
            tel.events(list(res.events))
            if keep_events:
                all_events.extend(res.events)
        step = engine.step(state, opts)
        previous, state = state, step.state
        tel.observe(state, stepped=True)
        tel.events(list(step.events))
        if keep_events:
            all_events.extend(step.events)
        if check_invariants:
            problems = check_state(engine, state, previous=previous)
            if problems:
                violations += len(problems)
                raise InvariantViolationError(problems)
    else:  # pragma: no cover - would mean the engine failed to conclude
        raise RuntimeError(f"mission did not conclude within {guard} ticks")

    m = engine.metrics
    c = tel.counts
    outcome = state.outcome.code if state.outcome else "in_progress"
    objectives = {k: v.status.value for k, v in sorted(state.objectives.items())}
    completed = int(m.value("science.opportunities_completed", state))
    n_opps = len(sc.science.opportunities)
    metrics = MissionMetrics(
        scenario_id=sc.id,
        strategy=policy.name,
        seed=seed,
        outcome=outcome,
        outcome_class=outcome_class(engine, state),
        ending_phase=state.phase,
        concluded=state.status == MissionStatus.CONCLUDED,
        duration_ticks=state.tick,
        duration_hours=state.tick * sc.time.tick_hours,
        battery_soc_min=tel.mins["soc"],
        battery_soc_final=m.value("power.battery_soc", state),
        battery_kwh_final=state.power.battery_charge_kwh,
        battery_zero_events=c["battery_zero_events"],
        battery_zero_ticks=c["battery_zero_ticks"],
        load_shed_ticks=c["load_shed_ticks"],
        unmet_energy_kwh=c["unmet_wh"] / 1000.0,
        oxygen_days_min=tel.mins["life_support.oxygen_days"],
        oxygen_kg_min=tel.mins["oxygen_kg"],
        water_days_min=tel.mins["life_support.water_days"],
        water_kg_min=tel.mins["water_kg"],
        food_days_min=tel.mins["food.food_days"],
        food_kg_min=tel.mins["food_kg"],
        oxygen_days_final=m.value("life_support.oxygen_days", state),
        water_days_final=m.value("life_support.water_days", state),
        food_days_final=m.value("food.food_days", state),
        co2_ppm_max=tel.maxs["co2"],
        habitat_temp_min=tel.mins["thermal.habitat_temp_c"],
        cold_ticks=c["cold_ticks"],
        processor_cold_ticks=c["processor_cold_ticks"],
        crew_dose_max_msv=m.value("crew.max_dose_msv", state),
        crew_min_health=tel.mins["crew.min_health"],
        crew_min_health_final=m.value("crew.min_health", state),
        crew_incapacitated=c["crew_incapacitated"],
        science_points=state.science.points,
        science_completed=completed,
        science_opportunities=n_opps,
        science_completion=completed / n_opps if n_opps else 0.0,
        data_downlinked_mb=state.comms.data_downlinked_mb,
        objectives_achieved=sum(
            1 for v in objectives.values() if v == ObjectiveStatus.ACHIEVED.value
        ),
        objectives_total=len(objectives),
        emergency_events=c["emergency_events"],
        critical_alerts=c["critical_alerts"],
        warning_alerts=c["warning_alerts"],
        cascade_warnings=c["cascade_warnings"],
        comms_outage_events=c["comms_outage_events"],
        comms_outage_ticks=c["comms_outage_ticks"],
        space_weather_events=c["space_weather_events"],
        random_faults=c["random_faults"],
        scripted_faults=c["scripted_faults"],
        maintenance_completed=c["maintenance_completed"],
        rover_traverses=c["rover_traverses"],
        rover_successes=sum(
            1
            for o in state.science.opportunities.values()
            if o.status == "completed" and sc.opportunity(o.id).requires_rover
        ),
        rover_lost=state.rover.status == RoverStatus.LOST,
        risk_final=m.value("risk.mission", state),
        risk_peak=tel.maxs["risk"],
        decisions_accepted=len(decisions),
        decisions_rejected=sum(rejections.values()),
        invariant_violations=violations,
        objectives=objectives,
        alerts_raised={
            k.removeprefix("alert:"): v for k, v in sorted(c.items()) if k.startswith("alert:")
        },
        decisions_by_type=dict(sorted(by_type.items())),
        rejections_by_code=dict(sorted(rejections.items())),
        overrides=dict(overrides or {}),
    )
    return MissionRun(
        metrics=metrics, initial=initial, final=state, decisions=decisions, events=all_events
    )
