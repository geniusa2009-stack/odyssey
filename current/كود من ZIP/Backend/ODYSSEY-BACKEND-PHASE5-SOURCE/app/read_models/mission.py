"""Mission-level read models: snapshot, HUD, clock, phase, alerts, risk, science, completion.

The snapshot is the authoritative current state of one timeline as a client may see it. It is
a pure projection of ``(engine, head state)``; recovering from a refresh, a reconnect, a lost
realtime event or a ``409`` is always "fetch the snapshot".
"""

from __future__ import annotations

from pydantic import Field

from app.read_models.common import READ_MODEL_VERSION, View, band, rnd, rnd_unit
from app.read_models.crew import CrewOverview, build_crew
from app.read_models.decisions import AvailableDecisionsView, build_decision_options
from app.read_models.objectives import ObjectiveOutlookView, ObjectiveView, build_objectives
from app.read_models.radiation import RadiationBudgetView, build_radiation
from app.read_models.resources import ResourceView, build_resources
from app.read_models.systems import SystemOverview, build_systems
from app.read_models.visibility import entered_phases, phase_is_visible
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.schema import LEGACY_OUTCOME_TIERS, OUTCOME_TIERS


class ClockView(View):
    tick: int
    max_ticks: int
    tick_hours: float
    elapsed_hours: float
    remaining_hours: float


class PhaseHistoryEntry(View):
    phase: str
    tick: int


class MissionPhaseView(View):
    id: str
    kind: str
    index: int
    total: int
    entered_tick: int
    next_phase: str | None = Field(
        description="Next phase, or null when there is none or it is withheld until entered "
        "(see next_phase_withheld; docs/API_CONTRACT.md#phase-visibility)"
    )
    next_phase_withheld: bool = False
    history: list[PhaseHistoryEntry]


class AlertView(View):
    # recovered name: the original API v1 used ``id`` (docs/RECOVERY_PROVENANCE.md, F1)
    id: str
    severity: str
    metric: str
    label: str
    unit: str
    value: float
    threshold: float
    op: str
    raised_tick: int
    category: str
    message_key: str


class RiskDriver(View):
    metric: str
    label: str
    severity: float
    weight: float
    contribution: float


class RiskSummary(View):
    index: float
    band: str
    drivers: list[RiskDriver]


class OpportunityView(View):
    id: str
    status: str
    opened_tick: int
    closes_tick: int
    progress_fraction: float
    work_ticks_required: int
    requires_rover: bool


class ScienceStatusView(View):
    points: float
    opportunities_completed: int
    data_downlinked_mb: float
    data_pending_mb: float
    active_opportunity: str | None
    opportunities: list[OpportunityView]


class AlertCounts(View):
    critical: int
    warning: int
    caution: int


class MissionHUD(View):
    """Compact headline numbers (also the payload of ``RESOURCE_CHANGED``)."""

    tick: int
    battery_soc: float
    oxygen_days: float
    co2_ppm: float
    water_days: float
    food_days: float
    habitat_temp_c: float
    generation_kw: float
    demand_kw: float
    unmet_kw: float
    crew_min_health: float
    max_dose_msv: float
    dose_margin_msv: float | None
    science_points: float
    data_downlinked_mb: float
    link_up: bool
    risk_index: float
    alerts: AlertCounts


class OutcomeView(View):
    code: str
    tier: str | None
    tick: int
    rule_id: str
    objectives_achieved: list[str]
    objectives_failed: list[str]
    message_key: str


class TimelineRef(View):
    id: str
    label: str
    parent_timeline_id: str | None
    fork_tick: int | None
    fork_sequence: int | None
    status: str
    is_active: bool
    head_tick: int
    head_sequence: int
    state_version: int


class MissionSnapshotView(View):
    read_model_version: int = READ_MODEL_VERSION
    session_id: str
    timeline: TimelineRef
    state_version: int
    state_hash: str
    status: str
    clock: ClockView
    phase: MissionPhaseView
    hud: MissionHUD
    resources: list[ResourceView]
    systems: SystemOverview
    crew: CrewOverview
    objectives: ObjectiveOutlookView
    alerts: list[AlertView]
    radiation: RadiationBudgetView
    science: ScienceStatusView
    risk: RiskSummary
    decisions: AvailableDecisionsView
    outcome: OutcomeView | None


class TierBlock(View):
    tier: str
    blocked_by: list[str]


class DurationView(View):
    ticks: int
    hours: float


class MissionCompletionView(View):
    session_id: str
    timeline_id: str
    state_version: int
    concluded: bool
    outcome: OutcomeView | None
    objectives: list[ObjectiveView]
    better_tiers_blocked: list[TierBlock]
    duration: DurationView
    decisions_count: int
    final_hud: MissionHUD
    analysis_paths: dict[str, str]


# ----------------------------------------------------------------------------------- builders
def outcome_tier(engine: SimulationEngine, code: str, rule_id: str) -> str | None:
    try:
        tier = engine.scenario.outcome_rule(rule_id).effective_tier
    except KeyError:
        tier = None
    return tier or LEGACY_OUTCOME_TIERS.get(code)


def build_outcome(engine: SimulationEngine, state: MissionState) -> OutcomeView | None:
    o = state.outcome
    if o is None:
        return None
    return OutcomeView(
        code=o.code,
        tier=outcome_tier(engine, o.code, o.rule_id),
        tick=o.tick,
        rule_id=o.rule_id,
        objectives_achieved=list(o.objectives_achieved),
        objectives_failed=list(o.objectives_failed),
        message_key=f"outcome.{o.code}",
    )


def build_clock(engine: SimulationEngine, state: MissionState) -> ClockView:
    t = engine.scenario.time
    return ClockView(
        tick=state.tick,
        max_ticks=t.max_ticks,
        tick_hours=t.tick_hours,
        elapsed_hours=rnd(state.tick * t.tick_hours, 1),
        remaining_hours=rnd(max(0, t.max_ticks - state.tick) * t.tick_hours, 1),
    )


def build_phase(engine: SimulationEngine, state: MissionState) -> MissionPhaseView:
    phases = engine.scenario.phases
    ids = [p.id for p in phases]
    idx = ids.index(state.phase) if state.phase in ids else 0
    entered = max((h.tick for h in state.phase_history if h.phase == state.phase), default=0)
    following = ids[idx + 1] if idx + 1 < len(ids) else None
    withheld = following is not None and not phase_is_visible(
        engine, following, entered_phases(state)
    )
    return MissionPhaseView(
        id=state.phase,
        kind=phases[idx].kind,
        index=idx,
        total=len(phases),
        entered_tick=entered,
        next_phase=None if withheld else following,
        next_phase_withheld=withheld,
        history=[PhaseHistoryEntry(phase=h.phase, tick=h.tick) for h in state.phase_history],
    )


def build_alerts(engine: SimulationEngine, state: MissionState) -> list[AlertView]:
    rules = {a.id: a for a in engine.scenario.alerts}
    order = {"critical": 0, "warning": 1, "caution": 2}
    out = []
    for a in state.alerts.values():
        rule = rules.get(a.id)
        spec = engine.metrics.spec(a.metric)
        out.append(
            AlertView(
                id=a.id,
                severity=a.severity.value,
                metric=a.metric,
                label=spec.label,
                unit=spec.unit,
                value=rnd_unit(a.value, spec.unit),
                threshold=rule.threshold if rule else 0.0,
                op=rule.op if rule else "",
                raised_tick=a.raised_tick,
                category=rule.category if rule else "resource",
                message_key=f"alert.{a.id}",
            )
        )
    out.sort(key=lambda v: (order.get(v.severity, 3), v.raised_tick, v.id))
    return out


def build_risk(engine: SimulationEngine, state: MissionState) -> RiskSummary:
    metrics = engine.metrics
    drivers = []
    for term in engine.scenario.analysis.risk_terms:
        sev = metrics.severity(term.metric, state)
        drivers.append(
            RiskDriver(
                metric=term.metric,
                label=metrics.spec(term.metric).label,
                severity=rnd(sev, 3),
                weight=term.weight,
                contribution=rnd(sev * term.weight, 3),
            )
        )
    drivers = sorted((d for d in drivers if d.contribution > 0), key=lambda d: -d.contribution)
    return RiskSummary(
        index=rnd(metrics.value("risk.mission", state), 3),
        band=band(metrics.severity("risk.mission", state)),
        drivers=drivers[:3],
    )


def build_science(engine: SimulationEngine, state: MissionState) -> ScienceStatusView:
    """Science status. Only windows that have *opened* are listed (never future ones)."""
    sc, m = engine.scenario, engine.metrics
    opps = []
    for opp in sorted(state.science.opportunities.values(), key=lambda o: (o.opened_tick, o.id)):
        spec = sc.opportunity(opp.id)
        opps.append(
            OpportunityView(
                id=opp.id,
                status=opp.status.value,
                opened_tick=opp.opened_tick,
                closes_tick=opp.closes_tick,
                progress_fraction=rnd(min(1.0, opp.progress_ticks / spec.work_ticks_required), 3),
                work_ticks_required=spec.work_ticks_required,
                requires_rover=spec.requires_rover,
            )
        )
    return ScienceStatusView(
        points=rnd_unit(state.science.points, "points"),
        opportunities_completed=int(m.value("science.opportunities_completed", state)),
        data_downlinked_mb=rnd_unit(state.comms.data_downlinked_mb, "MB"),
        data_pending_mb=rnd_unit(state.science.data_pending_mb, "MB"),
        active_opportunity=state.science.active_opportunity,
        opportunities=opps,
    )


def _v(engine: SimulationEngine, metric: str, state: MissionState) -> float:
    return rnd_unit(engine.metrics.value(metric, state), engine.metrics.spec(metric).unit)


def build_hud(engine: SimulationEngine, state: MissionState) -> MissionHUD:
    m = engine.metrics
    counts = {"critical": 0, "warning": 0, "caution": 0}
    for a in state.alerts.values():
        counts[a.severity.value] = counts.get(a.severity.value, 0) + 1
    return MissionHUD(
        tick=state.tick,
        battery_soc=_v(engine, "power.battery_soc", state),
        oxygen_days=_v(engine, "life_support.oxygen_days", state),
        co2_ppm=_v(engine, "life_support.co2_ppm", state),
        water_days=_v(engine, "life_support.water_days", state),
        food_days=_v(engine, "food.food_days", state),
        habitat_temp_c=_v(engine, "thermal.habitat_temp_c", state),
        generation_kw=_v(engine, "power.generation_kw", state),
        demand_kw=_v(engine, "power.demand_kw", state),
        unmet_kw=_v(engine, "power.unmet_kw", state),
        crew_min_health=_v(engine, "crew.min_health", state),
        max_dose_msv=_v(engine, "crew.max_dose_msv", state),
        dose_margin_msv=_v(engine, "crew.dose_margin_msv", state)
        if m.has("crew.dose_margin_msv")
        else None,
        science_points=_v(engine, "science.points", state),
        data_downlinked_mb=_v(engine, "comms.data_downlinked_mb", state),
        link_up=state.comms.link_up,
        risk_index=_v(engine, "risk.mission", state),
        alerts=AlertCounts(
            critical=counts["critical"], warning=counts["warning"], caution=counts["caution"]
        ),
    )


def build_snapshot(
    engine: SimulationEngine,
    state: MissionState,
    *,
    session_id: str,
    timeline: TimelineRef,
    previous: MissionState | None = None,
) -> MissionSnapshotView:
    """``previous``: the most recent *recorded* earlier state of this timeline (for trends)."""
    return MissionSnapshotView(
        session_id=session_id,
        timeline=timeline,
        state_version=timeline.state_version,
        state_hash=state.state_hash(),
        status=state.status.value,
        clock=build_clock(engine, state),
        phase=build_phase(engine, state),
        hud=build_hud(engine, state),
        resources=build_resources(engine, state, previous),
        systems=build_systems(engine, state),
        crew=build_crew(engine, state),
        objectives=build_objectives(engine, state),
        alerts=build_alerts(engine, state),
        radiation=build_radiation(engine, state),
        science=build_science(engine, state),
        risk=build_risk(engine, state),
        decisions=build_decision_options(engine, state),
        outcome=build_outcome(engine, state),
    )


def better_tiers_blocked(engine: SimulationEngine, state: MissionState) -> list[TierBlock]:
    """For a concluded mission: each tier better than the one reached, with the objectives
    (required by that tier's outcome rules) that were not achieved."""
    if state.outcome is None:
        return []
    sc = engine.scenario
    tier = outcome_tier(engine, state.outcome.code, state.outcome.rule_id)
    rank = OUTCOME_TIERS.index(tier) if tier in OUTCOME_TIERS else -1
    blocked: dict[str, set[str]] = {}
    for rule in sc.outcomes:
        t = rule.effective_tier
        if t is None or t not in OUTCOME_TIERS or OUTCOME_TIERS.index(t) <= rank:
            continue
        for o in sc.objectives:
            needed = o.effective_category in (rule.requires_categories or []) or bool(
                rule.requires_required_objectives and o.required
            )
            if needed and state.objectives[o.id].status.value != "achieved":
                blocked.setdefault(t, set()).add(o.id)
    order = {t: i for i, t in enumerate(OUTCOME_TIERS)}
    return [
        TierBlock(tier=t, blocked_by=sorted(ids))
        for t, ids in sorted(blocked.items(), key=lambda kv: -order[kv[0]])
    ]


def build_completion(
    engine: SimulationEngine,
    state: MissionState,
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
    decisions_count: int,
) -> MissionCompletionView:
    base = f"/api/v1/mission-sessions/{session_id}"
    concluded = state.outcome is not None
    return MissionCompletionView(
        session_id=session_id,
        timeline_id=timeline_id,
        state_version=state_version,
        concluded=concluded,
        outcome=build_outcome(engine, state),
        objectives=build_objectives(engine, state).objectives,
        better_tiers_blocked=better_tiers_blocked(engine, state),
        duration=DurationView(
            ticks=state.tick, hours=rnd(state.tick * engine.scenario.time.tick_hours, 1)
        ),
        decisions_count=decisions_count,
        final_hud=build_hud(engine, state),
        analysis_paths={
            "black_box": f"{base}/black-box/summary",
            "mission_dna": f"{base}/mission-dna/share",
            "engineering_profile": f"{base}/engineering-profile",
            "history": f"{base}/history",
        },
    )
