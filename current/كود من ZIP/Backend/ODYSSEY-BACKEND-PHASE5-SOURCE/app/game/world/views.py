"""Builders of the client-safe views (world, mission, campaign) from authoritative state."""

from __future__ import annotations

from app.game.actions.planner import gate_status
from app.game.campaign.campaign import missing_prerequisites
from app.game.content.loader import LoadedContent
from app.game.content.schema import Interaction, Provenance, WorldObject
from app.game.contracts.views import (
    AlertBrief,
    AuthorizationView,
    CampaignView,
    CapabilityBrief,
    ClockView,
    ContainerView,
    CrewView,
    CueView,
    DiscoveryView,
    IncidentView,
    InfrastructureRecordView,
    InsightView,
    InteractionView,
    ItemStackView,
    LocationView,
    MissionProgressView,
    MissionView,
    ModuleSlotView,
    ObjectiveBrief,
    ObjectView,
    PhaseView,
    ProvenanceView,
    RequirementView,
    ResourceBrief,
    WorldView,
)
from app.game.inventory.containers import contents_mass, contents_volume
from app.game.runtime import clock as clockmod
from app.game.world.conditions import Ctx, holds
from app.game.world.state import CampaignMeta, CueFire
from app.read_models.common import rnd
from app.read_models.mission import build_alerts
from app.read_models.resources import build_resources

_HEALTH_DEGRADED = 0.8
_HEALTH_DAMAGED = 0.3


def provenance_view(p: Provenance) -> ProvenanceView:
    return ProvenanceView(
        classification=p.classification, evidence_refs=list(p.evidence_refs), note=p.note
    )


def interaction_availability(
    ctx: Ctx, obj: WorldObject, inter: Interaction
) -> tuple[bool, str | None]:
    doc = ctx.doc
    if doc.status != "active":
        return False, "mission_not_active"
    if doc.objects[obj.id].access == "locked":
        return False, "target_locked"
    if inter.requires_location and doc.player_location != obj.location:
        return False, "not_at_location"
    if inter.once and f"{obj.id}:{inter.action}" in doc.once_done:
        return False, "already_done"
    for req in inter.requirements:
        if not holds(req.when, ctx):
            return False, req.reason
    source = inter.consumes_from or ctx.content.index.missions[doc.mission_id].player_kit
    for iq in inter.consumes:
        if source is None or doc.containers.get(source, {}).get(iq.item, 0) < iq.quantity:
            return False, "insufficient_quantity"
    if (inter.engine or inter.engine_by_param) and ctx.sim.concluded:
        return False, "mission_concluded"
    return True, None


def _status(ctx: Ctx, obj: WorldObject) -> tuple[str, str | None, str | None]:
    """(status, power, mode) derived from the simulation binding."""
    b, sim = obj.binding, ctx.sim
    status, power, mode = "nominal", None, None
    if b.component is not None and sim.has_metric(f"component.{b.component}.health"):
        health = sim.metric(f"component.{b.component}.health")
        if sim.metric(f"component.{b.component}.in_maintenance") >= 0.5:
            status = "maintenance"
        elif health < _HEALTH_DAMAGED:
            status = "damaged"
        elif health < _HEALTH_DEGRADED:
            status = "degraded"
        else:
            status = "operational"
    if b.consumer is not None and b.consumer in sim.state.power.consumers:
        cs = sim.state.power.consumers[b.consumer]
        mode = cs.mode.value
        if mode == "off":
            power = "off"
        elif cs.supply_ratio >= 0.99:
            power = "powered"
        elif cs.supply_ratio > 0.0:
            power = "partial"
        else:
            power = "unpowered"
        if status == "nominal":
            status = "operational" if power in {"powered", "partial"} else "offline"
    if not ctx.doc.objects[obj.id].operational:
        status = "offline"
    return status, power, mode


def _infrastructure_state(ctx: Ctx, obj: WorldObject, status: str, power: str | None) -> str | None:
    if obj.infrastructure_type is None:
        return None
    it = ctx.content.index.infrastructure_types[obj.infrastructure_type]
    installed = {
        ctx.content.index.items[m.item].module.category  # type: ignore[union-attr]
        for m in ctx.doc.modules.get(obj.id, {}).values()
    }
    present = [cat for cat in it.requires_modules if cat in installed]
    if len(present) < len(it.requires_modules):
        # nothing of the required hardware installed yet: planned; some of it: being built
        return "under_construction" if present else "planned"
    if status == "maintenance" or (it.depends_on_power and power in {"off", "unpowered"}):
        return "offline"
    if status == "damaged":
        return "damaged"
    if status == "degraded" or power == "partial":
        return "degraded"
    if status == "offline":
        return "offline"
    return "operational"


def infrastructure_state(ctx: Ctx, obj: WorldObject) -> str | None:
    """The semantic infrastructure state of ``obj`` (None if it is not infrastructure)."""
    status, power, _ = _status(ctx, obj)
    return _infrastructure_state(ctx, obj, status, power)


def object_view(ctx: Ctx, obj: WorldObject) -> ObjectView:
    state = ctx.doc.objects[obj.id]
    status, power, mode = _status(ctx, obj)
    infra = _infrastructure_state(ctx, obj, status, power)
    charge = None
    if obj.binding.rover and obj.kind == "vehicle" and ctx.sim.has_metric("rover.battery_kwh"):
        charge = rnd(ctx.sim.metric("rover.battery_kwh"), 1)
    interactions = []
    for inter in obj.interactions:
        ok, reason = interaction_availability(ctx, obj, inter)
        interactions.append(
            InteractionView(
                action=inter.action,
                params={k: list(v.enum) for k, v in inter.params.items()},
                available=ok,
                reason=reason,
            )
        )
    host_ok = infra is None or infra in {"operational", "degraded"}
    mods = [
        ModuleSlotView(
            slot=slot,
            item=m.item,
            state=("operational" if obj.infrastructure_type and host_ok else m.state),
        )
        for slot, m in sorted(ctx.doc.modules.get(obj.id, {}).items())
    ]
    return ObjectView(
        id=obj.id,
        kind=obj.kind,
        name=obj.name,
        location=obj.location,
        parent=obj.parent,
        tags=list(obj.tags),
        critical=obj.critical,
        access=state.access,
        inspected=state.inspected,
        status=status,
        power=power,
        mode=mode,
        charge_kwh=charge,
        vehicle_class=obj.vehicle_class,
        infrastructure_type=obj.infrastructure_type,
        infrastructure_state=infra,
        modules=mods,
        interactions=interactions,
    )


def container_view(content: LoadedContent, ctx: Ctx, cid: str) -> ContainerView:
    obj = content.index.objects[cid]
    spec = obj.container
    assert spec is not None
    contents = ctx.doc.containers[cid]
    vehicle = None
    if obj.parent is not None and content.index.objects[obj.parent].vehicle_class:
        vehicle = obj.parent
    kit = content.index.missions[ctx.doc.mission_id].player_kit
    role = "inventory" if cid == kit else ("cargo" if vehicle else "storage")
    items = content.index.items
    return ContainerView(
        id=cid,
        name=obj.name,
        location=obj.location,
        role=role,
        vehicle=vehicle,
        mass_kg=rnd(contents_mass(content, contents), 2),
        mass_limit_kg=spec.mass_limit_kg,
        volume_l=rnd(contents_volume(content, contents), 1),
        volume_limit_l=spec.volume_limit_l,
        items=[
            ItemStackView(item=i, quantity=q, mass_kg=rnd(items[i].mass_kg * q, 2))
            for i, q in sorted(contents.items())
        ],
    )


def _health_band(ctx: Ctx, crew_id: str) -> str | None:
    member = ctx.content.index.crew[crew_id]
    sim_id = member.sim_crew.get(ctx.sim.scenario_id)
    for c in ctx.sim.state.crew:
        if c.id == sim_id:
            return "nominal" if c.health >= 0.7 else ("degraded" if c.health >= 0.4 else "critical")
    return None


def world_view(ctx: Ctx) -> WorldView:
    content, doc = ctx.content, ctx.doc
    world = content.index.worlds[doc.world_id]
    visible_objects = [o for o in world.objects if doc.objects[o.id].known]
    incidents = []
    for inc_state in sorted(doc.incidents.values(), key=lambda i: (i.started_tick, i.id)):
        spec = content.index.incidents[inc_state.id]
        incidents.append(
            IncidentView(
                id=spec.id,
                message_key=spec.message_key,
                stage=inc_state.stage,
                started_tick=inc_state.started_tick,
                resolved_tick=inc_state.resolved_tick,
                involved_objects=list(spec.involved_objects),
                involved_crew=list(spec.involved_crew),
                facts=list(inc_state.facts),
            )
        )
    crew = []
    for member in content.content.narrative.crew:
        cs = doc.crew.get(member.id)
        involved = sorted(
            i.id
            for i in doc.incidents.values()
            if i.resolved_tick is None and member.id in content.index.incidents[i.id].involved_crew
        )
        crew.append(
            CrewView(
                id=member.id,
                name=member.name,
                role=member.role,
                specialty=member.specialty,
                intent=cs.intent if cs else None,
                location=cs.location if cs else None,
                involved_incidents=involved,
                health_band=_health_band(ctx, member.id),
            )
        )
    return WorldView(
        id=world.id,
        name=world.name,
        player_location=doc.player_location,
        locations=[
            LocationView(
                id=loc.id,
                name=loc.name,
                region=loc.region,
                kind=loc.kind,
                access=doc.locations[loc.id],
                visited=loc.id in doc.visited,
            )
            for loc in world.locations
        ],
        objects=[object_view(ctx, o) for o in visible_objects],
        containers=[
            container_view(content, ctx, o.id)
            for o in visible_objects
            if o.container is not None and o.id in doc.containers
        ],
        incidents=incidents,
        crew=crew,
        recent_cues=[_cue_view(ctx, c) for c in doc.recent_cues],
    )


def _cue_view(ctx: Ctx, fired: CueFire) -> CueView:
    spec = ctx.content.index.cues[fired.cue]
    again = None if spec.once else fired.tick + max(spec.cooldown_ticks, 1)
    return CueView(
        **fired.model_dump(),
        once=spec.once,
        cooldown_ticks=spec.cooldown_ticks,
        eligible_again_tick=again,
    )


def clock_view(ctx: Ctx) -> ClockView:
    c = ctx.doc.clock
    t = ctx.sim.engine.scenario.time
    return ClockView(
        mode=c.mode,
        started=c.started,
        pause_reason=c.pause_reason,
        sim_tick=ctx.sim.tick,
        max_ticks=t.max_ticks,
        tick_hours=t.tick_hours,
        elapsed_hours=rnd(ctx.sim.tick * t.tick_hours, 2),
        ticks_per_second=clockmod.rate(c),
        seconds_per_tick=clockmod.seconds_per_tick(c),
        max_catchup_ticks=c.max_catchup_ticks,
    )


def mission_view(ctx: Ctx) -> MissionView:
    content, doc, sim = ctx.content, ctx.doc, ctx.sim
    mission = content.index.missions[doc.mission_id]
    auth = None
    gate = mission.completion.gate
    if gate is not None:
        reqs = [RequirementView(id=r, met=ok, reason=reason) for r, ok, reason in gate_status(ctx)]
        auth = AuthorizationView(
            gate=gate.id,
            target=gate.target,
            available=all(r.met for r in reqs) and doc.status == "active",
            authorized=gate.id in doc.authorized,
            requirements=reqs,
        )
    engine, state = sim.engine, sim.state
    objectives = [
        ObjectiveBrief(
            id=o.id,
            category=o.effective_category,
            required=o.required,
            status=state.objectives[o.id].status.value,
            message_key=f"objective.{o.id}",
        )
        for o in engine.scenario.objectives
    ]
    resources = [
        ResourceBrief(
            id=r.id,
            label=r.label,
            value=r.value,
            unit=r.unit,
            state=r.state,
            warning_state=r.warning_state,
        )
        for r in build_resources(engine, state)
    ]
    alerts = [
        AlertBrief(id=a.id, severity=a.severity, category=a.category)
        for a in build_alerts(engine, state)
    ]
    return MissionView(
        id=mission.id,
        phase=mission.phase,
        title=mission.title,
        summary=mission.summary,
        status=doc.status,
        simulation_status=state.status.value,
        completion=mission.completion.type,
        authorization=auth,
        objectives=objectives,
        resources=resources,
        alerts=alerts,
        outcome_tier=sim.outcome_tier(),
    )


def campaign_view(content: LoadedContent, meta: CampaignMeta) -> CampaignView:
    phases = []
    for p in sorted(content.content.campaign.phases, key=lambda x: x.order):
        status = meta.phases[p.id]
        missing = (
            missing_prerequisites(content, meta, p.prerequisites) if status == "locked" else {}
        )
        phases.append(
            PhaseView(
                id=p.id,
                order=p.order,
                title=p.title,
                summary=p.summary,
                status=status,
                authored=p.authored,
                replayable=p.replayable
                or any(content.index.missions[m].replayable for m in p.missions),
                missions=list(p.missions),
                missing=missing,
            )
        )
    return CampaignView(
        id=content.content.campaign.id,
        content_version=meta.content_version,
        active_mission=meta.active_mission,
        phases=phases,
        missions=[
            MissionProgressView(
                id=m.id,
                phase=m.phase,
                status=meta.missions[m.id].status,
                attempts=meta.missions[m.id].attempts,
                best_tier=meta.missions[m.id].best_tier,
                replayable=m.replayable,
            )
            for m in content.content.campaign.missions
        ],
        capabilities=[
            CapabilityBrief(id=c.id, stage=meta.capabilities.get(c.id))
            for c in content.content.progression.capabilities
        ],
        certifications=list(meta.certifications),
        discoveries=list(meta.discoveries),
        insights=list(meta.insights),
        infrastructure=[
            InfrastructureRecordView(
                object=oid,
                type=r.type,
                world=r.world,
                state=r.state,
                modules=dict(r.modules),
                mission_id=r.mission_id,
            )
            for oid, r in sorted(meta.infrastructure.items())
        ],
    )


def discovery_views(ctx: Ctx) -> list[DiscoveryView]:
    content, doc, meta = ctx.content, ctx.doc, ctx.meta
    out: list[DiscoveryView] = []
    seen: set[str] = set()
    for rec in doc.discoveries:
        d = content.index.discoveries[rec.id]
        seen.add(rec.id)
        out.append(
            DiscoveryView(
                id=d.id,
                category=d.category,
                title=d.title,
                summary=d.summary,
                location=d.location,
                mission_id=rec.mission_id,
                tick=rec.tick,
                source=rec.source,
                committed=rec.id in meta.discoveries,
                provenance=provenance_view(d.provenance),
                insights=list(d.insights),
                capability_evidence=list(d.capability_evidence),
            )
        )
    for did in meta.discoveries:
        if did in seen:
            continue
        d = content.index.discoveries[did]
        mission = next(
            (
                m.id
                for m in content.content.campaign.missions
                if content.index.location_world.get(d.location) == m.world
            ),
            "",
        )
        out.append(
            DiscoveryView(
                id=d.id,
                category=d.category,
                title=d.title,
                summary=d.summary,
                location=d.location,
                mission_id=mission,
                committed=True,
                provenance=provenance_view(d.provenance),
                insights=list(d.insights),
                capability_evidence=list(d.capability_evidence),
            )
        )
    return out


def insight_views(content: LoadedContent, ids: list[str], ctx: Ctx | None) -> list[InsightView]:
    out = []
    for iid in ids:
        ins = content.index.insights[iid]
        why = ins.why_metric is not None and ctx is not None and ctx.sim.has_metric(ins.why_metric)
        out.append(
            InsightView(
                id=ins.id,
                concept=ins.concept,
                title=ins.title,
                observation=ins.observation,
                explanation=ins.explanation,
                matters_later=ins.matters_later,
                simplification=ins.simplification,
                provenance=provenance_view(ins.provenance),
                related_objects=list(ins.related_objects),
                why_available=why,
            )
        )
    return out
