"""Read views over campaign meta, the timeline document and the simulation (pure builders)."""

from __future__ import annotations

from app.game.content.loader import LoadedContent
from app.game.contracts.progression import (
    CapabilitiesView,
    CapabilityView,
    CatalogItemView,
    CatalogView,
    CertificationView,
    EvidenceStatus,
    ExpansionMapView,
    GateView,
    MapEdge,
    MapNode,
    MissingCapabilityView,
    ReadinessView,
    SlotStatus,
    StageStatus,
    VehicleView,
    WhyInput,
    WhyView,
)
from app.game.inventory.containers import vehicle_payload_mass
from app.game.progression.capabilities import prerequisites_met, readiness
from app.game.world.conditions import Ctx, capability_stage_met
from app.game.world.state import CampaignMeta, TimelineGameState
from app.game.world.views import provenance_view
from app.read_models.common import rnd, rnd_unit


def _req(content: LoadedContent, meta: CampaignMeta, cap: str, stage: str) -> dict[str, str | bool]:
    return {
        "capability": cap,
        "stage": stage,
        "met": capability_stage_met(content, meta, cap, stage),
    }


def capabilities_view(
    content: LoadedContent, meta: CampaignMeta, doc: TimelineGameState | None
) -> CapabilitiesView:
    have = set(meta.evidence)
    pending = set(doc.evidence) if doc is not None else set()
    caps = []
    for cap in content.content.progression.capabilities:
        stage = meta.capabilities.get(cap.id)
        locked = not prerequisites_met(content, meta, cap.prerequisites)
        reached_idx = cap.stages.index(stage) if stage else -1
        stages = []
        for i, s in enumerate(cap.stages):
            evs = cap.evidence.get(s, [])
            stages.append(
                StageStatus(
                    stage=s,
                    reached=i <= reached_idx,
                    attainable=bool(evs),
                    evidence=[
                        EvidenceStatus(
                            id=e,
                            description=next(
                                x.description
                                for x in content.content.progression.evidence
                                if x.id == e
                            ),
                            demonstrated=e in have,
                            pending_in_mission=e in pending and e not in have,
                        )
                        for e in evs
                    ],
                )
            )
        if locked:
            status = "locked"
        elif stage is None:
            status = "not_started"
        elif reached_idx == len(cap.stages) - 1:
            status = "max"
        else:
            status = "qualified"
        caps.append(
            CapabilityView(
                id=cap.id,
                name=cap.name,
                description=cap.description,
                domain=cap.domain,
                stage=stage,
                status=status,
                prerequisites=[
                    _req(content, meta, r.capability, r.stage) for r in cap.prerequisites
                ],
                stages=stages,
                certifications=[
                    c.id
                    for c in content.content.progression.certifications
                    if any(r.capability == cap.id for r in c.requires)
                ],
                provenance=provenance_view(cap.provenance),
                gameplay_effects=list(cap.gameplay_effects),
                unlocks=list(cap.unlocks),
            )
        )
    certs = [
        CertificationView(
            id=c.id,
            name=c.name,
            description=c.description,
            granted=c.id in meta.certifications,
            requires=[_req(content, meta, r.capability, r.stage) for r in c.requires],
            granted_on_completion_of=list(c.granted_on_completion_of),
            provenance=provenance_view(c.provenance),
        )
        for c in content.content.progression.certifications
    ]
    return CapabilitiesView(capabilities=caps, certifications=certs)


def readiness_view(content: LoadedContent, meta: CampaignMeta, profile_id: str) -> ReadinessView:
    status = readiness(content, meta, profile_id)
    profile = content.index.profiles[profile_id]
    return ReadinessView(
        profile=profile.id,
        title=profile.title,
        locked=status.locked,
        lock={
            "code": status.lock_code,
            "missing_gates": list(status.critical_missing),
            "missing_capabilities": status.missing_capability_ids,
        }
        if status.locked
        else None,
        gates_met=status.gates_met,
        gates_total=status.gates_total,
        percent=status.percent,
        critical_missing=list(status.critical_missing),
        gates=[
            GateView(
                id=g.id,
                category=g.category,
                title=g.title,
                critical=g.critical,
                met=g.met,
                missing_capabilities=[
                    MissingCapabilityView(
                        capability=mc.capability,
                        required_stage=mc.required_stage,
                        current_stage=mc.current_stage,
                    )
                    for mc in g.missing_capabilities
                ],
                missing_certifications=list(g.missing_certifications),
            )
            for g in status.gates
        ],
    )


def expansion_map(content: LoadedContent, meta: CampaignMeta) -> ExpansionMapView:
    """Nodes are real missions, phases, capabilities, certifications, readiness gates,
    infrastructure types and discoveries; edges say exactly which prerequisite links them."""
    nodes: list[MapNode] = []
    edges: list[MapEdge] = []
    c = content.content
    for ph in sorted(c.campaign.phases, key=lambda x: x.order):
        nodes.append(
            MapNode(id=f"phase:{ph.id}", type="phase", label=ph.title, state=meta.phases[ph.id])
        )
        for prev in ph.prerequisites.phases_completed:
            edges.append(
                MapEdge(
                    source=f"phase:{prev}",
                    target=f"phase:{ph.id}",
                    kind="requires",
                    explanation=f"{ph.id} requires {prev} completed",
                    satisfied=meta.phases.get(prev) == "completed",
                )
            )
        for r in ph.prerequisites.capabilities:
            edges.append(
                MapEdge(
                    source=f"capability:{r.capability}",
                    target=f"phase:{ph.id}",
                    kind="gates",
                    explanation=f"requires {r.capability} at {r.stage}",
                    satisfied=capability_stage_met(content, meta, r.capability, r.stage),
                )
            )
        if ph.prerequisites.readiness_profile:
            status = readiness(content, meta, ph.prerequisites.readiness_profile)
            for g in status.gates:
                edges.append(
                    MapEdge(
                        source=f"gate:{g.id}",
                        target=f"phase:{ph.id}",
                        kind="gates",
                        explanation=("critical gate " if g.critical else "gate ") + g.title,
                        satisfied=g.met,
                    )
                )
        for mid in ph.missions:
            mp = meta.missions[mid]
            mission = content.index.missions[mid]
            nodes.append(
                MapNode(
                    id=f"mission:{mid}",
                    type="mission",
                    label=mission.title,
                    state=mp.status,
                    related_mission=mid,
                )
            )
            edges.append(
                MapEdge(
                    source=f"phase:{ph.id}",
                    target=f"mission:{mid}",
                    kind="contains",
                    explanation=f"{mission.title} is part of {ph.title}",
                    satisfied=True,
                )
            )
    for cap in c.progression.capabilities:
        stage = meta.capabilities.get(cap.id)
        reached = (cap.stages.index(stage) + 1) if stage else 0
        nodes.append(
            MapNode(
                id=f"capability:{cap.id}",
                type="capability",
                label=cap.name,
                state=stage
                or (
                    "locked"
                    if not prerequisites_met(content, meta, cap.prerequisites)
                    else "not_started"
                ),
                related_capability=cap.id,
                evidence_refs=list(cap.provenance.evidence_refs),
                progress=f"{reached}/{len(cap.stages)} stages",
            )
        )
        for r in cap.prerequisites:
            edges.append(
                MapEdge(
                    source=f"capability:{r.capability}",
                    target=f"capability:{cap.id}",
                    kind="requires",
                    explanation=f"requires {r.capability} at {r.stage}",
                    satisfied=capability_stage_met(content, meta, r.capability, r.stage),
                )
            )
        for mission in c.campaign.missions:
            evs = {e.evidence for e in mission.completion_evidence}
            if any(evs & set(v) for v in cap.evidence.values()):
                edges.append(
                    MapEdge(
                        source=f"mission:{mission.id}",
                        target=f"capability:{cap.id}",
                        kind="qualifies",
                        explanation=f"{mission.title} can demonstrate evidence",
                        satisfied=meta.missions[mission.id].status == "completed",
                    )
                )
    for cert in c.progression.certifications:
        nodes.append(
            MapNode(
                id=f"certification:{cert.id}",
                type="certification",
                label=cert.name,
                state="granted" if cert.id in meta.certifications else "not_granted",
            )
        )
        for r in cert.requires:
            edges.append(
                MapEdge(
                    source=f"capability:{r.capability}",
                    target=f"certification:{cert.id}",
                    kind="certifies",
                    explanation=f"requires {r.capability} at {r.stage}",
                    satisfied=capability_stage_met(content, meta, r.capability, r.stage),
                )
            )
    for profile in c.readiness.profiles:
        status = readiness(content, meta, profile.id)
        for g in status.gates:
            nodes.append(
                MapNode(
                    id=f"gate:{g.id}",
                    type="readiness_gate",
                    label=g.title,
                    state="met" if g.met else ("missing_critical" if g.critical else "missing"),
                )
            )
            spec = next(x for x in profile.gates if x.id == g.id)
            for r in spec.requires:
                edges.append(
                    MapEdge(
                        source=f"capability:{r.capability}",
                        target=f"gate:{g.id}",
                        kind="gates",
                        explanation=f"requires {r.capability} at {r.stage}",
                        satisfied=capability_stage_met(content, meta, r.capability, r.stage),
                    )
                )
    for it in c.catalog.infrastructure_types:
        nodes.append(
            MapNode(
                id=f"infrastructure:{it.id}",
                type="infrastructure",
                label=it.name,
                state="known",
                evidence_refs=list(it.provenance.evidence_refs),
            )
        )
        for r in it.requires_capabilities:
            edges.append(
                MapEdge(
                    source=f"capability:{r.capability}",
                    target=f"infrastructure:{it.id}",
                    kind="requires",
                    explanation=f"requires {r.capability} at {r.stage}",
                    satisfied=capability_stage_met(content, meta, r.capability, r.stage),
                )
            )
    for did in meta.discoveries:
        d = content.index.discoveries[did]
        nodes.append(
            MapNode(
                id=f"discovery:{did}",
                type="discovery",
                label=d.title,
                state="recorded",
                evidence_refs=list(d.provenance.evidence_refs),
            )
        )
    return ExpansionMapView(nodes=nodes, edges=edges)


def why_view(ctx: Ctx, insight_id: str) -> WhyView:
    """WHY?: trace an unlocked insight's metric through the engine's dependency graph using
    current values only (no forecasts, no hidden events)."""
    ins = ctx.content.index.insights[insight_id]
    engine, state = ctx.sim.engine, ctx.sim.state
    base = {
        "insight": ins.id,
        "concept": ins.concept,
        "observation": ins.observation,
        "explanation": ins.explanation,
        "related_objects": list(ins.related_objects),
        "provenance": provenance_view(ins.provenance),
    }
    metric = ins.why_metric
    if metric is None or not engine.metrics.has(metric):
        return WhyView(
            **base,
            metric=metric,
            available=False,
            note="No live trace for this concept in the current mission.",
        )
    spec = engine.metrics.spec(metric)
    inputs = []
    for edge in engine.graph.parents(metric)[:8]:
        if not engine.metrics.has(edge.source):
            continue
        s = engine.metrics.spec(edge.source)
        inputs.append(
            WhyInput(
                metric=edge.source,
                label=s.label,
                unit=s.unit,
                value=rnd_unit(engine.metrics.value(edge.source, state), s.unit),
                mechanism=edge.mechanism,
            )
        )
    watched = {metric, *(i.metric for i in inputs)}
    alerts = sorted(a.id for a in state.alerts.values() if a.metric in watched)
    return WhyView(
        **base,
        metric=metric,
        label=spec.label,
        unit=spec.unit,
        value=rnd_unit(engine.metrics.value(metric, state), spec.unit),
        inputs=inputs,
        active_alerts=alerts,
        available=True,
        note="Current values from the authoritative simulation.",
    )


def vehicle_view(ctx: Ctx, vehicle_id: str) -> VehicleView:
    content, doc, meta = ctx.content, ctx.doc, ctx.meta
    obj = content.index.objects[vehicle_id]
    vc = content.index.vehicle_classes[obj.vehicle_class or ""]
    installed = doc.modules.get(vehicle_id, {})
    slots = [
        SlotStatus(
            slot=s.id,
            mount=s.mount,
            accepts=list(s.accepts),
            required_for_mission=s.required_for_mission,
            payload=s.payload,
            installed=installed[s.id].item if s.id in installed else None,
        )
        for s in vc.slots
    ]
    payload = vehicle_payload_mass(content, doc, vehicle_id)
    blockers = [f"slot_empty:{s.slot}" for s in slots if s.required_for_mission and not s.installed]
    if payload > vc.cargo_mass_limit_kg + 1e-9:
        blockers.append("payload_over_limit")
    quals = [_req(content, meta, r.capability, r.stage) for r in vc.qualification]
    blockers += [f"qualification_missing:{q['capability']}" for q in quals if not q["met"]]
    cargo = sorted(cid for cid in doc.containers if content.index.objects[cid].parent == vehicle_id)
    return VehicleView(
        id=vehicle_id,
        name=obj.name,
        vehicle_class=vc.id,
        class_name=vc.name,
        mission_role=vc.mission_role,
        crew_capacity=vc.crew_capacity,
        environment_rating=list(vc.environment_rating),
        mission_rating=list(vc.mission_rating),
        payload_mass_kg=rnd(payload, 2),
        payload_limit_kg=vc.cargo_mass_limit_kg,
        power_budget_kw=vc.power_budget_kw,
        life_support_crew_days=vc.life_support_crew_days,
        slots=slots,
        cargo=cargo,
        qualification=quals,
        ready=not blockers,
        blockers=blockers,
        provenance=provenance_view(vc.provenance),
    )


def catalog_view(content: LoadedContent) -> CatalogView:
    c = content.content.catalog
    return CatalogView(
        content_version=content.version,
        items=[
            CatalogItemView(
                id=i.id,
                name=i.name,
                category=i.category,
                mass_kg=i.mass_kg,
                volume_l=i.volume_l,
                stackable=i.stackable,
                max_stack=i.max_stack,
                unique=i.unique,
                tags=list(i.tags),
                provenance=provenance_view(i.provenance),
                module=i.module.model_dump(mode="json") if i.module else None,
            )
            for i in c.items
        ],
        vehicle_classes=[v.model_dump(mode="json") for v in c.vehicle_classes],
        infrastructure_types=[t.model_dump(mode="json") for t in c.infrastructure_types],
    )
