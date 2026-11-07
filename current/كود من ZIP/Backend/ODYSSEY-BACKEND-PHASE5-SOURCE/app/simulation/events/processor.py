"""Declarative scenario event processing.

Trigger evaluation happens at the start of a tick (before physics) so that modifiers created by
an event affect that same tick. Decision-triggered events fire when the decision is applied.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.simulation.domain.enums import OpportunityStatus, ProvenanceKind
from app.simulation.domain.state import ActiveModifier, MissionState, OpportunityState, Provenance
from app.simulation.engine.conditions import evaluate
from app.simulation.engine.context import TickContext
from app.simulation.scenarios.schema import (
    AdjustResourceEffect,
    DamageComponentEffect,
    DecisionTrigger,
    EventDefinition,
    MilestoneEffect,
    ModifierEffect,
    OpenOpportunityEffect,
    RandomTrigger,
    ScheduledTrigger,
    StateTrigger,
)
from app.simulation.systems.common import clamp


def _can_fire(ctx: TickContext, ev: EventDefinition) -> bool:
    if ev.id in ctx.options.suppressed_events:
        return False
    return ctx.state.event_fire_counts.get(ev.id, 0) < ev.max_fires


def _triggered(ctx: TickContext, ev: EventDefinition) -> bool:
    trig = ev.trigger
    if isinstance(trig, ScheduledTrigger):
        return trig.at_tick == ctx.tick
    if isinstance(trig, StateTrigger):
        return ctx.tick >= trig.after_tick and evaluate(trig.condition, ctx.state, ctx.metrics)
    if isinstance(trig, RandomTrigger):
        in_window = ctx.tick >= trig.from_tick and (trig.to_tick is None or ctx.tick < trig.to_tick)
        return in_window and ctx.chance(f"event:{ev.id}", trig.probability_per_tick)
    return False  # decision triggers are handled by fire_decision_events


def _apply_effects(ctx: TickContext, ev: EventDefinition) -> list[dict[str, object]]:
    st, tick = ctx.state, ctx.tick
    applied: list[dict[str, object]] = []
    for eff in ev.effects:
        if isinstance(eff, ModifierEffect):
            st.modifiers.append(
                ActiveModifier(
                    event_id=ev.id,
                    target=eff.target,
                    op=eff.op,
                    value=eff.value,
                    start_tick=tick,
                    end_tick=tick + eff.duration_ticks,
                )
            )
        elif isinstance(eff, DamageComponentEffect):
            comp = st.components[eff.component]
            comp.health = clamp(comp.health - eff.amount)
            comp.fault_count += 1
            comp.last_damage = Provenance(kind=ProvenanceKind.EVENT, ref=ev.id, tick=tick)
        elif isinstance(eff, OpenOpportunityEffect):
            if eff.opportunity not in st.science.opportunities:
                spec = ctx.scenario.opportunity(eff.opportunity)
                st.science.opportunities[eff.opportunity] = OpportunityState(
                    id=eff.opportunity,
                    status=OpportunityStatus.OPEN,
                    opened_tick=tick,
                    closes_tick=tick + spec.window_ticks,
                    opened_by=Provenance(kind=ProvenanceKind.EVENT, ref=ev.id, tick=tick),
                )
        elif isinstance(eff, AdjustResourceEffect):
            _adjust(st, eff.resource, eff.delta)
        elif isinstance(eff, MilestoneEffect):
            pass
        applied.append(eff.model_dump(mode="json"))
    return applied


def _adjust(st: MissionState, resource: str, delta: float) -> None:
    if resource == "battery_charge_kwh":
        st.power.battery_charge_kwh = max(0.0, st.power.battery_charge_kwh + delta)
    elif resource == "food_kg":
        st.food.food_kg = max(0.0, st.food.food_kg + delta)
    else:
        ls = st.life_support
        setattr(ls, resource, max(0.0, getattr(ls, resource) + delta))


def _fire(ctx: TickContext, ev: EventDefinition, trigger_data: dict[str, object]) -> None:
    effects = _apply_effects(ctx, ev)
    ctx.state.event_fire_counts[ev.id] = ctx.state.event_fire_counts.get(ev.id, 0) + 1
    ctx.emit(
        ev.kind,
        ev.id,
        severity=ev.severity,
        message_key=ev.message_key,
        data={"trigger": trigger_data, "effects": effects, "evidence": list(ev.evidence)},
    )


def process_tick_events(ctx: TickContext) -> None:
    for ev in ctx.scenario.events:  # scenario order = deterministic order
        if isinstance(ev.trigger, DecisionTrigger) or not _can_fire(ctx, ev):
            continue
        if _triggered(ctx, ev):
            _fire(ctx, ev, {"type": ev.trigger.type})


def _matches(match: Mapping[str, object], payload: Mapping[str, object]) -> bool:
    return all(payload.get(k) == v for k, v in match.items())


def fire_decision_events(
    ctx: TickContext, decision_type: str, payload: Mapping[str, object], decision_id: str
) -> None:
    for ev in ctx.scenario.events:
        trig = ev.trigger
        if not isinstance(trig, DecisionTrigger) or not _can_fire(ctx, ev):
            continue
        if trig.decision_type == decision_type and _matches(trig.match, payload):
            _fire(ctx, ev, {"type": "decision", "decision_id": decision_id})
