"""Analysis read models: Future Lens, Black Box, history, rewind, profile, Mission DNA, claims.

Each is a frontend-safe projection of an engine analysis result. None of them exposes the
seed, dependency-graph internals (node and edge lists) or anything about unforeseeable future
events.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import Field

from app.read_models.common import View, clean_data, rnd, rnd_unit
from app.read_models.decisions import decision_parameters, decision_to_option_id
from app.read_models.events import EventView, event_view
from app.read_models.mission import MissionHUD, OutcomeView, TimelineRef, outcome_tier
from app.read_models.visibility import (
    phase_is_visible,
    redact_usage,
    unforeseeable_event_ids,
)
from app.science.evidence import ScienceEvidence
from app.simulation.analysis.black_box import BlackBoxReport, TimelineEntry
from app.simulation.analysis.future_lens import (
    KNOWLEDGE_FACTOR_EXCLUDED,
    BranchPrediction,
    FutureLensResult,
    confidence_from_factors,
)
from app.simulation.analysis.mission_dna import MissionDNA
from app.simulation.analysis.profile import EngineeringProfile
from app.simulation.analysis.root_cause import RootCauseTrace
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.ledger import DecisionRecord

PredictionMode = Literal["known_only", "omniscient"]
GENERIC_UNFORESEEABLE_ASSUMPTION = (
    "Unforeseeable events (for example space weather, communication outages and equipment "
    "faults) are not anticipated."
)
KNOWLEDGE_STATEMENTS: dict[str, str] = {
    "known_only": "Projections use only what is known now: the current state, the mission plan, "
    "and random faults sampled with seeds derived for the projection (never the mission's own "
    "random sequence). Unforeseeable events are never anticipated, whether or not any remain.",
    "omniscient": "Omniscient projection (teacher/debug): the mission's own random sequence and "
    "every scheduled event are used, so hidden future events are revealed.",
}


# ============================================================================== decisions
class DecisionRef(View):
    option_id: str
    parameters: dict[str, float] = Field(default_factory=dict)


class DecisionEntryView(View):
    decision_id: str
    sequence: int
    tick: int
    phase: str
    decision_type: str
    option_id: str
    parameters: dict[str, float]
    affected_systems: list[str]
    timeline_id: str
    inherited: bool = False
    participant_id: str | None = Field(
        None,
        description="Participant who submitted the decision, or null when none was given. "
        "(Recovered field: the name is inferred from the recorded fixture/class shape; "
        "see docs/RECOVERY_PROVENANCE.md.)",
    )


def decision_entry(
    r: DecisionRecord, timeline_id: str, *, inherited: bool = False
) -> DecisionEntryView:
    """One ledger decision as a client sees it (``inherited``: recorded on a parent timeline
    before the fork point)."""
    return DecisionEntryView(
        decision_id=r.decision_id,
        sequence=r.sequence,
        tick=r.tick,
        phase=r.phase,
        decision_type=r.decision_type,
        option_id=decision_to_option_id(r.inputs),
        parameters=decision_parameters(r.inputs),
        affected_systems=list(r.affected_systems),
        timeline_id=timeline_id,
        inherited=inherited or r.timeline_id != timeline_id,
        participant_id=_participant(r),
    )


def _participant(r: DecisionRecord) -> str | None:
    # the decision core records the submitting participant in the ledger metadata (and in the
    # participant_id column of the same row)
    value = (r.metadata or {}).get("participant_id")
    return str(value) if value else None


# ============================================================================== Future Lens
class ResourceProjectionView(View):
    metric: str
    label: str
    unit: str
    start: float
    end: float
    end_min: float
    end_max: float
    delta: float
    worst: float
    worst_tick: int
    vs_baseline: float | None = None


class CounterfactualView(View):
    target_metric: str
    target_tick: int
    verdict: str
    with_decision: float | None = None
    without_decision: float | None = None


class CausalStepView(View):
    kind: str
    label: str
    tick: int | None = None
    value: float | None = None
    via: str | None = None


class CausalChainView(View):
    target_metric: str
    target_tick: int
    steps: list[CausalStepView]
    counterfactual: CounterfactualView | None = None


class ExplanationView(View):
    target_metric: str
    steps: list[str]
    counterfactual: CounterfactualView | None = None


class WarningProjectionView(View):
    alert_id: str
    severity: str
    metric: str
    first_tick: int
    hours_from_now: float
    sample_fraction: float
    introduced_by_candidate: bool


class ObjectiveProjectionView(View):
    objective: str
    category: str
    status_now: str
    projected_status: str
    achieved_fraction: float
    failed_fraction: float


class RiskProjectionView(View):
    end_index: float
    peak_index: float
    peak_tick: int
    critical_warning_fraction: float


class KnowledgeBoundaryView(View):
    prediction_mode: PredictionMode
    anticipates_unforeseeable_events: bool
    uses_mission_random_sequence: bool
    statement: str


class HorizonView(View):
    requested_ticks: int
    projected_ticks: int
    hours: float
    clipped_to_mission_end: bool


class ConfidenceView(View):
    level: str
    score: float
    samples: int
    provisional: bool
    horizon_factor: float
    spread_factor: float
    model_factor: float
    knowledge_factor: float


class RejectionView(View):
    reason: str
    message: str


class BranchView(View):
    label: str
    is_baseline: bool
    decisions: list[DecisionRef] = Field(default_factory=list)
    valid: bool
    rejection: RejectionView | None = None
    concludes_within_horizon: bool = False
    projected_outcome: OutcomeView | None = None
    projected_phase: str | None = None
    projected_phase_withheld: bool = Field(
        False,
        description="True when the projected phase is withheld until entered (phase visibility "
        "rule); projected_phase is then null. Never set in omniscient mode.",
    )
    resources: list[ResourceProjectionView] = Field(default_factory=list)
    warnings: list[WarningProjectionView] = Field(default_factory=list)
    objectives: list[ObjectiveProjectionView] = Field(default_factory=list)
    risk: RiskProjectionView | None = None
    confidence: ConfidenceView | None = None
    assumptions: list[str] = Field(default_factory=list)
    explanations: list[ExplanationView] = Field(default_factory=list)


class FutureLensView(View):
    session_id: str
    timeline_id: str
    base_tick: int
    state_version: int
    request_hash: str
    knowledge_boundary: KnowledgeBoundaryView
    horizon: HorizonView
    branches: list[BranchView]


def _trace_counterfactual(trace: RootCauseTrace) -> CounterfactualView | None:
    target_unit = next(
        (n.unit for n in trace.nodes if n.id == f"metric:{trace.target_metric}"), None
    )
    for node in trace.nodes:
        cf = node.details.get("counterfactual")
        if cf:
            return CounterfactualView(
                target_metric=str(cf["target_metric"]),
                target_tick=int(cf["target_tick"]),
                verdict=str(cf["verdict"]),
                with_decision=_num(cf.get("with_decision_value"), target_unit),
                without_decision=_num(cf.get("without_decision_value"), target_unit),
            )
    return None


def _num(value: Any, unit: str | None = None) -> float | None:
    """A counterfactual value at the display precision of its unit (3 decimals if unknown)."""
    if not isinstance(value, int | float):
        return None
    return rnd_unit(float(value), unit) if unit else rnd(float(value), 3)


def _step_label(kind: str, label: str) -> str:
    # engine labels decision nodes "Decision <type>"; the client sees "Decision: <type>"
    if kind == "decision" and label.startswith("Decision ") and ":" not in label:
        return "Decision: " + label.removeprefix("Decision ")
    return label


def _chain_steps(trace: RootCauseTrace) -> list[CausalStepView]:
    if not trace.chains:
        return []
    nodes = {n.id: n for n in trace.nodes}
    mech = {(e.source, e.target): e.mechanism for e in trace.edges}
    chain = _explained_chain(trace)
    steps = []
    for i, node_id in enumerate(chain):
        n = nodes[node_id]
        via = mech.get((node_id, chain[i + 1])) if i + 1 < len(chain) else None
        value = rnd_unit(n.value, n.unit or "") if n.value is not None else None
        steps.append(
            CausalStepView(
                kind=n.kind, label=_step_label(n.kind, n.label), tick=n.tick, value=value, via=via
            )
        )
    return steps


# A budget margin is explained by the quantity it is the margin of: the explanation names the
# underlying metric when that metric is the node directly upstream of the margin on the
# explained causal chain. Only the label of the explained quantity changes; the engine's trace,
# its values and its steps are used unchanged (docs/RECOVERY_PROVENANCE.md, F3).
_MARGIN_OF: dict[str, str] = {"crew.projected_dose_margin_msv": "crew.projected_dose_msv"}


def _explained_chain(trace: RootCauseTrace) -> list[str]:
    if not trace.chains:
        return []
    decision_chains = [c for c in trace.chains if c and c[0].startswith("decision:")]
    return (decision_chains or trace.chains)[0]


def _explained_metric(trace: RootCauseTrace) -> str:
    underlying = _MARGIN_OF.get(trace.target_metric)
    chain = _explained_chain(trace)
    if (
        underlying is not None
        and len(chain) >= 2
        and chain[-1] == f"metric:{trace.target_metric}"
        and chain[-2] == f"metric:{underlying}"
    ):
        return underlying
    return trace.target_metric


def _explanation(trace: RootCauseTrace) -> ExplanationView:
    steps = [
        s.label + (f" (tick {s.tick})" if s.tick is not None else "") for s in _chain_steps(trace)
    ]
    return ExplanationView(
        target_metric=_explained_metric(trace),
        steps=steps,
        counterfactual=_trace_counterfactual(trace),
    )


def _assumptions(assumptions: Sequence[str], mode: PredictionMode) -> list[str]:
    if mode == "omniscient":
        return list(assumptions)
    # The raw result names which unforeseeable events were excluded; whether any remain is
    # itself hidden information, so the sentence is replaced by a generic one.
    kept = [a for a in assumptions if "nforeseeable" not in a and "xcluded" not in a]
    return [*kept, GENERIC_UNFORESEEABLE_ASSUMPTION]


def _branch_view(
    engine: SimulationEngine,
    p: BranchPrediction,
    mode: PredictionMode,
    base_tick: int,
    entered: frozenset[str],
) -> BranchView:
    decisions = [
        DecisionRef(option_id=decision_to_option_id(d), parameters=decision_parameters(d))
        for d in p.decisions
    ]
    if not p.valid:
        rej = p.rejection or {}
        return BranchView(
            label=p.label,
            is_baseline=p.is_baseline,
            decisions=decisions,
            valid=False,
            rejection=RejectionView(
                reason=rej.get("code", "decision_rejected"), message=rej.get("message", "")
            ),
        )
    m = engine.metrics
    tick_hours = engine.scenario.time.tick_hours
    resources = [
        ResourceProjectionView(
            metric=x.metric,
            label=m.spec(x.metric).label,
            unit=x.unit,
            start=rnd_unit(x.start, x.unit),
            end=rnd_unit(x.end, x.unit),
            end_min=rnd_unit(x.end_min, x.unit),
            end_max=rnd_unit(x.end_max, x.unit),
            delta=rnd_unit(x.delta, x.unit),
            worst=rnd_unit(x.worst, x.unit),
            worst_tick=x.worst_tick,
            vs_baseline=rnd_unit(p.vs_baseline[x.metric], x.unit)
            if x.metric in p.vs_baseline
            else None,
        )
        for x in p.metrics
    ]
    warnings = [
        WarningProjectionView(
            alert_id=w.alert_id,
            severity=w.severity.value,
            metric=w.metric,
            first_tick=w.first_tick,
            hours_from_now=rnd((w.first_tick - base_tick) * tick_hours, 1),
            sample_fraction=rnd(w.sample_fraction, 3),
            introduced_by_candidate=w.alert_id in p.new_warnings,
        )
        for w in p.warnings
    ]
    objectives = [
        ObjectiveProjectionView(
            objective=o.objective,
            category=o.category,
            status_now=o.status_now,
            projected_status=o.projected_status,
            achieved_fraction=rnd(o.achieved_fraction, 3),
            failed_fraction=rnd(o.failed_fraction, 3),
        )
        for o in p.objective_outlook
    ]
    risk = (
        RiskProjectionView(
            end_index=rnd(p.risk.get("end_risk", 0.0), 3),
            peak_index=rnd(p.risk.get("peak_risk", 0.0), 3),
            peak_tick=int(p.risk.get("peak_risk_tick", base_tick)),
            critical_warning_fraction=rnd(p.risk.get("critical_warning_fraction", 0.0), 3),
        )
        if p.risk
        else None
    )
    confidence = None
    if p.confidence is not None:
        c = p.confidence
        if mode == "known_only":
            # constant knowledge factor: whether hidden events remain is not revealed
            c = confidence_from_factors(
                horizon_factor=c.horizon_factor,
                spread_factor=c.spread_factor,
                knowledge_factor=KNOWLEDGE_FACTOR_EXCLUDED,
                samples=c.samples,
            )
        confidence = ConfidenceView(
            level=c.level,
            score=rnd(c.score, 2),
            samples=c.samples,
            provisional=c.provisional,
            horizon_factor=rnd(c.horizon_factor, 2),
            spread_factor=rnd(c.spread_factor, 2),
            model_factor=rnd(c.model_factor, 2),
            knowledge_factor=rnd(c.knowledge_factor, 2),
        )
    outcome = None
    if p.projected_outcome is not None:
        rule = next((r for r in engine.scenario.outcomes if r.code == p.projected_outcome), None)
        outcome = OutcomeView(
            code=p.projected_outcome,
            tier=rule.effective_tier if rule else outcome_tier(engine, p.projected_outcome, ""),
            tick=base_tick + p.ticks_projected,
            rule_id=rule.id if rule else "",
            objectives_achieved=sorted(
                o.objective for o in p.objective_outlook if o.projected_status == "achieved"
            ),
            objectives_failed=sorted(
                o.objective for o in p.objective_outlook if o.projected_status == "failed"
            ),
            message_key=f"outcome.{p.projected_outcome}",
        )
    phase_withheld = (
        mode == "known_only"
        and p.projected_phase is not None
        and not phase_is_visible(engine, p.projected_phase, entered)
    )
    return BranchView(
        label=p.label,
        is_baseline=p.is_baseline,
        decisions=decisions,
        valid=True,
        concludes_within_horizon=p.concludes,
        projected_outcome=outcome,
        projected_phase=None if phase_withheld else p.projected_phase,
        projected_phase_withheld=phase_withheld,
        resources=resources,
        warnings=warnings,
        objectives=objectives,
        risk=risk,
        confidence=confidence,
        assumptions=_assumptions(p.assumptions, mode),
        explanations=[_explanation(t) for t in p.causal_explanation],
    )


def build_future_lens_view(
    engine: SimulationEngine,
    result: FutureLensResult,
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
    requested_ticks: int,
    entered: frozenset[str],
) -> FutureLensView:
    """``entered``: phases the mission has entered at the base state (phase visibility)."""
    mode: PredictionMode = result.knowledge_policy
    projected = max((p.ticks_projected for p in result.predictions if p.valid), default=0)
    return FutureLensView(
        session_id=session_id,
        timeline_id=timeline_id,
        base_tick=result.base_tick,
        state_version=state_version,
        request_hash=result.request_hash,
        knowledge_boundary=KnowledgeBoundaryView(
            prediction_mode=mode,
            anticipates_unforeseeable_events=mode == "omniscient",
            uses_mission_random_sequence=mode == "omniscient",
            statement=KNOWLEDGE_STATEMENTS[mode],
        ),
        horizon=HorizonView(
            requested_ticks=requested_ticks,
            projected_ticks=projected,
            hours=rnd(projected * engine.scenario.time.tick_hours, 1),
            clipped_to_mission_end=projected < requested_ticks,
        ),
        branches=[
            _branch_view(engine, p, mode, result.base_tick, entered) for p in result.predictions
        ],
    )


# ============================================================================== Black Box
class TriggerView(View):
    metric: str
    label: str
    unit: str
    op: str
    threshold: float
    value: float
    tick: int


class DecisionRefView(View):
    decision_id: str
    decision_type: str | None
    option_id: str | None
    tick: int | None
    verdict: str


class CauseView(View):
    id: str
    kind: str
    label: str


class EffectView(View):
    metric: str
    label: str
    unit: str


class ShortfallView(View):
    objective: str
    category: str
    kind: str
    resolved_tick: int | None
    blocks_tiers: list[str]
    triggers: list[TriggerView]
    root_decisions: list[DecisionRefView]
    decisions_on_path_without_effect: list[DecisionRefView]
    other_causes: list[CauseView]
    intermediate_effects: list[EffectView]
    facts: list[str]
    consequence: str
    causal_chain: CausalChainView | None = None


class KeyMomentView(View):
    tick: int
    category: str
    kind: str
    key: str
    severity: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class BlackBoxView(View):
    session_id: str
    timeline_id: str
    state_version: int
    mission_status: str
    final_tick: int
    outcome: OutcomeView | None
    blocked_tiers: dict[str, list[str]]
    shortfalls: list[ShortfallView]
    key_moments: list[KeyMomentView]
    decisions_count: int
    counterfactuals_evaluated: bool
    statement: str = (
        "Decisions are named as root causes only when a counterfactual replay without them "
        "makes the failing quantity better. Decisions on a causal path whose removal changes "
        "nothing are listed separately and never blamed."
    )


def _moment(e: TimelineEntry) -> KeyMomentView:
    return KeyMomentView(
        tick=e.tick,
        category=e.category,
        kind=e.kind,
        key=e.key,
        severity=e.severity,
        data=clean_data(e.data),
    )


def _is_key_moment(e: TimelineEntry) -> bool:
    """Key moments are mission milestones, phase transitions and designed or state-triggered
    incidents. Randomly sampled wear faults (engine ``data.random``) are incidental noise: they
    stay in the report's failures and causal data but are not elevated to key moments."""
    return not (e.category == "failure" and e.data.get("random") is True)


def build_black_box_view(
    engine: SimulationEngine,
    report: BlackBoxReport,
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
    counterfactuals: bool,
) -> BlackBoxView:
    inputs_by_id = {d.decision_id: d.inputs for d in report.decisions}

    def dref(
        decision_id: str, dtype: str | None, tick: int | None, verdict: str
    ) -> DecisionRefView:
        inputs = inputs_by_id.get(decision_id)
        return DecisionRefView(
            decision_id=decision_id,
            decision_type=dtype,
            option_id=decision_to_option_id(inputs) if inputs else None,
            tick=tick,
            verdict=verdict,
        )

    outcome = None
    if report.outcome is not None:
        o = report.outcome
        outcome = OutcomeView(
            code=o.code,
            tier=outcome_tier(engine, o.code, o.rule_id),
            tick=o.tick,
            rule_id=o.rule_id,
            objectives_achieved=list(o.objectives_achieved),
            objectives_failed=list(o.objectives_failed),
            message_key=f"outcome.{o.code}",
        )
    analysis = report.outcome_analysis
    blocked = analysis.blocked_tiers if analysis else {}
    shortfalls: list[ShortfallView] = []
    for chain in analysis.chains if analysis else []:
        trace = (
            report.causal_traces[chain.trace_index]
            if chain.trace_index is not None and chain.trace_index < len(report.causal_traces)
            else None
        )
        nodes = {n.id: n for n in trace.nodes} if trace else {}
        m = engine.metrics
        triggers = [
            TriggerView(
                metric=t.metric,
                label=m.spec(t.metric).label if m.has(t.metric) else t.metric,
                unit=m.spec(t.metric).unit if m.has(t.metric) else "",
                op=t.op,
                threshold=t.threshold,
                value=rnd_unit(t.value, m.spec(t.metric).unit) if m.has(t.metric) else t.value,
                tick=t.tick,
            )
            for t in chain.triggers
        ]
        others = []
        for node_id in chain.other_roots:
            n = nodes.get(node_id)
            others.append(
                CauseView(
                    id=node_id,
                    kind=n.kind if n else node_id.split(":", 1)[0],
                    label=n.label if n else node_id,
                )
            )
        # intermediate effects are dependency-graph node ids ("metric:<name>")
        effect_metrics = [x.removeprefix("metric:") for x in chain.intermediate_effects]
        effects = [
            EffectView(
                metric=x,
                label=m.spec(x).label if m.has(x) else x,
                unit=m.spec(x).unit if m.has(x) else "",
            )
            for x in effect_metrics
        ]
        causal_chain = None
        if trace is not None:
            causal_chain = CausalChainView(
                target_metric=trace.target_metric,
                target_tick=trace.target_tick,
                steps=_chain_steps(trace),
                counterfactual=_trace_counterfactual(trace) if counterfactuals else None,
            )
        shortfalls.append(
            ShortfallView(
                objective=chain.objective,
                category=chain.category,
                kind=chain.kind,
                resolved_tick=chain.resolved_tick,
                blocks_tiers=sorted(t for t, objs in blocked.items() if chain.objective in objs),
                triggers=triggers,
                root_decisions=[
                    dref(d.decision_id, d.decision_type, d.tick, d.verdict)
                    for d in chain.root_decisions
                ],
                decisions_on_path_without_effect=[
                    dref(d.decision_id, d.decision_type, d.tick, d.verdict)
                    for d in chain.on_path_no_effect
                ],
                other_causes=others,
                intermediate_effects=effects,
                facts=list(chain.facts),
                consequence=chain.consequence,
                causal_chain=causal_chain,
            )
        )
    moments = [
        _moment(e)
        for e in sorted(
            [*report.phase_transitions, *report.milestones, *report.failures],
            key=lambda e: (e.tick, e.category, e.key),
        )
        if _is_key_moment(e)
    ]
    return BlackBoxView(
        session_id=session_id,
        timeline_id=timeline_id,
        state_version=state_version,
        mission_status=report.status,
        final_tick=report.final_tick,
        outcome=outcome,
        blocked_tiers=dict(blocked),
        shortfalls=shortfalls,
        key_moments=moments,
        decisions_count=len(report.decisions),
        counterfactuals_evaluated=counterfactuals,
    )


# ============================================================================== history
class PhaseEntryView(View):
    phase: str
    tick: int


class MissionHistoryView(View):
    session_id: str
    timeline_id: str
    state_version: int
    tick: int
    decisions: list[DecisionEntryView]
    phases: list[PhaseEntryView]
    events: list[EventView]
    events_truncated: bool


def build_history(
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
    state: MissionState,
    records: Sequence[DecisionRecord],
    events: Sequence[MissionEvent],
    limit: int,
) -> MissionHistoryView:
    """The known past of a timeline: its effective decisions (incl. inherited ones), phase
    entries and mission events up to now (``limit`` events, most recent kept)."""
    views = [event_view(e) for e in events]
    truncated = len(views) > limit
    return MissionHistoryView(
        session_id=session_id,
        timeline_id=timeline_id,
        state_version=state_version,
        tick=state.tick,
        decisions=[decision_entry(r, timeline_id) for r in records],
        phases=[PhaseEntryView(phase=h.phase, tick=h.tick) for h in state.phase_history],
        events=views[-limit:] if truncated else views,
        events_truncated=truncated,
    )


# ============================================================================== rewind
class RewindPointView(View):
    decision_id: str
    sequence: int
    tick: int
    phase: str
    decision_type: str
    option_id: str
    inherited: bool
    decisions_discarded_if_replaced: int


class RewindPointsView(View):
    session_id: str
    timeline_id: str
    state_version: int
    points: list[RewindPointView]


def build_rewind_points(
    records: Sequence[DecisionRecord],
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
) -> RewindPointsView:
    total = len(records)
    return RewindPointsView(
        session_id=session_id,
        timeline_id=timeline_id,
        state_version=state_version,
        points=[
            RewindPointView(
                decision_id=r.decision_id,
                sequence=r.sequence,
                tick=r.tick,
                phase=r.phase,
                decision_type=r.decision_type,
                option_id=decision_to_option_id(r.inputs),
                inherited=r.timeline_id != timeline_id,
                decisions_discarded_if_replaced=total - i,
            )
            for i, r in enumerate(records)
        ],
    )


class ForkPreviewView(View):
    session_id: str
    timeline_id: str
    replaced_decision: DecisionEntryView
    fork_tick: int
    inherited_decisions: int
    discarded_decisions: int
    state_at_fork: MissionHUD
    statement: str = (
        "A branch starts from the state just before the replaced decision; the source timeline "
        "is never modified. Nothing has been created yet."
    )


class TimelineNodeView(View):
    id: str
    label: str
    parent_timeline_id: str | None
    children: list[str]
    fork_tick: int | None
    fork_sequence: int | None
    replaced_decision_id: str | None
    alternative_option_id: str | None
    status: str
    is_active: bool
    head_tick: int
    head_sequence: int
    state_version: int
    outcome_code: str | None
    outcome_tier: str | None


class TimelineTreeView(View):
    session_id: str
    active_timeline_id: str | None
    timelines: list[TimelineNodeView]


class TimelineChangeView(View):
    """Result of creating a branch (also the ``TIMELINE_CHANGED`` payload shape)."""

    timeline: TimelineRef
    parent_timeline_id: str
    replaced_decision_id: str
    alternative_decision: DecisionEntryView | None
    state_version: int
    active: bool
    hud: MissionHUD


# ============================================================================== profile, DNA
class ProfileDimensionView(View):
    id: str
    value: float
    contributions: dict[str, float]


class EngineeringProfileView(View):
    session_id: str
    timeline_id: str
    state_version: int
    weights_version: str
    provisional: bool
    archetype: str | None = Field(None, description="Not supported until D5 is decided")
    dimensions: list[ProfileDimensionView]
    explanation_inputs: dict[str, float]
    coverage: dict[str, Any]
    notes: list[str]


def build_profile_view(
    profile: EngineeringProfile,
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
    concluded: bool,
    lens_requests: int,
) -> EngineeringProfileView:
    return EngineeringProfileView(
        session_id=session_id,
        timeline_id=timeline_id,
        state_version=state_version,
        weights_version=profile.weights_version,
        provisional=profile.provisional,
        dimensions=[
            ProfileDimensionView(
                id=d.dimension,
                value=rnd(d.score, 3),
                contributions={k: rnd(v, 3) for k, v in d.contributions.items()},
            )
            for d in profile.dimensions
        ],
        explanation_inputs={k: rnd(v, 3) for k, v in profile.features.items()},
        coverage={
            "decisions_analysed": profile.decision_count,
            "ticks_analysed": profile.ticks_analysed,
            "mission_concluded": concluded,
            "future_lens_requests": lens_requests,
        },
        notes=list(profile.notes),
    )


class MissionDNAView(View):
    code: str
    dna_version: int
    scenario_id: str
    scenario_version: str
    outcome_code: str | None
    outcome_tier: str | None
    concluded: bool
    genes: dict[str, Any]
    comparison_fields: list[str]
    share_safe: bool = True


def build_dna_view(engine: SimulationEngine, dna: MissionDNA, *, concluded: bool) -> MissionDNAView:
    outcome = str(dna.genes.get("outcome", "in_progress"))
    tier = None
    if concluded:
        rule = next((r for r in engine.scenario.outcomes if r.code == outcome), None)
        tier = rule.effective_tier if rule else outcome_tier(engine, outcome, "")
    return MissionDNAView(
        code=dna.code,
        dna_version=dna.version,
        scenario_id=engine.scenario.id,
        scenario_version=engine.scenario.version,
        outcome_code=outcome if concluded else None,
        outcome_tier=tier,
        concluded=concluded,
        genes=dict(dna.genes),
        comparison_fields=sorted(dna.genes),
    )


# ============================================================================== science claims
class EvidenceSourceView(View):
    name: str
    citation: str | None
    url: str | None
    retrieved_date: str


class ScienceClaimView(View):
    id: str
    concept: str
    claim: str
    value: float | None
    unit: str | None
    source: EvidenceSourceView
    provenance: Literal["primary_source", "secondary_source", "unverified"]
    verification_status: str
    verified: bool
    status_label: str
    simulation_usage: list[str]
    simplification: str
    confidence: str
    notes: str | None


_PROVENANCE: dict[str, Literal["primary_source", "secondary_source", "unverified"]] = {
    "verified_primary": "primary_source",
    "verified_secondary": "secondary_source",
    "unverified": "unverified",
}
_STATUS_LABELS = {
    "verified_primary": "Verified — primary source",
    "verified_secondary": "Verified — secondary source",
    "unverified": "Unverified — educational abstraction, not established science",
}


def _hidden_events() -> frozenset[str]:
    from app.simulation.scenarios.loader import list_scenarios

    return unforeseeable_event_ids(list_scenarios())


def build_claim(e: ScienceEvidence) -> ScienceClaimView:
    return ScienceClaimView(
        id=e.id,
        concept=e.concept,
        claim=e.claim,
        value=e.value,
        unit=e.unit,
        source=EvidenceSourceView(
            name=e.source_name,
            citation=e.source_citation,
            url=str(e.source_url) if e.source_url else None,
            retrieved_date=e.retrieved_date,
        ),
        provenance=_PROVENANCE[e.verification_status],
        verification_status=e.verification_status,
        verified=e.verification_status.startswith("verified"),
        status_label=_STATUS_LABELS[e.verification_status],
        simulation_usage=redact_usage(e.simulation_usage, _hidden_events()),
        simplification=e.simplification,
        confidence=e.confidence,
        notes=e.notes,
    )
