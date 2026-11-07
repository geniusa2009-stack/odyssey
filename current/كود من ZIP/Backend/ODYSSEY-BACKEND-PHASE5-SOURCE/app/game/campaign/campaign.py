"""Campaign progression (pure): phase/mission availability, mission start and completion.

Rules:
* Phases follow content order; a phase becomes ``available`` only when its prerequisites
  (completed phases/missions, capabilities at stages, discoveries, certifications, readiness
  profile) are met — no phase can be skipped.
* Unauthored phases can become available but cannot start (``phase_content_not_authored``).
* Mission completion atomically commits the timeline's pending evidence and discoveries,
  re-derives capability stages, grants certifications, applies carry rules and opens the next
  phase. Failure records history and leaves the mission replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.game.actions.errors import GameRuleError, not_found, unavailable
from app.game.content.loader import LoadedContent
from app.game.content.schema import MissionDef, Prerequisites
from app.game.progression.capabilities import (
    CommitResult,
    commit_evidence,
    prerequisites_met,
    readiness,
)
from app.game.world.conditions import Ctx, holds
from app.game.world.state import (
    CampaignMeta,
    ClockState,
    CompletionRecord,
    CrewState,
    InfrastructureRecord,
    InstalledModule,
    MissionProgress,
    ObjectState,
    TimelineGameState,
)


def missing_prerequisites(
    content: LoadedContent, meta: CampaignMeta, p: Prerequisites
) -> dict[str, Any]:
    missing: dict[str, Any] = {}
    phases = [ph for ph in p.phases_completed if meta.phases.get(ph) != "completed"]
    if phases:
        missing["phases"] = phases
    missions = [
        mid
        for mid in p.missions_completed
        if meta.missions.get(mid, MissionProgress()).status != "completed"
    ]
    if missions:
        missing["missions"] = missions
    caps = [
        {"capability": r.capability, "stage": r.stage}
        for r in p.capabilities
        if not prerequisites_met(content, meta, [r])
    ]
    if caps:
        missing["capabilities"] = caps
    discoveries = [d for d in p.discoveries if d not in meta.discoveries]
    if discoveries:
        missing["discoveries"] = discoveries
    certs = [c for c in p.certifications if c not in meta.certifications]
    if certs:
        missing["certifications"] = certs
    if p.readiness_profile is not None:
        status = readiness(content, meta, p.readiness_profile)
        if status.locked:
            missing["readiness"] = {
                "profile": status.profile,
                "lock_code": status.lock_code,
                "missing_gates": list(status.critical_missing),
                "missing_capabilities": status.missing_capability_ids,
            }
    return missing


def refresh(content: LoadedContent, meta: CampaignMeta) -> None:
    """Recompute locked/available for phases and missions not yet active/completed/failed."""
    for phase in sorted(content.content.campaign.phases, key=lambda p: p.order):
        if meta.phases.get(phase.id) in {"active", "completed", "failed"}:
            continue
        ok = not missing_prerequisites(content, meta, phase.prerequisites)
        meta.phases[phase.id] = "available" if ok else "locked"
    for mission in content.content.campaign.missions:
        progress = meta.missions.setdefault(mission.id, MissionProgress())
        if progress.status in {"active", "completed", "failed"}:
            continue
        phase_open = meta.phases.get(mission.phase) in {"available", "active"}
        ok = phase_open and not missing_prerequisites(content, meta, mission.prerequisites)
        progress.status = "available" if ok else "locked"


def new_campaign(content: LoadedContent) -> CampaignMeta:
    meta = CampaignMeta(
        content_version=content.version,
        phases={p.id: "locked" for p in content.content.campaign.phases},
        missions={m.id: MissionProgress() for m in content.content.campaign.missions},
    )
    refresh(content, meta)
    return meta


def first_mission(content: LoadedContent) -> MissionDef:
    phase = min(content.content.campaign.phases, key=lambda p: p.order)
    return content.index.missions[phase.missions[0]]


def check_can_start(content: LoadedContent, meta: CampaignMeta, mission_id: str) -> MissionDef:
    mission = content.index.missions.get(mission_id)
    if mission is None:
        raise not_found("unknown_mission", mission=mission_id)
    phase = content.index.phases[mission.phase]
    if not phase.authored:
        raise unavailable("phase_content_not_authored", phase=phase.id)
    if meta.active_mission is not None:
        raise unavailable("mission_already_active", mission=meta.active_mission)
    progress = meta.missions.get(mission_id, MissionProgress())
    replay = progress.status in {"completed", "failed"} and (
        mission.replayable or progress.status == "failed"
    )
    if progress.status != "available" and not replay:
        missing = missing_prerequisites(content, meta, phase.prerequisites) | (
            missing_prerequisites(content, meta, mission.prerequisites)
        )
        _raise_readiness_lock(missing)
        raise unavailable("mission_not_available", mission=mission_id, missing=missing)
    return mission


def _raise_readiness_lock(missing: dict[str, Any]) -> None:
    """A missing readiness profile is reported with its lock code (``MARS_MISSION_LOCKED``)
    and the exact missing gates and capability ids — never as an aggregate percentage."""
    if "readiness" not in missing:
        return
    r = missing["readiness"]
    raise GameRuleError(
        r["lock_code"].lower(),
        "readiness gates are missing",
        kind="unavailable",
        details={
            "lock_code": r["lock_code"],
            "missing_gates": r["missing_gates"],
            "missing_capabilities": r["missing_capabilities"],
            "missing": {k: v for k, v in missing.items() if k != "readiness"},
        },
    )


def check_can_start_phase(content: LoadedContent, meta: CampaignMeta, phase_id: str) -> MissionDef:
    """Which mission starting ``phase_id`` would begin. Prerequisites are checked before
    content availability, so a locked Mars phase answers ``MARS_MISSION_LOCKED`` (with the
    missing capability ids) rather than "not authored"."""
    phase = content.index.phases.get(phase_id)
    if phase is None:
        raise not_found("unknown_phase", phase=phase_id)
    if meta.phases.get(phase_id) == "locked":
        missing = missing_prerequisites(content, meta, phase.prerequisites)
        _raise_readiness_lock(missing)
        raise unavailable("phase_locked", phase=phase_id, missing=missing)
    if not phase.authored:
        raise unavailable("phase_content_not_authored", phase=phase.id)
    last: GameRuleError | None = None
    for mid in phase.missions:
        try:
            return check_can_start(content, meta, mid)
        except GameRuleError as exc:
            last = exc
    raise last or unavailable("no_available_mission", phase=phase_id)


def initial_document(
    content: LoadedContent, meta: CampaignMeta, mission: MissionDef
) -> TimelineGameState:
    world = content.index.worlds[mission.world]
    containers: dict[str, dict[str, int]] = {}
    modules: dict[str, dict[str, InstalledModule]] = {}
    objects: dict[str, ObjectState] = {}
    for obj in world.objects:
        objects[obj.id] = ObjectState(
            access=obj.initial.access, known=obj.initial.known, operational=obj.initial.operational
        )
        if obj.container is not None:
            contents: dict[str, int] = {}
            for iq in obj.container.initial:
                contents[iq.item] = contents.get(iq.item, 0) + iq.quantity
            for item, qty in meta.carried.get(obj.id, {}).items():
                contents[item] = contents.get(item, 0) + qty
            containers[obj.id] = dict(sorted(contents.items()))
        record = meta.infrastructure.get(obj.id) if mission.inherit_infrastructure else None
        if record is not None and record.world == world.id:
            # persistent infrastructure: start from the state the campaign last left it in
            objects[obj.id].operational = record.state not in {"offline", "damaged"}
            if record.modules:
                modules[obj.id] = {
                    slot: InstalledModule(item=item, state="installed")
                    for slot, item in sorted(record.modules.items())
                }
        elif obj.installed_modules:
            modules[obj.id] = {
                slot: InstalledModule(item=item, state="installed")
                for slot, item in sorted(obj.installed_modules.items())
            }
    clock = mission.clock
    return TimelineGameState(
        mission_id=mission.id,
        world_id=world.id,
        player_location=mission.start_location,
        visited=[mission.start_location],
        locations={loc.id: loc.access for loc in world.locations},
        objects=objects,
        containers=containers,
        modules=modules,
        crew={c.id: CrewState() for c in content.content.narrative.crew},
        clock=ClockState(
            mode="PAUSED",
            realtime_ticks_per_second=clock.realtime_ticks_per_second,
            accelerated_multiplier=clock.accelerated_multiplier,
            max_catchup_ticks=clock.max_catchup_ticks,
            pause_reason="not_started" if clock.start_on_zone_entered else "paused",
        ),
    )


def start_mission(content: LoadedContent, meta: CampaignMeta, mission_id: str) -> TimelineGameState:
    mission = check_can_start(content, meta, mission_id)
    doc = initial_document(content, meta, mission)
    for obj_id in list(meta.carried):
        if obj_id in doc.containers:
            del meta.carried[obj_id]  # carried cargo has landed in this world
    progress = meta.missions[mission.id]
    progress.status = "active"
    progress.attempts += 1
    meta.active_mission = mission.id
    meta.phases[mission.phase] = "active"
    return doc


@dataclass(slots=True)
class Completion:
    record: CompletionRecord
    commit: CommitResult
    next_mission: str | None = None
    phases_opened: list[str] = field(default_factory=list)


_TIER_RANK = {
    "critical_failure": 0,
    "mission_failed": 1,
    "partial": 2,
    "success": 3,
    "exceptional": 4,
}


def complete_mission(ctx: Ctx, *, tier: str | None) -> Completion:
    """Commit a successful mission atomically (the caller persists meta + doc together)."""
    content, meta, doc = ctx.content, ctx.meta, ctx.doc
    mission = content.index.missions[doc.mission_id]
    evidence = list(doc.evidence)
    for rule in mission.completion_evidence:
        if holds(rule.when, ctx) and rule.evidence not in evidence:
            evidence.append(rule.evidence)
    doc.evidence = sorted(set(evidence))
    commit = commit_evidence(content, meta, doc.evidence, completed_mission=mission.id)
    new_discoveries = [d.id for d in doc.discoveries if d.id not in meta.discoveries]
    meta.discoveries = sorted(set(meta.discoveries) | set(new_discoveries))
    for carry in mission.carry:
        meta.carried[carry.to_object] = dict(doc.containers.get(carry.from_object, {}))
    commit_infrastructure(ctx, attempt=meta.missions[mission.id].attempts)
    progress = meta.missions[mission.id]
    progress.status = "completed"
    if tier is not None and _TIER_RANK.get(tier, -1) > _TIER_RANK.get(progress.best_tier or "", -1):
        progress.best_tier = tier
    doc.status = "completed"
    meta.active_mission = None
    phase = content.index.phases[mission.phase]
    if all(
        meta.missions[m].status == "completed"
        for m in phase.missions
        if content.index.missions[m].kind == "primary"
    ):
        meta.phases[phase.id] = "completed"
    before = dict(meta.phases)
    refresh(content, meta)
    opened = [p for p, s in meta.phases.items() if s == "available" and before.get(p) == "locked"]
    record = CompletionRecord(
        mission_id=mission.id,
        attempt=progress.attempts,
        result="completed",
        tier=tier,
        evidence_committed=commit.evidence_added,
        capabilities_progressed=commit.progressed,
        certifications_granted=commit.certifications,
        discoveries_committed=new_discoveries,
    )
    meta.history.append(record)
    nxt = mission.next.mission if mission.next is not None else None
    if nxt is not None and meta.missions[nxt].status not in {"available", "completed", "failed"}:
        nxt = None
    return Completion(record=record, commit=commit, next_mission=nxt, phases_opened=opened)


def commit_infrastructure(ctx: Ctx, *, attempt: int) -> list[str]:
    """Record the end-of-mission state of every infrastructure object of the mission's world
    in campaign meta (atomic with the completion). Failed missions commit nothing."""
    from app.game.world.views import infrastructure_state

    content, meta, doc = ctx.content, ctx.meta, ctx.doc
    world = content.index.worlds[doc.world_id]
    changed: list[str] = []
    for obj in world.objects:
        if obj.infrastructure_type is None:
            continue
        state = infrastructure_state(ctx, obj)
        assert state is not None
        record = InfrastructureRecord(
            type=obj.infrastructure_type,
            world=world.id,
            state=state,
            modules={slot: m.item for slot, m in sorted(doc.modules.get(obj.id, {}).items())},
            mission_id=doc.mission_id,
            attempt=attempt,
        )
        if meta.infrastructure.get(obj.id) != record:
            meta.infrastructure[obj.id] = record
            changed.append(obj.id)
    meta.infrastructure = dict(sorted(meta.infrastructure.items()))
    return changed


def fail_mission(ctx: Ctx, *, tier: str | None) -> CompletionRecord:
    """A failed mission commits nothing; the mission stays replayable."""
    content, meta, doc = ctx.content, ctx.meta, ctx.doc
    mission = content.index.missions[doc.mission_id]
    progress = meta.missions[mission.id]
    progress.status = "failed"
    doc.status = "failed"
    meta.active_mission = None
    if mission.kind == "primary":
        meta.phases[mission.phase] = "failed"
    record = CompletionRecord(
        mission_id=mission.id, attempt=progress.attempts, result="failed", tier=tier
    )
    meta.history.append(record)
    return record
