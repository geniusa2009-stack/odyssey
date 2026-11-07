"""End-of-tick mission logic: alerts, cascade warnings, objectives, outcome, phases."""

from __future__ import annotations

from app.simulation.domain.enums import (
    AlertSeverity,
    EventKind,
    MissionStatus,
    ObjectiveStatus,
)
from app.simulation.domain.state import AlertState, OutcomeState, PhaseTransition
from app.simulation.engine.conditions import compare, evaluate
from app.simulation.engine.context import TickContext
from app.simulation.engine.dependency_graph import DependencyGraph
from app.simulation.scenarios.schema import AlertRule, OutcomeRule


def _cleared(rule: AlertRule, value: float) -> bool:
    if rule.op in ("<", "<="):
        return value >= rule.clear_threshold
    return value <= rule.clear_threshold


def evaluate_alerts(ctx: TickContext) -> None:
    st = ctx.state
    for rule in ctx.scenario.alerts:
        value = ctx.metrics.value(rule.metric, st)
        active = rule.id in st.alerts
        if not active and compare(value, rule.op, rule.threshold):
            st.alerts[rule.id] = AlertState(
                id=rule.id,
                severity=rule.severity,
                metric=rule.metric,
                raised_tick=ctx.tick,
                value=value,
            )
            kind = (
                EventKind.RESOURCE_WARNING
                if rule.category == "resource"
                else EventKind.ALERT_RAISED
            )
            ctx.emit(
                kind,
                rule.id,
                severity=rule.severity,
                message_key=f"alert.{rule.id}",
                data={
                    "metric": rule.metric,
                    "value": value,
                    "threshold": rule.threshold,
                    "category": rule.category,
                },
            )
        elif active and _cleared(rule, value):
            del st.alerts[rule.id]
            ctx.emit(
                EventKind.ALERT_CLEARED,
                rule.id,
                message_key=f"alert.{rule.id}.cleared",
                data={"metric": rule.metric, "value": value},
            )
        elif active:
            st.alerts[rule.id].value = value


def evaluate_cascades(ctx: TickContext, graph: DependencyGraph) -> None:
    """Warn when a degraded system is propagating degradation downstream.

    An edge is *active* when its source severity ≥ parent threshold and its target severity ≥
    child threshold. Newly active edges are grouped into one warning per source node.
    """
    an = ctx.scenario.analysis
    st = ctx.state
    previously = set(st.cascade_edges_active)
    now: set[str] = set()
    new_by_source: dict[str, list[dict[str, object]]] = {}
    source_sev: dict[str, float] = {}
    for edge in graph.system_edges():
        p = ctx.metrics.severity(edge.source, st)
        if p < an.cascade_parent_threshold:
            continue
        c = ctx.metrics.severity(edge.target, st)
        if c < an.cascade_child_threshold:
            continue
        now.add(edge.key)
        if edge.key not in previously:
            source_sev[edge.source] = p
            new_by_source.setdefault(edge.source, []).append(
                {"target": edge.target, "mechanism": edge.mechanism, "target_severity": c}
            )
    for source in sorted(new_by_source):
        ctx.emit(
            EventKind.CASCADE_WARNING,
            f"cascade:{source}",
            severity=AlertSeverity.WARNING,
            message_key="cascade.warning",
            data={
                "source": source,
                "source_severity": source_sev[source],
                "targets": new_by_source[source],
            },
        )
    st.cascade_edges_active = sorted(now)


def evaluate_objectives(ctx: TickContext, *, final: bool) -> None:
    st = ctx.state
    for spec in ctx.scenario.objectives:
        obj = st.objectives[spec.id]
        if obj.status != ObjectiveStatus.PENDING:
            continue
        new_status: ObjectiveStatus | None = None
        if spec.evaluate == "continuous":
            if spec.fail_when is not None and evaluate(spec.fail_when, st, ctx.metrics):
                new_status = ObjectiveStatus.FAILED
            elif spec.achieve_when is not None and evaluate(spec.achieve_when, st, ctx.metrics):
                new_status = ObjectiveStatus.ACHIEVED
            elif final:
                new_status = (
                    ObjectiveStatus.ACHIEVED
                    if spec.achieve_when is None
                    else ObjectiveStatus.FAILED
                )
        elif final:
            ok = spec.achieve_when is None or evaluate(spec.achieve_when, st, ctx.metrics)
            failed = spec.fail_when is not None and evaluate(spec.fail_when, st, ctx.metrics)
            new_status = ObjectiveStatus.ACHIEVED if ok and not failed else ObjectiveStatus.FAILED
        if new_status is not None:
            obj.status = new_status
            obj.resolved_tick = ctx.tick
            data: dict[str, object] = {
                "objective": spec.id,
                "status": new_status.value,
                "required": spec.required,
            }
            if spec.category is not None:  # scenarios without categories keep v0.1.0 events
                data["category"] = spec.category
            ctx.emit(
                EventKind.OBJECTIVE,
                spec.id,
                message_key=f"objective.{new_status.value}",
                data=data,
            )


def _rule_matches(ctx: TickContext, rule: OutcomeRule) -> bool:
    st = ctx.state
    specs = ctx.scenario.objectives
    if rule.requires_required_objectives is not None:
        all_req = all(
            st.objectives[o.id].status == ObjectiveStatus.ACHIEVED for o in specs if o.required
        )
        if all_req != rule.requires_required_objectives:
            return False
    if rule.min_optional_objectives_fraction is not None:
        optional = [o for o in specs if not o.required]
        if optional:
            done = sum(
                1 for o in optional if st.objectives[o.id].status == ObjectiveStatus.ACHIEVED
            )
            if done / len(optional) < rule.min_optional_objectives_fraction - 1e-12:
                return False
    if rule.category_refs():
        by_cat: dict[str, list[ObjectiveStatus]] = {}
        for o in specs:
            by_cat.setdefault(o.effective_category, []).append(st.objectives[o.id].status)
        for cat in rule.requires_categories or []:
            if any(status != ObjectiveStatus.ACHIEVED for status in by_cat.get(cat, [])):
                return False
        for cat, minimum in (rule.min_achieved_in_categories or {}).items():
            if sum(1 for x in by_cat.get(cat, []) if x == ObjectiveStatus.ACHIEVED) < minimum:
                return False
        if rule.any_failed_in_categories is not None and not any(
            x == ObjectiveStatus.FAILED
            for cat in rule.any_failed_in_categories
            for x in by_cat.get(cat, [])
        ):
            return False
    return rule.when is None or evaluate(rule.when, st, ctx.metrics)


def _conclude(ctx: TickContext, rule: OutcomeRule) -> None:
    st = ctx.state
    evaluate_objectives(ctx, final=True)
    achieved = sorted(k for k, v in st.objectives.items() if v.status == ObjectiveStatus.ACHIEVED)
    failed = sorted(k for k, v in st.objectives.items() if v.status == ObjectiveStatus.FAILED)
    st.outcome = OutcomeState(
        code=rule.code,
        tick=ctx.tick,
        rule_id=rule.id,
        objectives_achieved=achieved,
        objectives_failed=failed,
    )
    st.status = MissionStatus.CONCLUDED
    ctx.emit(
        EventKind.OUTCOME,
        rule.code,
        message_key=f"outcome.{rule.code}",
        data=(
            {"rule": rule.id, "achieved": achieved, "failed": failed}
            | ({"tier": rule.tier} if rule.tier is not None else {})
        ),
    )
    for phase in ctx.scenario.phases:
        if phase.kind in ("conclusion", "analysis"):
            _enter_phase(ctx, phase.id)


def evaluate_outcome(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    for rule in sc.outcomes:
        if not rule.at_end and _rule_matches(ctx, rule):
            _conclude(ctx, rule)
            return
    if st.tick >= sc.time.max_ticks:
        # Final objective resolution must precede at_end rule matching.
        evaluate_objectives(ctx, final=True)
        for rule in sc.outcomes:
            if rule.at_end and _rule_matches(ctx, rule):
                _conclude(ctx, rule)
                return


def _enter_phase(ctx: TickContext, phase_id: str) -> None:
    st = ctx.state
    previous = st.phase
    st.phase = phase_id
    st.phase_history.append(PhaseTransition(phase=phase_id, tick=ctx.tick))
    ctx.emit(
        EventKind.PHASE_CHANGE,
        phase_id,
        message_key=f"phase.{phase_id}",
        data={"from": previous, "to": phase_id},
    )


def advance_phase(ctx: TickContext) -> None:
    sc, st = ctx.scenario, ctx.state
    ids = [p.id for p in sc.phases]
    idx = ids.index(st.phase)
    current = sc.phases[idx]
    if current.kind != "simulated" or current.advance_when is None:
        return
    if idx + 1 >= len(sc.phases) or sc.phases[idx + 1].kind != "simulated":
        return
    if evaluate(current.advance_when, st, ctx.metrics):
        _enter_phase(ctx, sc.phases[idx + 1].id)
