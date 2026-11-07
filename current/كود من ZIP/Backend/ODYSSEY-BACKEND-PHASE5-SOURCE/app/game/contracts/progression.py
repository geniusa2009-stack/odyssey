"""Read shapes for capabilities, certification, readiness, the Human Expansion Map, knowledge
(WHY?), vehicles (shipyard) and the static content catalog."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.game.contracts.views import GameView, ProvenanceView


class EvidenceStatus(GameView):
    id: str
    description: str
    demonstrated: bool
    pending_in_mission: bool


class StageStatus(GameView):
    stage: str
    reached: bool
    attainable: bool
    evidence: list[EvidenceStatus]


class CapabilityView(GameView):
    id: str
    name: str
    description: str
    domain: str
    stage: str | None
    status: Literal["locked", "not_started", "qualified", "max"]
    prerequisites: list[dict[str, str | bool]]
    stages: list[StageStatus]
    certifications: list[str]
    provenance: ProvenanceView
    gameplay_effects: list[str]
    unlocks: list[str]


class CertificationView(GameView):
    id: str
    name: str
    description: str
    granted: bool
    requires: list[dict[str, str | bool]]
    granted_on_completion_of: list[str]
    provenance: ProvenanceView


class CapabilitiesView(GameView):
    capabilities: list[CapabilityView]
    certifications: list[CertificationView]


class MissingCapabilityView(GameView):
    capability: str
    required_stage: str
    current_stage: str | None


class GateView(GameView):
    id: str
    category: str
    title: str
    critical: bool
    met: bool
    missing_capabilities: list[MissingCapabilityView]
    missing_certifications: list[str]


class ReadinessView(GameView):
    profile: str
    title: str
    locked: bool
    lock: dict[str, object] | None
    gates_met: int
    gates_total: int
    percent: int = Field(description="gates met / gates; never hides a missing critical gate")
    critical_missing: list[str]
    gates: list[GateView]


class MapNode(GameView):
    id: str
    type: Literal[
        "phase",
        "mission",
        "capability",
        "certification",
        "readiness_gate",
        "infrastructure",
        "discovery",
    ]
    label: str
    state: str
    related_mission: str | None = None
    related_capability: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    progress: str | None = None


class MapEdge(GameView):
    source: str
    target: str
    kind: Literal["requires", "unlocks", "qualifies", "certifies", "gates", "contains"]
    explanation: str
    satisfied: bool


class ExpansionMapView(GameView):
    nodes: list[MapNode]
    edges: list[MapEdge]


class WhyInput(GameView):
    metric: str
    label: str
    value: float
    unit: str
    mechanism: str


class WhyView(GameView):
    insight: str
    concept: str
    observation: str
    explanation: str
    metric: str | None
    label: str | None = None
    value: float | None = None
    unit: str | None = None
    inputs: list[WhyInput] = Field(default_factory=list)
    active_alerts: list[str] = Field(default_factory=list)
    related_objects: list[str] = Field(default_factory=list)
    provenance: ProvenanceView
    available: bool
    note: str


class KnowledgeView(GameView):
    insights: list[dict[str, object]]


class SlotStatus(GameView):
    slot: str
    mount: str
    accepts: list[str]
    required_for_mission: bool
    payload: bool
    installed: str | None


class VehicleView(GameView):
    id: str
    name: str
    vehicle_class: str
    class_name: str
    mission_role: str
    crew_capacity: int
    environment_rating: list[str]
    mission_rating: list[str]
    payload_mass_kg: float
    payload_limit_kg: float
    power_budget_kw: float | None
    life_support_crew_days: float | None
    slots: list[SlotStatus]
    cargo: list[str]
    qualification: list[dict[str, str | bool]]
    ready: bool
    blockers: list[str]
    provenance: ProvenanceView


class CatalogItemView(GameView):
    id: str
    name: str
    category: str
    mass_kg: float
    volume_l: float | None
    stackable: bool
    max_stack: int
    unique: bool
    tags: list[str]
    provenance: ProvenanceView
    module: dict[str, object] | None = None


class CatalogView(GameView):
    content_version: str
    items: list[CatalogItemView]
    vehicle_classes: list[dict[str, object]]
    infrastructure_types: list[dict[str, object]]
