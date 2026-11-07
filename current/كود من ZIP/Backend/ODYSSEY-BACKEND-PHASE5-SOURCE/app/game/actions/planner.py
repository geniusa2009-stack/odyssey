"""Validation and planning of semantic actions (pure).

``plan(ctx, command)`` checks everything that can be checked before touching the simulation
(mission, target existence and visibility, location, parameters, requirements, resources,
idempotent ``once`` semantics) and returns a :class:`Plan`: the simulation decisions to apply
and a ``finalize`` step that applies the game-side consequences against the *post-decision*
simulation state. The orchestrator dry-runs the whole plan on copies first, so a plan that
would fail midway is rejected before any authoritative change.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.game.actions.errors import GameRuleError, invalid, not_found, unavailable
from app.game.actions.registry import ACTIONS
from app.game.content.rendering import param_effects, rendered_decisions
from app.game.content.schema import Interaction, WorldObject
from app.game.inventory import containers, modules
from app.game.world.conditions import Ctx, holds
from app.game.world.effects import apply_effects
from app.simulation.domain.decisions import DecisionInput, parse_decision

COMMANDER = "commander"
CLOCK_MODES = ("PAUSED", "REALTIME", "ACCELERATED")


@dataclass(frozen=True, slots=True)
class Command:
    action: str
    target: str | None
    params: Mapping[str, Any] = field(default_factory=dict)
    actor: str = COMMANDER


@dataclass(slots=True)
class Outcome:
    result: Literal["applied", "no_change"] = "applied"
    reason: str | None = None
    start_clock: bool = False
    clock_mode: str | None = None
    complete_mission: bool = False
    checkpoint_label: str | None = None
    context: dict[str, Any] | None = None


@dataclass(slots=True)
class Plan:
    action: str
    target: str | None
    decisions: list[DecisionInput]
    finalize: Callable[[Ctx], Outcome]
    mutates: bool = True


# ------------------------------------------------------------------ helpers
def _str_param(cmd: Command, name: str, *, required: bool = True) -> str | None:
    value = cmd.params.get(name)
    if value is None:
        if required:
            raise invalid("missing_parameter", parameter=name)
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        raise invalid("invalid_parameter", parameter=name)
    return value


def _int_param(cmd: Command, name: str) -> int:
    value = cmd.params.get(name, 1)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10_000:
        raise invalid("invalid_parameter", parameter=name)
    return int(value)


def _only_params(cmd: Command, allowed: set[str]) -> None:
    extra = sorted(set(cmd.params) - allowed)
    if extra:
        raise invalid("unknown_parameter", parameters=extra)


def _known_object(ctx: Ctx, object_id: str | None) -> WorldObject:
    if object_id is None:
        raise invalid("missing_target")
    obj = ctx.content.index.objects.get(object_id)
    state = ctx.doc.objects.get(object_id)
    if obj is None or state is None or not state.known:
        raise not_found("unknown_target", target=object_id)
    return obj


def _object_location(ctx: Ctx, obj: WorldObject) -> str:
    return obj.location


def _at(ctx: Ctx, obj: WorldObject) -> None:
    if ctx.doc.player_location != _object_location(ctx, obj):
        raise unavailable(
            "not_at_location",
            target=obj.id,
            required_location=obj.location,
            player_location=ctx.doc.player_location,
        )


def _reachable_container(ctx: Ctx, cid: str) -> None:
    containers.require_container(ctx.content, ctx.doc, cid)
    obj = ctx.content.index.objects[cid]
    if not ctx.doc.objects[cid].known:
        raise not_found("unknown_container", container=cid)
    if cid == _player_kit(ctx):
        return
    _at(ctx, obj)
    if obj.parent is not None and ctx.doc.objects[obj.parent].access in {"locked", "restricted"}:
        raise unavailable(
            "host_not_accessible", target=obj.parent, access=ctx.doc.objects[obj.parent].access
        )


def _player_kit(ctx: Ctx) -> str | None:
    return ctx.content.index.missions[ctx.doc.mission_id].player_kit


def _engine_decisions(raw: list[dict[str, Any]]) -> list[DecisionInput]:
    return [parse_decision(r) for r in raw]


# ------------------------------------------------------------------ entry point
def plan(ctx: Ctx, cmd: Command) -> Plan:
    spec = ACTIONS.get(cmd.action)
    if spec is None:
        raise invalid("unknown_action", action=cmd.action)
    if cmd.actor != COMMANDER:
        raise GameRuleError("actor_not_controllable", kind="invalid", details={"actor": cmd.actor})
    if ctx.doc.status != "active":
        raise GameRuleError(
            "mission_not_active", kind="complete", details={"status": ctx.doc.status}
        )
    handler = _HANDLERS[spec.handler]
    return handler(ctx, cmd)


# ------------------------------------------------------------------ handlers
def _zone(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, set())
    loc = cmd.target
    if loc is None or loc not in ctx.doc.locations:
        raise not_found("unknown_location", location=loc)
    if ctx.doc.locations[loc] != "open":
        raise unavailable("location_locked", location=loc)

    def finalize(c: Ctx) -> Outcome:
        out = Outcome()
        moved = c.doc.player_location != loc
        c.doc.player_location = loc
        if loc not in c.doc.visited:
            c.doc.visited.append(loc)
        mission = c.content.index.missions[c.doc.mission_id]
        if mission.clock.start_on_zone_entered and not c.doc.clock.started:
            out.start_clock = True
        elif not moved:
            out.result, out.reason = "no_change", "already_here"
        return out

    return Plan(cmd.action, loc, [], finalize)


def _interaction_for(obj: WorldObject, action: str) -> Interaction:
    for inter in obj.interactions:
        if inter.action == action:
            return inter
    raise invalid("action_not_supported", action=action, target=obj.id)


def _interaction(ctx: Ctx, cmd: Command) -> Plan:
    obj = _known_object(ctx, cmd.target)
    inter = _interaction_for(obj, cmd.action)
    if ctx.doc.objects[obj.id].access == "locked":
        raise unavailable("target_locked", target=obj.id)
    _only_params(cmd, set(inter.params))
    params: dict[str, str] = {}
    for name, ps in inter.params.items():
        value = _str_param(cmd, name)
        assert value is not None
        if value not in ps.enum:
            raise invalid("invalid_parameter", parameter=name, allowed=list(ps.enum))
        params[name] = value
    if inter.requires_location:
        _at(ctx, obj)
    once_key = f"{obj.id}:{inter.action}"
    if inter.once and once_key in ctx.doc.once_done:
        return Plan(
            cmd.action, obj.id, [], lambda c: Outcome("no_change", "already_done"), mutates=False
        )
    check_requirements(ctx, inter)
    source = inter.consumes_from or _player_kit(ctx)
    for iq in inter.consumes:
        if source is None:
            raise unavailable("required_item_missing", item=iq.item)
        containers.check_remove(ctx.doc, source, iq.item, iq.quantity)
    decisions = _engine_decisions(rendered_decisions(inter, params))

    def finalize(c: Ctx) -> Outcome:
        for iq in inter.consumes:
            assert source is not None
            containers.remove_items(c.doc, source, iq.item, iq.quantity)
        kit = _player_kit(c)
        for eff in param_effects(inter, params):
            apply_effects(c.content, c.doc, c.meta, eff, tick=c.sim.tick, default_container=kit)
        for ce in inter.conditional_effects:
            if holds(ce.when, c):
                apply_effects(
                    c.content, c.doc, c.meta, ce.effects, tick=c.sim.tick, default_container=kit
                )
        if inter.action in {"system.inspect", "vehicle.inspect"}:
            c.doc.objects[obj.id].inspected = True
            c.doc.set_flag(f"inspected:{obj.id}")
        if inter.once:
            c.doc.once_done.append(once_key)
        return Outcome()

    return Plan(cmd.action, obj.id, decisions, finalize)


def check_requirements(ctx: Ctx, inter: Interaction) -> None:
    for req in inter.requirements:
        if not holds(req.when, ctx):
            raise unavailable(req.reason, requirement=req.id)


def _transfer(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, {"item", "quantity", "from"})
    dst = cmd.target
    src = _str_param(cmd, "from")
    item = _str_param(cmd, "item")
    qty = _int_param(cmd, "quantity")
    assert src is not None
    assert item is not None
    if dst is None:
        raise invalid("missing_target")
    if item not in ctx.content.index.items:
        raise not_found("unknown_item", item=item)
    _reachable_container(ctx, src)
    _reachable_container(ctx, dst)

    def finalize(c: Ctx) -> Outcome:
        containers.transfer(c.content, c.doc, src, dst, item, qty)
        return Outcome()

    # validate now (raises the precise reason) on a copy
    probe = ctx.doc.model_copy(deep=True)
    containers.transfer(ctx.content, probe, src, dst, item, qty)
    return Plan(cmd.action, dst, [], finalize)


def _install(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, {"slot", "item", "from"})
    host = _known_object(ctx, cmd.target)
    slot = _str_param(cmd, "slot")
    item = _str_param(cmd, "item")
    src = _str_param(cmd, "from")
    assert slot is not None
    assert item is not None
    assert src is not None
    _at(ctx, host)
    _reachable_container(ctx, src)

    def finalize(c: Ctx) -> Outcome:
        modules.install(c.content, c.meta, c.doc, host.id, slot, item, src)
        return Outcome()

    modules.install(ctx.content, ctx.meta, ctx.doc.model_copy(deep=True), host.id, slot, item, src)
    return Plan(cmd.action, host.id, [], finalize)


def _uninstall(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, {"slot", "to"})
    host = _known_object(ctx, cmd.target)
    slot = _str_param(cmd, "slot")
    dst = _str_param(cmd, "to")
    assert slot is not None
    assert dst is not None
    _at(ctx, host)
    _reachable_container(ctx, dst)

    def finalize(c: Ctx) -> Outcome:
        modules.remove(c.content, c.doc, host.id, slot, dst)
        return Outcome()

    modules.remove(ctx.content, ctx.doc.model_copy(deep=True), host.id, slot, dst)
    return Plan(cmd.action, host.id, [], finalize)


def _crew_location(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, set())
    loc_id = cmd.target
    if loc_id is None or loc_id not in ctx.doc.locations:
        raise not_found("unknown_location", location=loc_id)
    if ctx.doc.locations[loc_id] != "open":
        raise unavailable("location_locked", location=loc_id)
    loc = ctx.content.index.locations[loc_id]
    decisions: list[DecisionInput] = []
    if loc.crew_sim_location is not None:
        decisions = _engine_decisions(
            [{"type": "set_crew_location", "location": loc.crew_sim_location}]
        )

    def finalize(c: Ctx) -> Outcome:
        changed = False
        for crew in c.doc.crew.values():
            if crew.location != loc_id:
                crew.location = loc_id
                changed = True
        return Outcome() if changed or decisions else Outcome("no_change", "already_there")

    return Plan(cmd.action, loc_id, decisions, finalize)


def _context(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, set())
    crew_id = cmd.target
    if crew_id is None or crew_id not in ctx.content.index.crew:
        raise not_found("unknown_crew", crew=crew_id)
    member = ctx.content.index.crew[crew_id]
    eligible = [
        c for c in ctx.content.content.narrative.cues if c.speaker == crew_id and holds(c.when, ctx)
    ]
    best = min(eligible, key=lambda c: (-c.priority, c.id)) if eligible else None
    state = ctx.doc.crew.get(crew_id)
    incidents = sorted(
        i.id
        for i in ctx.doc.incidents.values()
        if i.resolved_tick is None and crew_id in ctx.content.index.incidents[i.id].involved_crew
    )
    payload = {
        "crew": crew_id,
        "role": member.role,
        "intent": state.intent if state else None,
        "involved_incidents": incidents,
        "cue": None
        if best is None
        else {
            "cue": best.id,
            "speaker": best.speaker,
            "priority": best.priority,
            "line": best.line,
            "message_key": best.message_key,
        },
    }
    return Plan(
        cmd.action, crew_id, [], lambda c: Outcome("no_change", context=payload), mutates=False
    )


def gate_status(ctx: Ctx) -> list[tuple[str, bool, str]]:
    mission = ctx.content.index.missions[ctx.doc.mission_id]
    gate = mission.completion.gate
    if gate is None:
        return []
    return [(r.id, holds(r.when, ctx), r.reason) for r in gate.requirements]


def _authorize(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, set())
    mission = ctx.content.index.missions[ctx.doc.mission_id]
    gate = mission.completion.gate
    if gate is None:
        raise invalid("mission_has_no_authorization", mission=mission.id)
    if cmd.target != gate.target:
        raise invalid("not_the_authorization_target", target=cmd.target)
    obj = _known_object(ctx, cmd.target)
    _at(ctx, obj)
    if gate.id in ctx.doc.authorized:
        return Plan(
            cmd.action,
            obj.id,
            [],
            lambda c: Outcome("no_change", "already_authorized"),
            mutates=False,
        )
    unmet = [(rid, reason) for rid, ok, reason in gate_status(ctx) if not ok]
    if unmet:
        raise unavailable(
            unmet[0][1], gate=gate.id, unmet=[{"requirement": r, "reason": x} for r, x in unmet]
        )

    def finalize(c: Ctx) -> Outcome:
        c.doc.authorized.append(gate.id)
        c.doc.set_flag(f"authorized:{gate.id}")
        return Outcome(complete_mission=True)

    return Plan(cmd.action, obj.id, [], finalize)


def _clock(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, {"mode"})
    mode = _str_param(cmd, "mode")
    if mode not in CLOCK_MODES:
        raise invalid("invalid_parameter", parameter="mode", allowed=list(CLOCK_MODES))
    if not ctx.doc.clock.started and mode != "PAUSED":
        raise unavailable("clock_not_started")
    if ctx.sim.concluded:
        raise GameRuleError("mission_concluded", kind="complete")

    def finalize(c: Ctx) -> Outcome:
        if c.doc.clock.mode == mode:
            return Outcome("no_change", "clock_unchanged")
        return Outcome(clock_mode=mode)

    return Plan(cmd.action, None, [], finalize)


def _checkpoint(ctx: Ctx, cmd: Command) -> Plan:
    _only_params(cmd, {"label"})
    label = _str_param(cmd, "label", required=False) or "manual"
    return Plan(cmd.action, None, [], lambda c: Outcome(checkpoint_label=label))


_HANDLERS: dict[str, Callable[[Ctx, Command], Plan]] = {
    "zone": _zone,
    "interaction": _interaction,
    "transfer": _transfer,
    "install": _install,
    "uninstall": _uninstall,
    "crew_location": _crew_location,
    "context": _context,
    "authorize": _authorize,
    "clock": _clock,
    "checkpoint": _checkpoint,
}
