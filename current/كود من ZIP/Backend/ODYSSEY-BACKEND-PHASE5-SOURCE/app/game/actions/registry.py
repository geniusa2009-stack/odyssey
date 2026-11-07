"""The authoritative semantic action registry.

Every action the backend understands, what it targets, its parameters and which handler decides
it. Movement, camera, animation, physics and presentation are deliberately absent (Unreal).
Content-defined actions (``handler="interaction"``) take their parameters from the target
object's interaction definition; the registry lists the common shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.game.content.vocabulary import ACTION_TYPES, INTERACTION_ACTIONS

TargetKind = Literal["location", "object", "container", "host", "crew", "gate", "none"]
Handler = Literal[
    "zone",
    "interaction",
    "transfer",
    "install",
    "uninstall",
    "crew_location",
    "context",
    "authorize",
    "clock",
    "checkpoint",
]


@dataclass(frozen=True, slots=True)
class ParamDoc:
    name: str
    kind: Literal["id", "enum", "int", "str"]
    required: bool = True
    description: str = ""
    values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionSpec:
    type: str
    handler: Handler
    target: TargetKind
    summary: str
    mutates: bool = True
    params: tuple[ParamDoc, ...] = field(default_factory=tuple)


_I: Handler = "interaction"
ACTIONS: dict[str, ActionSpec] = {
    s.type: s
    for s in (
        ActionSpec(
            "world.zone_entered",
            "zone",
            "location",
            "The player entered a semantic location (starts the mission clock once).",
        ),
        ActionSpec("world.poi_discovered", _I, "object", "The player found a point of interest."),
        ActionSpec("system.inspect", _I, "object", "Inspect a system or subsystem."),
        ActionSpec(
            "system.set_mode",
            _I,
            "object",
            "Change a system's operating mode.",
            params=(ParamDoc("mode", "enum", description="per target; see interactions"),),
        ),
        ActionSpec(
            "power.reroute",
            _I,
            "object",
            "Reroute power between buses or storage.",
            params=(ParamDoc("direction", "enum"),),
        ),
        ActionSpec("repair.perform", _I, "object", "Repair a diagnosed fault."),
        ActionSpec(
            "science.instrument_operate",
            _I,
            "object",
            "Start or stop an instrument.",
            params=(ParamDoc("operation", "enum"),),
        ),
        ActionSpec("science.sample_collect", _I, "object", "Collect a sample at a site."),
        ActionSpec("infrastructure.activate", _I, "object", "Bring infrastructure online."),
        ActionSpec("infrastructure.deactivate", _I, "object", "Take infrastructure offline."),
        ActionSpec("vehicle.inspect", _I, "object", "Inspect a vehicle."),
        ActionSpec(
            "vehicle.dispatch",
            _I,
            "object",
            "Give a vehicle an order.",
            params=(ParamDoc("order", "enum"),),
        ),
        ActionSpec(
            "cargo.transfer",
            "transfer",
            "container",
            "Move cargo into a container (target = destination).",
            params=(ParamDoc("item", "id"), ParamDoc("quantity", "int"), ParamDoc("from", "id")),
        ),
        ActionSpec(
            "inventory.move",
            "transfer",
            "container",
            "Move items between containers (target = destination).",
            params=(ParamDoc("item", "id"), ParamDoc("quantity", "int"), ParamDoc("from", "id")),
        ),
        ActionSpec(
            "module.install",
            "install",
            "host",
            "Install a hardware module in a slot.",
            params=(ParamDoc("slot", "id"), ParamDoc("item", "id"), ParamDoc("from", "id")),
        ),
        ActionSpec(
            "module.remove",
            "uninstall",
            "host",
            "Remove a module into a container.",
            params=(ParamDoc("slot", "id"), ParamDoc("to", "id")),
        ),
        ActionSpec(
            "crew.assign_location",
            "crew_location",
            "location",
            "Send the crew to a location (e.g. the radiation shelter).",
        ),
        ActionSpec(
            "npc.context_request",
            "context",
            "crew",
            "Ask a crew member for context (read-only).",
            mutates=False,
        ),
        ActionSpec(
            "mission.authorize",
            "authorize",
            "object",
            "Authorize the mission at its gate (target = gate object).",
        ),
        ActionSpec(
            "mission.clock_set",
            "clock",
            "none",
            "Pause, resume or accelerate time.",
            params=(ParamDoc("mode", "enum", values=("PAUSED", "REALTIME", "ACCELERATED")),),
        ),
        ActionSpec(
            "checkpoint.save",
            "checkpoint",
            "none",
            "Save a manual checkpoint.",
            params=(ParamDoc("label", "str", required=False),),
        ),
    )
}

assert set(ACTIONS) == set(ACTION_TYPES), "registry and vocabulary disagree"
assert {a for a, s in ACTIONS.items() if s.handler == "interaction"} == set(INTERACTION_ACTIONS)
