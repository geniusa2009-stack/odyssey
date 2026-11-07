"""Deterministic game events derived from client-safe views (before → after).

Events are computed by diffing the same views the client receives, so an event can never carry
information the snapshot would not show (no hidden-event leak by construction), and the order is
deterministic: categories in a fixed order, ids sorted within a category.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.game.contracts.views import (
    CampaignView,
    ClockView,
    DiscoveryView,
    InsightView,
    MissionView,
    WorldView,
)


@dataclass(frozen=True, slots=True)
class PublicState:
    world: WorldView
    mission: MissionView
    clock: ClockView
    campaign: CampaignView
    discoveries: tuple[DiscoveryView, ...]
    insights: tuple[InsightView, ...]


@dataclass(frozen=True, slots=True)
class DerivedEvent:
    type: str
    scope: str
    payload: dict[str, Any]


_OBJECT_FIELDS = ("access", "inspected", "status", "power", "mode", "infrastructure_state")


def _objects(before: WorldView, after: WorldView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    old = {o.id: o for o in before.objects}
    availability: list[str] = []
    for obj in sorted(after.objects, key=lambda o: o.id):
        prev = old.get(obj.id)
        if prev is None:
            out.append(DerivedEvent("world.object_revealed", "world", {"object": obj.id}))
            continue
        changes = {
            f: getattr(obj, f) for f in _OBJECT_FIELDS if getattr(obj, f) != getattr(prev, f)
        }
        if prev.modules != obj.modules:
            changes["modules"] = [m.model_dump() for m in obj.modules]
        if "access" in changes:
            out.append(
                DerivedEvent(
                    "world.access_changed", "world", {"object": obj.id, "access": obj.access}
                )
            )
        if changes:
            etype = "infrastructure.changed" if obj.infrastructure_type else "system.state_changed"
            out.append(DerivedEvent(etype, "world", {"object": obj.id, "changes": changes}))
        if [(i.action, i.available, i.reason) for i in prev.interactions] != [
            (i.action, i.available, i.reason) for i in obj.interactions
        ]:
            availability.append(obj.id)
    if availability:
        out.append(DerivedEvent("interactions.changed", "world", {"objects": availability}))
    return out


def _containers(before: WorldView, after: WorldView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    old = {c.id: c for c in before.containers}
    for c in sorted(after.containers, key=lambda x: x.id):
        prev = old.get(c.id)
        if prev is not None and prev.items == c.items:
            continue
        etype = "cargo.changed" if c.role == "cargo" else "inventory.changed"
        out.append(
            DerivedEvent(
                etype,
                "world",
                {
                    "container": c.id,
                    "items": [i.model_dump() for i in c.items],
                    "mass_kg": c.mass_kg,
                    "mass_limit_kg": c.mass_limit_kg,
                },
            )
        )
    return out


def _locations(before: WorldView, after: WorldView) -> list[DerivedEvent]:
    old = {loc.id: loc.access for loc in before.locations}
    return [
        DerivedEvent("world.access_changed", "world", {"location": loc.id, "access": loc.access})
        for loc in sorted(after.locations, key=lambda x: x.id)
        if old.get(loc.id) not in (None, loc.access)
    ]


def _incidents(before: WorldView, after: WorldView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    old = {i.id: i for i in before.incidents}
    for inc in after.incidents:
        prev = old.get(inc.id)
        body = {
            "incident": inc.id,
            "stage": inc.stage,
            "message_key": inc.message_key,
            "involved_objects": inc.involved_objects,
            "involved_crew": inc.involved_crew,
        }
        if prev is None:
            out.append(DerivedEvent("incident.started", "mission", body))
            if inc.resolved_tick is not None:
                out.append(DerivedEvent("incident.resolved", "mission", body))
            continue
        if prev.resolved_tick is None and inc.resolved_tick is not None:
            out.append(DerivedEvent("incident.resolved", "mission", body))
        elif prev.stage != inc.stage or prev.facts != inc.facts:
            out.append(DerivedEvent("incident.updated", "mission", {**body, "facts": inc.facts}))
    return out


def _crew(before: WorldView, after: WorldView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    old = {c.id: c for c in before.crew}
    for c in after.crew:
        prev = old.get(c.id)
        if prev is not None and (
            prev.intent,
            prev.location,
            prev.involved_incidents,
            prev.health_band,
        ) == (c.intent, c.location, c.involved_incidents, c.health_band):
            continue
        out.append(DerivedEvent("crew.updated", "crew", c.model_dump()))
    seen = {(c.cue, c.tick) for c in before.recent_cues}
    for cue in after.recent_cues:
        if (cue.cue, cue.tick) not in seen:
            out.append(DerivedEvent("crew.cue", "crew", cue.model_dump()))
    return out


def _mission(before: MissionView, after: MissionView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    old = {o.id: o.status for o in before.objectives}
    for o in after.objectives:
        if old.get(o.id) != o.status:
            out.append(
                DerivedEvent(
                    "objective.updated",
                    "mission",
                    {"objective": o.id, "status": o.status, "category": o.category},
                )
            )
    prev_alerts = {a.id: a for a in before.alerts}
    cur_alerts = {a.id: a for a in after.alerts}
    for aid in sorted(set(prev_alerts) | set(cur_alerts)):
        if (aid in prev_alerts) == (aid in cur_alerts):
            continue
        a = cur_alerts.get(aid) or prev_alerts[aid]
        etype = "resource.threshold_changed" if a.category == "resource" else "system.alert_changed"
        out.append(
            DerivedEvent(
                etype,
                "mission",
                {
                    "alert": aid,
                    "severity": a.severity,
                    "category": a.category,
                    "active": aid in cur_alerts,
                },
            )
        )
    if (
        before.status != after.status
        or before.authorization != after.authorization
        or before.simulation_status != after.simulation_status
        or before.outcome_tier != after.outcome_tier
    ):
        out.append(
            DerivedEvent(
                "mission.updated",
                "mission",
                {
                    "mission": after.id,
                    "status": after.status,
                    "simulation_status": after.simulation_status,
                    "outcome_tier": after.outcome_tier,
                    "authorization": after.authorization.model_dump()
                    if after.authorization
                    else None,
                },
            )
        )
    return out


def _clock(before: ClockView, after: ClockView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    if after.sim_tick != before.sim_tick:
        out.append(
            DerivedEvent(
                "time.advanced",
                "mission",
                {
                    "from_tick": before.sim_tick,
                    "to_tick": after.sim_tick,
                    "elapsed_hours": after.elapsed_hours,
                },
            )
        )
    if (before.mode, before.pause_reason, before.started) != (
        after.mode,
        after.pause_reason,
        after.started,
    ):
        out.append(
            DerivedEvent(
                "clock.updated",
                "mission",
                {
                    "mode": after.mode,
                    "pause_reason": after.pause_reason,
                    "ticks_per_second": after.ticks_per_second,
                    "sim_tick": after.sim_tick,
                },
            )
        )
    return out


def campaign_events(before: CampaignView, after: CampaignView) -> list[DerivedEvent]:
    out: list[DerivedEvent] = []
    old_caps = {c.id: c.stage for c in before.capabilities}
    for c in after.capabilities:
        if old_caps.get(c.id) != c.stage and c.stage is not None:
            out.append(
                DerivedEvent(
                    "capability.progressed",
                    "campaign",
                    {"capability": c.id, "stage": c.stage, "previous_stage": old_caps.get(c.id)},
                )
            )
    for cert in after.certifications:
        if cert not in before.certifications:
            out.append(DerivedEvent("certification.granted", "campaign", {"certification": cert}))
    old_infra = {r.object: r for r in before.infrastructure}
    for r in after.infrastructure:
        if old_infra.get(r.object) != r:
            out.append(
                DerivedEvent(
                    "infrastructure.changed",
                    "campaign",
                    {"object": r.object, "state": r.state, "persistent": True},
                )
            )
    old_phases = {p.id: p.status for p in before.phases}
    changed = {p.id: p.status for p in after.phases if old_phases.get(p.id) != p.status}
    old_missions = {m.id: m.status for m in before.missions}
    changed_m = {m.id: m.status for m in after.missions if old_missions.get(m.id) != m.status}
    if changed or changed_m or before.active_mission != after.active_mission:
        out.append(
            DerivedEvent(
                "campaign.updated",
                "campaign",
                {"phases": changed, "missions": changed_m, "active_mission": after.active_mission},
            )
        )
    return out


def derive(before: PublicState, after: PublicState) -> list[DerivedEvent]:
    """Events for one transition on the same timeline/world."""
    out: list[DerivedEvent] = []
    out += _clock(before.clock, after.clock)
    out += _incidents(before.world, after.world)
    out += _objects(before.world, after.world)
    out += _locations(before.world, after.world)
    out += _containers(before.world, after.world)
    out += _mission(before.mission, after.mission)
    known = {d.id for d in before.discoveries}
    for d in after.discoveries:
        if d.id not in known:
            out.append(
                DerivedEvent(
                    "discovery.recorded",
                    "world",
                    {
                        "discovery": d.id,
                        "category": d.category,
                        "title": d.title,
                        "location": d.location,
                        "provenance": d.provenance.classification,
                    },
                )
            )
    unlocked = {i.id for i in before.insights}
    for i in after.insights:
        if i.id not in unlocked:
            out.append(
                DerivedEvent(
                    "knowledge.unlocked",
                    "campaign",
                    {
                        "insight": i.id,
                        "title": i.title,
                        "concept": i.concept,
                        "why_available": i.why_available,
                    },
                )
            )
    out += _crew(before.world, after.world)
    out += campaign_events(before.campaign, after.campaign)
    return out
