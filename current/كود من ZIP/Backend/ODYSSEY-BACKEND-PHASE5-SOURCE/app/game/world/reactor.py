"""World reactions to simulation and game changes (pure, deterministic).

Run after every authoritative change (an action's effects, simulation decisions, clock
advancement). Evaluates, to a fixpoint: incident triggers/stages/facts, location unlocks and
automatic insight unlocks; then selects at most one crew cue. Incidents stay invisible until
their trigger has happened in the simulation, so nothing here can leak a future event.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.game.content.schema import Incident
from app.game.world.conditions import Ctx, holds
from app.game.world.effects import apply_effects, unlock_insight
from app.game.world.state import MAX_RECENT_CUES, CueFire, IncidentState

MAX_PASSES = 6


@dataclass(slots=True)
class Reaction:
    incidents_started: list[str] = field(default_factory=list)
    incidents_resolved: list[str] = field(default_factory=list)
    pause_requested: bool = False
    cue: CueFire | None = None


def _stage(inc: Incident, ctx: Ctx) -> tuple[str, bool]:
    for st in inc.stages:
        if holds(st.when, ctx):
            return st.id, st.terminal
    last = inc.stages[-1]  # validated: unconditional
    return last.id, last.terminal


def _enter_stage(ctx: Ctx, inc: Incident, stage_id: str, default_container: str | None) -> None:
    spec = next(s for s in inc.stages if s.id == stage_id)
    apply_effects(
        ctx.content,
        ctx.doc,
        ctx.meta,
        spec.effects,
        tick=ctx.sim.tick,
        default_container=default_container,
    )


def react(ctx: Ctx, *, default_container: str | None) -> Reaction:
    out = Reaction()
    content, doc, meta, tick = ctx.content, ctx.doc, ctx.meta, ctx.sim.tick
    world = content.index.worlds[doc.world_id]
    for _ in range(MAX_PASSES):
        changed = False
        for inc in world.incidents:
            if inc.mission != doc.mission_id:
                continue
            state = doc.incidents.get(inc.id)
            if state is None:
                if not holds(inc.trigger, ctx):
                    continue
                stage, terminal = _stage(inc, ctx)
                doc.incidents[inc.id] = state = IncidentState(
                    id=inc.id, stage=stage, started_tick=tick
                )
                apply_effects(
                    content,
                    doc,
                    meta,
                    inc.start_effects,
                    tick=tick,
                    default_container=default_container,
                )
                _enter_stage(ctx, inc, stage, default_container)
                out.incidents_started.append(inc.id)
                if inc.pause_clock_on_start:
                    out.pause_requested = True
                if terminal:
                    state.resolved_tick = tick
                    out.incidents_resolved.append(inc.id)
                changed = True
                continue
            if state.resolved_tick is not None:
                continue
            for fact in inc.facts:
                if fact.id not in state.facts and holds(fact.when, ctx):
                    state.facts.append(fact.id)
                    doc.set_flag(f"fact:{inc.id}:{fact.id}")
                    changed = True
            stage, terminal = _stage(inc, ctx)
            if stage != state.stage:
                state.stage = stage
                _enter_stage(ctx, inc, stage, default_container)
                if terminal:
                    state.resolved_tick = tick
                    out.incidents_resolved.append(inc.id)
                changed = True
        for loc in world.locations:
            if (
                doc.locations.get(loc.id) == "locked"
                and loc.unlock_when is not None
                and holds(loc.unlock_when, ctx)
            ):
                doc.locations[loc.id] = "open"
                changed = True
        for ins in content.content.knowledge.insights:
            if ins.unlock is not None and ins.id not in doc.insights and holds(ins.unlock, ctx):
                unlock_insight(doc, meta, ins.id)
                changed = True
        if not changed:
            break
    out.cue = select_cue(ctx)
    return out


def select_cue(ctx: Ctx) -> CueFire | None:
    """At most one cue per reaction: the highest-priority eligible one (ties by id)."""
    doc, tick = ctx.doc, ctx.sim.tick
    eligible = []
    for cue in ctx.content.content.narrative.cues:
        last = doc.cue_last_tick.get(cue.id)
        if last is not None and (cue.once or tick - last < max(cue.cooldown_ticks, 1)):
            continue
        if holds(cue.when, ctx):
            eligible.append(cue)
    if not eligible:
        return None
    best = min(eligible, key=lambda c: (-c.priority, c.id))
    doc.cue_last_tick[best.id] = tick
    fire = CueFire(
        cue=best.id,
        speaker=best.speaker,
        priority=best.priority,
        tick=tick,
        line=best.line,
        message_key=best.message_key,
    )
    doc.recent_cues = [*doc.recent_cues, fire][-MAX_RECENT_CUES:]
    return fire
