"""Capability qualification, certification and readiness (no XP).

A capability's stage is *derived* from committed evidence: stage k is reached when the evidence
of every stage up to k has been demonstrated, and only while the capability's prerequisites are
met at their required stages. A stage with no evidence defined cannot be reached yet (content
deferred). Derivation is monotonic because committed evidence only grows.

Readiness profiles are explicit gates. A percentage is ``gates met / gates`` and is always shown
next to the list of missing critical gates; any missing critical gate locks the profile
(``lock_code``, e.g. ``MARS_MISSION_LOCKED``) with the missing capability ids.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.game.content.loader import LoadedContent
from app.game.content.schema import Capability, CapReq
from app.game.world.state import CampaignMeta


def _topo(content: LoadedContent) -> list[Capability]:
    caps = content.index.capabilities
    seen: set[str] = set()
    out: list[Capability] = []

    def visit(cid: str) -> None:
        if cid in seen:
            return
        seen.add(cid)
        for req in caps[cid].prerequisites:
            visit(req.capability)
        out.append(caps[cid])

    for cid in sorted(caps):
        visit(cid)
    return out


def _met(content: LoadedContent, stages: dict[str, str], req: CapReq) -> bool:
    current = stages.get(req.capability)
    if current is None:
        return False
    ladder = content.index.capabilities[req.capability].stages
    return ladder.index(current) >= ladder.index(req.stage)


def derive_stages(content: LoadedContent, evidence: Iterable[str]) -> dict[str, str]:
    have = set(evidence)
    stages: dict[str, str] = {}
    for cap in _topo(content):
        if not all(_met(content, stages, r) for r in cap.prerequisites):
            continue  # locked: evidence is kept, the stage is not granted
        reached = None
        for stage in cap.stages:
            needed = cap.evidence.get(stage)
            if not needed or not set(needed) <= have:
                break
            reached = stage
        if reached is not None:
            stages[cap.id] = reached
    return dict(sorted(stages.items()))


def prerequisites_met(content: LoadedContent, meta: CampaignMeta, reqs: Iterable[CapReq]) -> bool:
    return all(_met(content, meta.capabilities, r) for r in reqs)


@dataclass(slots=True)
class CommitResult:
    progressed: dict[str, str] = field(default_factory=dict)
    certifications: list[str] = field(default_factory=list)
    evidence_added: list[str] = field(default_factory=list)


def commit_evidence(
    content: LoadedContent, meta: CampaignMeta, evidence: Iterable[str], *, completed_mission: str
) -> CommitResult:
    """Commit evidence to the campaign, re-derive stages and grant certifications (idempotent:
    committing the same evidence twice changes nothing)."""
    out = CommitResult()
    for ev in evidence:
        if ev not in meta.evidence:
            meta.evidence.append(ev)
            out.evidence_added.append(ev)
    meta.evidence.sort()
    before = dict(meta.capabilities)
    after = derive_stages(content, meta.evidence)
    for cid, stage in after.items():
        if before.get(cid) != stage:
            out.progressed[cid] = stage
    meta.capabilities = after
    for cert in content.content.progression.certifications:
        if cert.id in meta.certifications:
            continue
        on_mission = not cert.granted_on_completion_of or (
            completed_mission in cert.granted_on_completion_of
        )
        if on_mission and prerequisites_met(content, meta, cert.requires):
            meta.certifications.append(cert.id)
            out.certifications.append(cert.id)
    meta.certifications.sort()
    return out


# ------------------------------------------------------------------ readiness
@dataclass(frozen=True, slots=True)
class MissingCapability:
    capability: str
    required_stage: str
    current_stage: str | None


@dataclass(frozen=True, slots=True)
class GateStatus:
    id: str
    category: str
    title: str
    critical: bool
    met: bool
    missing_capabilities: tuple[MissingCapability, ...]
    missing_certifications: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadinessStatus:
    profile: str
    lock_code: str
    locked: bool
    gates_met: int
    gates_total: int
    critical_missing: tuple[str, ...]
    gates: tuple[GateStatus, ...]

    @property
    def percent(self) -> int:
        return (100 * self.gates_met) // self.gates_total if self.gates_total else 0

    @property
    def missing_capability_ids(self) -> list[str]:
        return sorted(
            {
                mc.capability
                for g in self.gates
                if g.critical and not g.met
                for mc in g.missing_capabilities
            }
        )


def readiness(content: LoadedContent, meta: CampaignMeta, profile_id: str) -> ReadinessStatus:
    profile = content.index.profiles[profile_id]
    gates: list[GateStatus] = []
    for g in profile.gates:
        missing = tuple(
            MissingCapability(r.capability, r.stage, meta.capabilities.get(r.capability))
            for r in g.requires
            if not _met(content, meta.capabilities, r)
        )
        missing_certs = tuple(c for c in g.requires_certifications if c not in meta.certifications)
        gates.append(
            GateStatus(
                id=g.id,
                category=g.category,
                title=g.title,
                critical=g.critical,
                met=not missing and not missing_certs,
                missing_capabilities=missing,
                missing_certifications=missing_certs,
            )
        )
    critical_missing = tuple(g.id for g in gates if g.critical and not g.met)
    return ReadinessStatus(
        profile=profile.id,
        lock_code=profile.lock_code,
        locked=bool(critical_missing),
        gates_met=sum(1 for g in gates if g.met),
        gates_total=len(gates),
        critical_missing=critical_missing,
        gates=tuple(gates),
    )
