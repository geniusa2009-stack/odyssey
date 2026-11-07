"""Client-safe read shapes of ``odyssey.game.v1`` (snapshot/bootstrap building blocks).

Closed and frozen like the v1 read models. They never contain: the seed, raw database ids,
unstarted incidents, unfired unforeseeable events, event schedules or engine internals.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GameView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProvenanceView(GameView):
    classification: str
    evidence_refs: list[str] = Field(default_factory=list)
    note: str | None = None


class InteractionView(GameView):
    action: str
    params: dict[str, list[str]] = Field(default_factory=dict)
    available: bool
    reason: str | None = None


class ModuleSlotView(GameView):
    slot: str
    item: str
    state: str


class ObjectView(GameView):
    id: str
    kind: str
    name: str
    location: str
    parent: str | None = None
    tags: list[str]
    critical: bool
    access: str
    inspected: bool
    status: Literal["operational", "degraded", "damaged", "maintenance", "offline", "nominal"]
    power: Literal["powered", "partial", "unpowered", "off"] | None = None
    mode: str | None = None
    charge_kwh: float | None = None
    vehicle_class: str | None = None
    infrastructure_type: str | None = None
    infrastructure_state: str | None = None
    modules: list[ModuleSlotView] = Field(default_factory=list)
    interactions: list[InteractionView] = Field(default_factory=list)


class ItemStackView(GameView):
    item: str
    quantity: int
    mass_kg: float
    condition: Literal["nominal"] = "nominal"


class ContainerView(GameView):
    id: str
    name: str
    location: str
    role: Literal["inventory", "cargo", "storage"]
    vehicle: str | None = None
    mass_kg: float
    mass_limit_kg: float | None
    volume_l: float
    volume_limit_l: float | None
    items: list[ItemStackView]


class LocationView(GameView):
    id: str
    name: str
    region: str
    kind: str
    access: Literal["open", "locked"]
    visited: bool


class IncidentView(GameView):
    id: str
    message_key: str
    stage: str
    started_tick: int
    resolved_tick: int | None
    involved_objects: list[str]
    involved_crew: list[str]
    facts: list[str]


class CueView(GameView):
    """A fired contextual cue. Unreal decides when/how (or whether) it is performed."""

    cue: str
    speaker: str
    priority: int
    tick: int
    line: str
    message_key: str
    once: bool = False
    cooldown_ticks: int = 0
    eligible_again_tick: int | None = Field(
        None, description="simulation tick from which the cue may fire again (None: never)"
    )


class CrewView(GameView):
    id: str
    name: str
    role: str
    specialty: str
    intent: str | None
    location: str | None
    involved_incidents: list[str]
    health_band: Literal["nominal", "degraded", "critical"] | None = None


class DiscoveryView(GameView):
    id: str
    category: str
    title: str
    summary: str
    location: str
    mission_id: str
    tick: int | None = None
    source: str | None = Field(None, description="who made it (player / crew id) on this timeline")
    committed: bool
    provenance: ProvenanceView
    insights: list[str] = Field(default_factory=list, description="knowledge it unlocks")
    capability_evidence: list[str] = Field(
        default_factory=list, description="evidence it contributes (counts at mission completion)"
    )


class InsightView(GameView):
    id: str
    concept: str
    title: str
    observation: str
    explanation: str
    matters_later: str
    simplification: str
    provenance: ProvenanceView
    related_objects: list[str]
    why_available: bool


class ClockView(GameView):
    mode: str
    started: bool
    pause_reason: str | None
    sim_tick: int
    max_ticks: int
    tick_hours: float
    elapsed_hours: float
    ticks_per_second: float
    seconds_per_tick: float | None
    max_catchup_ticks: int


class RequirementView(GameView):
    id: str
    met: bool
    reason: str


class AuthorizationView(GameView):
    gate: str
    target: str
    available: bool
    authorized: bool
    requirements: list[RequirementView]


class ObjectiveBrief(GameView):
    id: str
    category: str
    required: bool
    status: str
    message_key: str


class ResourceBrief(GameView):
    id: str
    label: str
    value: float
    unit: str
    state: str
    warning_state: str


class AlertBrief(GameView):
    id: str
    severity: str
    category: str


class MissionView(GameView):
    id: str
    phase: str
    title: str
    summary: str
    status: str
    simulation_status: str
    completion: Literal["authorization", "simulation_concluded"]
    authorization: AuthorizationView | None = None
    objectives: list[ObjectiveBrief]
    resources: list[ResourceBrief]
    alerts: list[AlertBrief]
    outcome_tier: str | None = None


class WorldView(GameView):
    id: str
    name: str
    player_location: str
    locations: list[LocationView]
    objects: list[ObjectView]
    containers: list[ContainerView]
    incidents: list[IncidentView]
    crew: list[CrewView]
    recent_cues: list[CueView]


class PhaseView(GameView):
    id: str
    order: int
    title: str
    summary: str
    status: str
    authored: bool
    replayable: bool
    missions: list[str]
    missing: dict[str, object] = Field(default_factory=dict)


class MissionProgressView(GameView):
    id: str
    phase: str
    status: str
    attempts: int
    best_tier: str | None
    replayable: bool


class CapabilityBrief(GameView):
    id: str
    stage: str | None


class InfrastructureRecordView(GameView):
    """Persistent (campaign-global) infrastructure as last left at a completed mission."""

    object: str
    type: str
    world: str
    state: str
    modules: dict[str, str] = Field(default_factory=dict)
    mission_id: str


class CampaignView(GameView):
    id: str
    content_version: str
    active_mission: str | None
    phases: list[PhaseView]
    missions: list[MissionProgressView]
    capabilities: list[CapabilityBrief]
    certifications: list[str]
    discoveries: list[str]
    insights: list[str]
    infrastructure: list[InfrastructureRecordView] = Field(default_factory=list)
