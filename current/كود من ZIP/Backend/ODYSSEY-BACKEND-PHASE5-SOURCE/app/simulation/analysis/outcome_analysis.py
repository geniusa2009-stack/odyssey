"""Outcome analysis: why the mission ended in its tier, objective by objective.

For every FAILED objective the analysis names:

* the **triggering condition**: the objective's own rule and the recorded metric value that
  met it (``fail_when`` at the resolution tick), or the unmet target at mission end
  (``achieve_when`` objectives that were never achieved);
* the **root decisions**, only when counterfactual replay shows that removing the decision
  changes the triggering metric in the harmful direction (``decision_worsened_target``).
  Decisions on a causal path whose removal changes nothing are reported separately as
  ``on_path_no_effect`` and never blamed;
* the **intermediate system effects**: metrics on the traced causal chains between the roots
  and the trigger;
* the **consequence**: which better outcome tier the failure blocked.

Objectives whose metric has no severity scale (science points, downlinked data, completed
campaigns) cannot be traced through degraded states. They are explained by recorded facts
instead (opportunities missed or never started, data produced but not sent, link outages),
labelled ``omission``. Nothing is inferred beyond the recorded history and the declared
dependency graph.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.analysis.root_cause import Counterfactual, RootCauseTrace, trace_root_cause
from app.simulation.domain.enums import EventKind, ObjectiveStatus
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine.conditions import compare
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.schema import OUTCOME_TIERS, Condition, ObjectiveDefinition

ChainKind = Literal["traced", "omission", "untraced"]


class TriggerCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    op: str
    threshold: float
    value: float = Field(description="Recorded value at the evaluation tick")
    tick: int


class RootDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    decision_type: str | None = None
    tick: int | None = None
    verdict: str = Field(description="Counterfactual verdict for the triggering metric")


class FailureChain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    category: str
    kind: ChainKind
    resolved_tick: int | None
    triggers: list[TriggerCondition]
    root_decisions: list[RootDecision] = Field(
        default_factory=list,
        description="Verified by counterfactual replay: the decision made the trigger worse",
    )
    on_path_no_effect: list[RootDecision] = Field(
        default_factory=list, description="On a causal path, but removing it changes nothing"
    )
    other_roots: list[str] = Field(
        default_factory=list, description="Non-decision causes: events, environment, faults"
    )
    intermediate_effects: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list, description="Recorded facts (omissions)")
    trace_index: int | None = Field(None, description="Index into BlackBoxReport.causal_traces")
    consequence: str


class OutcomeAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_code: str
    tier: str | None
    rule_id: str
    blocked_tiers: dict[str, list[str]] = Field(
        description="Better tier → failed objectives that blocked it"
    )
    chains: list[FailureChain]


def _leaf_conditions(cond: Condition) -> list[Condition]:
    if cond.metric is not None:
        return [cond]
    out: list[Condition] = []
    for child in [*(cond.all or []), *(cond.any or [])]:
        out += _leaf_conditions(child)
    if cond.not_ is not None:
        out += _leaf_conditions(cond.not_)
    return out


def _state_at(history: list[MissionState], tick: int) -> MissionState:
    base = history[0].tick
    return history[min(max(0, tick - base), len(history) - 1)]


def _triggers(
    engine: SimulationEngine, cond: Condition, state: MissionState, *, met: bool
) -> list[TriggerCondition]:
    """Leaf conditions that are met (``met=True``) / not met at ``state``."""
    out: list[TriggerCondition] = []
    for leaf in _leaf_conditions(cond):
        assert leaf.metric is not None
        assert leaf.op is not None
        assert leaf.value is not None
        value = engine.metrics.value(leaf.metric, state)
        if compare(value, leaf.op, leaf.value) == met:
            out.append(
                TriggerCondition(
                    metric=leaf.metric,
                    op=leaf.op,
                    threshold=leaf.value,
                    value=value,
                    tick=state.tick,
                )
            )
    return out


def _blocked(engine: SimulationEngine, final: MissionState) -> dict[str, list[str]]:
    """For every rule of a better tier, the failed/unachieved objectives it required."""
    sc = engine.scenario
    assert final.outcome is not None
    try:
        tier = sc.outcome_rule(final.outcome.rule_id).effective_tier
    except KeyError:
        tier = None
    rank = OUTCOME_TIERS.index(tier) if tier in OUTCOME_TIERS else -1
    out: dict[str, list[str]] = {}
    for rule in sc.outcomes:
        t = rule.effective_tier
        if t is None or t not in OUTCOME_TIERS or OUTCOME_TIERS.index(t) <= rank:
            continue
        missing: list[str] = []
        for o in sc.objectives:
            status = final.objectives[o.id].status
            needed = o.effective_category in (rule.requires_categories or []) or (
                rule.requires_required_objectives and o.required
            )
            if needed and status != ObjectiveStatus.ACHIEVED:
                missing.append(o.id)
        if missing:
            out.setdefault(t, sorted(set(out.get(t, [])) | set(missing)))
    return out


def _decision_roots(
    trace: RootCauseTrace, info: dict[str, dict[str, Any]]
) -> tuple[list[RootDecision], list[RootDecision], list[str]]:
    blamed: list[RootDecision] = []
    harmless: list[RootDecision] = []
    others: list[str] = []
    nodes = {n.id: n for n in trace.nodes}
    for root in trace.roots:
        node = nodes[root]
        if node.kind != "decision":
            others.append(root)
            continue
        did = root.removeprefix("decision:")
        meta = info.get(did, {})
        cf = node.details.get("counterfactual")
        verdict = cf["verdict"] if cf else "not_checked"
        item = RootDecision(
            decision_id=did,
            decision_type=meta.get("decision_type"),
            tick=node.tick,
            verdict=verdict,
        )
        (blamed if verdict == "decision_worsened_target" else harmless).append(item)
    return blamed, harmless, others


def _intermediates(trace: RootCauseTrace) -> list[str]:
    target = f"metric:{trace.target_metric}"
    seen: list[str] = []
    for chain in trace.chains:
        for node in chain[1:-1]:
            if node != target and node.startswith("metric:") and node not in seen:
                seen.append(node)
    return seen


def _omission_facts(
    engine: SimulationEngine,
    spec: ObjectiveDefinition,
    final: MissionState,
    events: list[MissionEvent],
    decision_types: list[str],
) -> list[str]:
    facts: list[str] = []
    leaves = _leaf_conditions(spec.achieve_when) if spec.achieve_when else []
    metrics = {leaf.metric for leaf in leaves}
    if metrics & {"science.points", "science.opportunities_completed"}:
        for opp in sorted(final.science.opportunities.values(), key=lambda o: o.id):
            if opp.status == "completed":
                facts.append(f"science campaign {opp.id} completed")
            elif opp.status == "missed":
                started = opp.started_by is not None
                facts.append(
                    f"science campaign {opp.id} missed "
                    + ("(started but not finished in its window)" if started else "(never started)")
                )
            else:
                facts.append(f"science campaign {opp.id} {opp.status} at mission end")
        if not any(t in ("start_science_activity", "rover_command") for t in decision_types):
            facts.append("no science activity was ever started")
    if "comms.data_downlinked_mb" in metrics:
        pending = final.science.data_pending_mb
        facts.append(f"{final.comms.data_downlinked_mb:.0f} MB downlinked to Earth")
        if pending > 0:
            facts.append(f"{pending:.0f} MB of science data produced but never sent")
        outages = sum(
            1 for e in events if e.kind == EventKind.COMMUNICATION and e.key == "link_lost"
        )
        if outages:
            facts.append(f"communication link lost {outages} time(s)")
    return facts


def _radiation_facts(
    engine: SimulationEngine,
    spec: ObjectiveDefinition,
    history: list[MissionState],
    events: list[MissionEvent],
) -> list[str]:
    """Where the crew was while radiation was elevated (an omission no decision node shows)."""
    conds = [c for c in (spec.fail_when, spec.achieve_when) if c is not None]
    if not any(leaf.metric == "crew.max_dose_msv" for c in conds for leaf in _leaf_conditions(c)):
        return []
    m = engine.metrics
    background = (
        m.value("env.background_dose_rate_msv_h", history[0])
        if m.has("env.background_dose_rate_msv_h")
        else None
    )
    elevated = [
        s
        for s in history
        if background is not None
        and s.environment.radiation_dose_rate_msv_h > 2.0 * max(background, 1e-9)
    ]
    exposed = [s for s in elevated if m.value("crew.in_shelter", s) == 0.0]
    facts = []
    weather = sorted({e.key for e in events if e.kind == EventKind.SPACE_WEATHER})
    if weather:
        facts.append("radiation events: " + ", ".join(weather))
    if elevated:
        facts.append(
            f"{len(exposed)} of {len(elevated)} elevated-radiation hours spent outside the shelter"
        )
    facts.append(f"highest crew dose {m.value('crew.max_dose_msv', history[-1]):.1f} mSv")
    return facts


def analyse_outcome(
    engine: SimulationEngine,
    history: list[MissionState],
    events: list[MissionEvent],
    decision_info: dict[str, dict[str, Any]],
    *,
    counterfactual: Counterfactual | None = None,
    traces: list[RootCauseTrace] | None = None,
    lookback_ticks: int = 120,
) -> OutcomeAnalysis | None:
    """Explain the outcome; appends the traces it builds to ``traces`` (if given)."""
    final = history[-1]
    if final.outcome is None:
        return None
    sc = engine.scenario
    try:
        tier = sc.outcome_rule(final.outcome.rule_id).effective_tier
    except KeyError:
        tier = None
    decision_types = [str(v.get("decision_type")) for v in decision_info.values()]
    chains: list[FailureChain] = []
    blocked = _blocked(engine, final)
    blocking_index = {o: t for t, objs in blocked.items() for o in objs}
    for spec in sc.objectives:
        obj = final.objectives[spec.id]
        if obj.status != ObjectiveStatus.FAILED:
            continue
        consequence = (
            f"blocked outcome tier '{blocking_index[spec.id]}'"
            if spec.id in blocking_index
            else "did not change the outcome tier"
        )
        if tier == "critical_failure" and spec.id == "crew_survival":
            consequence = "ended the mission (critical failure)"
        # An objective resolved during tick t is evaluated on the state *after* that tick.
        tick = obj.resolved_tick + 1 if obj.resolved_tick is not None else final.tick
        state = _state_at(history, min(tick, final.tick))
        if spec.fail_when is not None and spec.evaluate == "continuous":
            trig = _triggers(engine, spec.fail_when, state, met=True)
        elif spec.achieve_when is not None:
            trig = _triggers(engine, spec.achieve_when, state, met=False)
        else:
            trig = []
        traceable = [t for t in trig if engine.metrics.spec(t.metric).severity is not None]
        if traceable:
            first = traceable[0]
            index: int | None = None
            existing = [
                i
                for i, t in enumerate(traces or [])
                if (t.target_metric, t.target_tick) == (first.metric, first.tick)
            ]
            if existing and traces is not None:
                index = existing[0]
                trace = traces[index]
            else:
                trace = trace_root_cause(
                    engine,
                    history,
                    first.metric,
                    first.tick,
                    start_tick=history[0].tick,
                    lookback_ticks=lookback_ticks,
                    decision_info=decision_info,
                    counterfactual=counterfactual,
                )
                if traces is not None:
                    traces.append(trace)
                    index = len(traces) - 1
            blamed, harmless, others = _decision_roots(trace, decision_info)
            facts = _radiation_facts(engine, spec, history, events)
            chains.append(
                FailureChain(
                    objective=spec.id,
                    category=spec.effective_category,
                    kind="traced",
                    resolved_tick=obj.resolved_tick,
                    triggers=trig,
                    root_decisions=blamed,
                    on_path_no_effect=harmless,
                    other_roots=others,
                    intermediate_effects=_intermediates(trace),
                    facts=facts,
                    trace_index=index,
                    consequence=consequence,
                )
            )
        else:
            facts = _omission_facts(engine, spec, final, events, decision_types)
            chains.append(
                FailureChain(
                    objective=spec.id,
                    category=spec.effective_category,
                    kind="omission" if facts else "untraced",
                    resolved_tick=obj.resolved_tick,
                    triggers=trig,
                    facts=facts,
                    consequence=consequence,
                )
            )
    return OutcomeAnalysis(
        outcome_code=final.outcome.code,
        tier=tier,
        rule_id=final.outcome.rule_id,
        blocked_tiers=blocked,
        chains=chains,
    )
