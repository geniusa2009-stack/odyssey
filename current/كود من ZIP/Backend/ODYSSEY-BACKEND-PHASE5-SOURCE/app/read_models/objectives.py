"""Objective outlook read model.

For each objective: its pillar, status, the (non-secret) rule it is judged by with the current
measured values, a completion fraction where the rule is a single "reach at least X" target, a
margin where it is a single "stay within X" constraint, and blockers observable *now*.

What it never does: estimate probabilities, or reveal anything about future events. Tier
"still possible" flags are logic over the scenario's outcome rules and current objective
statuses ("has a required objective already failed?"), not forecasts.
"""

from __future__ import annotations

from typing import Literal

from app.read_models.common import View, rnd, rnd_unit
from app.simulation.domain.enums import ObjectiveStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.schema import OUTCOME_TIERS, Condition, ObjectiveDefinition

ObjectiveKind = Literal["achieve", "avoid", "achieve_at_end"]
BETTER_TIERS = ("partial", "success", "exceptional")
_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


class ConditionView(View):
    """A rule as data. Leaves carry the metric, target and current value."""

    metric: str | None = None
    label: str | None = None
    unit: str | None = None
    op: str | None = None
    target: float | None = None
    current: float | None = None
    met: bool | None = None
    all: list[ConditionView] | None = None
    any: list[ConditionView] | None = None
    negate: ConditionView | None = None


class Blocker(View):
    code: Literal["objective_failed", "input_critical"]
    metric: str | None = None
    label: str | None = None
    value: float | None = None
    unit: str | None = None
    tick: int | None = None


class ObjectiveView(View):
    id: str
    category: str
    required: bool
    status: str
    kind: ObjectiveKind
    evaluated: Literal["continuously", "at_mission_end"]
    resolved_tick: int | None
    rule: ConditionView
    completion_fraction: float | None
    margin: float | None
    margin_unit: str | None
    blockers: list[Blocker]
    message_key: str


class PillarSummary(View):
    category: str
    total: int
    achieved: int
    failed: int
    pending: int


class TierOutlook(View):
    tier: str
    still_possible: bool
    blocked_by: list[str]


class ObjectiveOutlookView(View):
    objectives: list[ObjectiveView]
    pillars: list[PillarSummary]
    tiers: list[TierOutlook]
    tier_statement: str = (
        "still_possible is logic over the outcome rules and the objective statuses now: a tier "
        "is no longer possible once an objective it requires has failed. It is not a probability."
    )


def _condition(engine: SimulationEngine, state: MissionState, c: Condition) -> ConditionView:
    if c.metric is not None:
        spec = engine.metrics.spec(c.metric)
        current = engine.metrics.value(c.metric, state)
        assert c.op is not None
        assert c.value is not None
        return ConditionView(
            metric=c.metric,
            label=spec.label,
            unit=spec.unit,
            op=c.op,
            target=c.value,
            current=rnd_unit(current, spec.unit),
            met=bool(_OPS[c.op](current, c.value)),
        )
    if c.all is not None:
        return ConditionView(all=[_condition(engine, state, x) for x in c.all])
    if c.any is not None:
        return ConditionView(any=[_condition(engine, state, x) for x in c.any])
    assert c.not_ is not None
    return ConditionView(negate=_condition(engine, state, c.not_))


def _kind(spec: ObjectiveDefinition) -> ObjectiveKind:
    if spec.evaluate == "at_end":
        return "achieve_at_end"
    return "achieve" if spec.achieve_when is not None else "avoid"


def _leaf_metrics(c: Condition) -> list[str]:
    return sorted(c.metrics())


def build_objective(
    engine: SimulationEngine, state: MissionState, spec: ObjectiveDefinition
) -> ObjectiveView:
    obj = state.objectives[spec.id]
    cond = spec.achieve_when or spec.fail_when
    assert cond is not None
    rule = _condition(engine, state, cond)
    kind = _kind(spec)
    completion = margin = None
    margin_unit = None
    if cond.metric is not None and cond.value is not None:
        current = engine.metrics.value(cond.metric, state)
        unit = engine.metrics.spec(cond.metric).unit
        if kind == "achieve" and cond.op in (">=", ">") and cond.value > 0:
            completion = rnd(min(1.0, max(0.0, current / cond.value)), 3)
        if kind == "avoid":
            # distance from the failure threshold; positive = still inside the limit
            raw = cond.value - current if cond.op in (">", ">=") else current - cond.value
            margin, margin_unit = rnd_unit(raw, unit), unit
    if obj.status == ObjectiveStatus.ACHIEVED:
        completion = 1.0 if completion is not None else None
    blockers: list[Blocker] = []
    if obj.status == ObjectiveStatus.FAILED:
        blockers.append(Blocker(code="objective_failed", tick=obj.resolved_tick))
    elif obj.status == ObjectiveStatus.PENDING and kind == "achieve":
        seen: set[str] = set()
        for metric in _leaf_metrics(cond):
            for edge in engine.graph.parents(metric):
                src = edge.source
                if src in seen or engine.metrics.spec(src).severity is None:
                    continue
                seen.add(src)
                if engine.metrics.severity(src, state) >= 1.0 - 1e-9:
                    spec_src = engine.metrics.spec(src)
                    blockers.append(
                        Blocker(
                            code="input_critical",
                            metric=src,
                            label=spec_src.label,
                            value=rnd_unit(engine.metrics.value(src, state), spec_src.unit),
                            unit=spec_src.unit,
                        )
                    )
    return ObjectiveView(
        id=spec.id,
        category=spec.effective_category,
        required=spec.required,
        status=obj.status.value,
        kind=kind,
        evaluated="at_mission_end" if spec.evaluate == "at_end" else "continuously",
        resolved_tick=obj.resolved_tick,
        rule=rule,
        completion_fraction=completion,
        margin=margin,
        margin_unit=margin_unit,
        blockers=blockers,
        message_key=f"objective.{spec.id}",
    )


def build_objectives(engine: SimulationEngine, state: MissionState) -> ObjectiveOutlookView:
    sc = engine.scenario
    views = [build_objective(engine, state, o) for o in sc.objectives]
    by_cat: dict[str, list[ObjectiveView]] = {}
    for v in views:
        by_cat.setdefault(v.category, []).append(v)
    pillars = [
        PillarSummary(
            category=cat,
            total=len(vs),
            achieved=sum(1 for v in vs if v.status == "achieved"),
            failed=sum(1 for v in vs if v.status == "failed"),
            pending=sum(1 for v in vs if v.status == "pending"),
        )
        for cat, vs in by_cat.items()
    ]
    status = {v.id: v.status for v in views}
    tiers: list[TierOutlook] = []
    # tiers above "mission_failed": what a player can still aim for
    for tier in [t for t in reversed(OUTCOME_TIERS) if t in BETTER_TIERS]:
        rules = [r for r in sc.outcomes if r.effective_tier == tier]
        if not rules:
            continue
        blocked: set[str] = set()
        possible = False
        for rule in rules:
            needed = [
                o.id
                for o in sc.objectives
                if o.effective_category in (rule.requires_categories or [])
                or (rule.requires_required_objectives and o.required)
            ]
            failed = {o for o in needed if status[o] == "failed"}
            blocked |= failed
            if not failed:
                possible = True
        tiers.append(TierOutlook(tier=tier, still_possible=possible, blocked_by=sorted(blocked)))
    return ObjectiveOutlookView(objectives=views, pillars=pillars, tiers=tiers)
