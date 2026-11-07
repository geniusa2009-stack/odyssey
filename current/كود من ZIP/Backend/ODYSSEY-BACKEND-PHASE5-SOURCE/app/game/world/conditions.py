"""Evaluation of content conditions over game state, campaign progress and the simulation."""

from __future__ import annotations

from dataclasses import dataclass

from app.game.content.loader import LoadedContent
from app.game.content.schema import GameCondition
from app.game.world.sim import SimView
from app.game.world.state import CampaignMeta, TimelineGameState
from app.simulation.scenarios.schema import Condition

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass(frozen=True, slots=True)
class Ctx:
    content: LoadedContent
    doc: TimelineGameState
    meta: CampaignMeta
    sim: SimView


def capability_stage_met(content: LoadedContent, meta: CampaignMeta, cap: str, stage: str) -> bool:
    current = meta.capabilities.get(cap)
    if current is None:
        return False
    ladder = content.index.capabilities[cap].stages
    return ladder.index(current) >= ladder.index(stage)


def item_count(doc: TimelineGameState, item: str, container: str | None) -> int:
    if container is not None:
        return doc.containers.get(container, {}).get(item, 0)
    return sum(c.get(item, 0) for c in doc.containers.values())


def sim_condition(c: Condition, sim: SimView) -> bool:
    if c.metric is not None:
        if not sim.has_metric(c.metric):
            return False  # a condition about another mission's simulation
        assert c.op is not None
        assert c.value is not None
        return bool(_OPS[c.op](sim.metric(c.metric), c.value))
    if c.all is not None:
        return all(sim_condition(x, sim) for x in c.all)
    if c.any is not None:
        return any(sim_condition(x, sim) for x in c.any)
    assert c.not_ is not None
    return not sim_condition(c.not_, sim)


def holds(cond: GameCondition | None, ctx: Ctx) -> bool:
    """``None`` holds. Exactly one key of a condition is set (validated by the schema)."""
    if cond is None:
        return True
    doc = ctx.doc
    if cond.all is not None:
        return all(holds(c, ctx) for c in cond.all)
    if cond.any is not None:
        return any(holds(c, ctx) for c in cond.any)
    if cond.not_ is not None:
        return not holds(cond.not_, ctx)
    if cond.flag is not None:
        return doc.has_flag(cond.flag)
    if cond.location is not None:
        return doc.player_location == cond.location
    if cond.incident is not None:
        inc = doc.incidents.get(cond.incident.id)
        return inc is not None and inc.stage in cond.incident.stages
    if cond.sim is not None:
        return sim_condition(cond.sim, ctx.sim)
    if cond.sim_event is not None:
        return ctx.sim.has_event(cond.sim_event) and ctx.sim.event_fired(cond.sim_event)
    if cond.alert is not None:
        return ctx.sim.has_alert(cond.alert) and ctx.sim.alert_active(cond.alert)
    if cond.item is not None:
        return item_count(doc, cond.item.item, cond.item.container) >= cond.item.min_quantity
    if cond.module_installed is not None:
        mc = cond.module_installed
        installed = doc.modules.get(mc.host, {}).get(mc.slot)
        return installed is not None and (mc.module is None or installed.item == mc.module)
    if cond.capability is not None:
        return capability_stage_met(
            ctx.content, ctx.meta, cond.capability.capability, cond.capability.stage
        )
    if cond.object_state is not None:
        os_ = cond.object_state
        obj = doc.objects.get(os_.object)
        if obj is None:
            return False
        return bool(getattr(obj, os_.field) == os_.equals)
    if cond.mission is not None:
        progress = ctx.meta.missions.get(cond.mission.mission)
        if cond.mission.status == "active":
            return ctx.meta.active_mission == cond.mission.mission
        return progress is not None and progress.status == cond.mission.status
    if cond.sim_outcome is not None:
        tier = ctx.sim.outcome_tier()
        return ctx.sim.concluded and tier in cond.sim_outcome.tiers
    raise AssertionError("unreachable: condition without a key")  # pragma: no cover
