"""Versioned game content schema (validated at startup and in CI).

Content is data (YAML under ``app/game/content/data``); this module defines its shape. Cross-file
reference checks (ids that must exist, engine bindings that must match the mission scenario,
evidence that must be verified, acyclic prerequisites) live in :mod:`app.game.content.validate`.

Conventions: stable, human-readable dotted ids (``earth.command.engineering.power_bus_b``);
every model forbids unknown fields; numbers that are gameplay choices are labelled by their
provenance (``gameplay_parameter``), never presented as science.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.game.content.vocabulary import (
    AccessState,
    CapabilityDomain,
    ClockMode,
    DiscoveryCategory,
    InfrastructureState,
    ItemCategory,
    ModuleCategory,
    ObjectKind,
    ProvenanceClass,
    ReadinessCategory,
)
from app.simulation.scenarios.schema import Condition

Id = str


class _C(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# ============================================================================ shared pieces
class Provenance(_C):
    """Where a claim comes from. ``verified_evidence`` must cite verified science evidence."""

    classification: ProvenanceClass
    evidence_refs: list[Id] = Field(default_factory=list)
    note: str | None = None


class CapReq(_C):
    capability: Id
    stage: Id


class ItemQty(_C):
    item: Id
    quantity: int = Field(1, ge=1)


class IncidentCond(_C):
    id: Id
    stages: list[Id] = Field(min_length=1)


class ItemCond(_C):
    item: Id
    container: Id | None = None
    min_quantity: int = Field(1, ge=1)


class ModuleCond(_C):
    host: Id
    slot: Id
    module: Id | None = None


class ObjectStateCond(_C):
    object: Id
    field: Literal["access", "operational", "known", "inspected"]
    equals: str | bool


class MissionCond(_C):
    mission: Id
    status: Literal["active", "completed", "failed"]


class OutcomeCond(_C):
    tiers: list[Literal["exceptional", "success", "partial", "mission_failed", "critical_failure"]]


class GameCondition(_C):
    """A condition over game state, mission simulation state and campaign progress.

    Exactly one of the keys is set. ``sim`` reuses the scenario's metric condition; ``sim_event``
    and ``alert`` look at the simulation (backend-internal; never sent to clients)."""

    all: list[GameCondition] | None = None
    any: list[GameCondition] | None = None
    not_: GameCondition | None = Field(None, alias="not")
    flag: str | None = None
    location: Id | None = None
    incident: IncidentCond | None = None
    sim: Condition | None = None
    sim_event: Id | None = None
    alert: Id | None = None
    item: ItemCond | None = None
    module_installed: ModuleCond | None = None
    capability: CapReq | None = None
    object_state: ObjectStateCond | None = None
    mission: MissionCond | None = None
    sim_outcome: OutcomeCond | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> GameCondition:
        keys = [k for k in type(self).model_fields if getattr(self, k) is not None]
        if len(keys) != 1:
            raise ValueError(f"a condition needs exactly one key, got {keys or 'none'}")
        return self


class ObjectUpdate(_C):
    object: Id
    field: Literal["access", "operational", "known"]
    value: str | bool


class CrewIntent(_C):
    crew: Id
    intent: str | None


class Effects(_C):
    """Game-side consequences (the simulation computes the physical ones)."""

    set_flags: list[str] = Field(default_factory=list)
    clear_flags: list[str] = Field(default_factory=list)
    object_updates: list[ObjectUpdate] = Field(default_factory=list)
    location_access: dict[Id, Literal["open", "locked"]] = Field(default_factory=dict)
    insights: list[Id] = Field(default_factory=list)
    discoveries: list[Id] = Field(default_factory=list)
    evidence: list[Id] = Field(default_factory=list)
    add_items: list[ItemQty] = Field(default_factory=list)
    add_items_to: Id | None = None
    crew_intents: list[CrewIntent] = Field(default_factory=list)


class ParamSpec(_C):
    enum: list[str] = Field(min_length=1)


class EngineStep(_C):
    """A simulation decision template. String values ``"$name"`` take the command parameter
    ``name``. Validated against the mission's scenario at load time."""

    decision: dict[str, Any]


class ConditionalEffects(_C):
    when: GameCondition
    effects: Effects


class Requirement(_C):
    """One precondition of an action; ``reason`` is the machine-readable code returned when it
    does not hold."""

    id: Id
    reason: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    when: GameCondition


class Interaction(_C):
    action: str
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    requirements: list[Requirement] = Field(default_factory=list)
    requires_location: bool = True
    consumes: list[ItemQty] = Field(default_factory=list)
    consumes_from: Id | None = None
    engine: list[EngineStep] = Field(default_factory=list)
    engine_by_param: dict[str, dict[str, list[EngineStep]]] = Field(default_factory=dict)
    effects: Effects = Field(default_factory=Effects)
    effects_by_param: dict[str, dict[str, Effects]] = Field(default_factory=dict)
    conditional_effects: list[ConditionalEffects] = Field(default_factory=list)
    once: bool = False


# ============================================================================ world
class Region(_C):
    id: Id
    name: str


class Location(_C):
    id: Id
    name: str
    region: Id
    kind: Literal["zone", "facility", "site", "vehicle_interior"] = "zone"
    access: Literal["open", "locked"] = "open"
    unlock_when: GameCondition | None = None
    crew_sim_location: Literal["habitat", "shelter"] | None = Field(
        None, description="assigning the crew here moves the simulated crew (set_crew_location)"
    )


class SimBinding(_C):
    consumer: Id | None = None
    component: Id | None = None
    rover: bool = False
    opportunity: Id | None = None


class ContainerSpec(_C):
    mass_limit_kg: float | None = Field(None, gt=0)
    volume_limit_l: float | None = Field(None, gt=0)
    accepts: list[ItemCategory] = Field(default_factory=list)
    initial: list[ItemQty] = Field(default_factory=list)


class ObjectInitial(_C):
    access: AccessState = "open"
    known: bool = True
    operational: bool = True


class WorldObject(_C):
    id: Id
    kind: ObjectKind
    name: str
    location: Id
    parent: Id | None = None
    tags: list[str] = Field(default_factory=list)
    mission_relevance: list[Id] = Field(default_factory=list)
    critical: bool = False
    initial: ObjectInitial = Field(default_factory=ObjectInitial)
    binding: SimBinding = Field(default_factory=SimBinding)
    interactions: list[Interaction] = Field(default_factory=list)
    container: ContainerSpec | None = None
    installed_modules: dict[Id, Id] = Field(
        default_factory=dict, description="vehicle/infrastructure slot → module item at start"
    )
    vehicle_class: Id | None = None
    infrastructure_type: Id | None = None


class IncidentStage(_C):
    """Stages are listed in priority order: the current stage is the first whose ``when`` holds
    (``None`` = always). Reaching a ``terminal`` stage is final."""

    id: Id
    when: GameCondition | None = None
    terminal: bool = False
    effects: Effects = Field(default_factory=Effects)


class OutcomeFact(_C):
    id: Id
    when: GameCondition


class Incident(_C):
    """Hidden until it starts: never part of the client content catalog."""

    id: Id
    mission: Id
    message_key: str
    trigger: GameCondition
    involved_objects: list[Id] = Field(default_factory=list)
    involved_crew: list[Id] = Field(default_factory=list)
    pause_clock_on_start: bool = False
    start_effects: Effects = Field(default_factory=Effects)
    stages: list[IncidentStage] = Field(min_length=1)
    facts: list[OutcomeFact] = Field(default_factory=list)


class Discovery(_C):
    id: Id
    category: DiscoveryCategory
    title: str
    summary: str
    location: Id
    provenance: Provenance
    insights: list[Id] = Field(default_factory=list)
    capability_evidence: list[Id] = Field(default_factory=list)


class World(_C):
    id: Id
    name: str
    regions: list[Region]
    locations: list[Location]
    objects: list[WorldObject]
    incidents: list[Incident] = Field(default_factory=list)
    discoveries: list[Discovery] = Field(default_factory=list)


# ============================================================================ progression
class StageDef(_C):
    id: Id
    order: int
    name: str
    description: str


class EvidenceDef(_C):
    id: Id
    description: str


class Capability(_C):
    id: Id
    name: str
    description: str
    domain: CapabilityDomain
    stages: list[Id] = Field(min_length=1)
    prerequisites: list[CapReq] = Field(default_factory=list)
    evidence: dict[Id, list[Id]] = Field(
        default_factory=dict, description="stage → evidence required to reach it"
    )
    provenance: Provenance
    gameplay_effects: list[str] = Field(default_factory=list)
    unlocks: list[Id] = Field(default_factory=list)


class Certification(_C):
    id: Id
    name: str
    description: str
    requires: list[CapReq] = Field(min_length=1)
    granted_on_completion_of: list[Id] = Field(default_factory=list)
    provenance: Provenance


class Progression(_C):
    stages: list[StageDef]
    evidence: list[EvidenceDef]
    capabilities: list[Capability]
    certifications: list[Certification]


# ======================================================================= items, modules, vehicles
class ModuleSpec(_C):
    category: ModuleCategory
    mount: Id
    power_bus: Id | None = None
    data_bus: Id | None = None
    environment_rating: list[Id] = Field(default_factory=list)
    mission_rating: list[Id] = Field(default_factory=list)
    qualification: CapReq | None = None
    provides: list[str] = Field(default_factory=list)


class Item(_C):
    id: Id
    name: str
    category: ItemCategory
    mass_kg: float = Field(ge=0)
    volume_l: float | None = Field(None, ge=0)
    stackable: bool = True
    max_stack: int = Field(99, ge=1)
    unique: bool = False
    tags: list[str] = Field(default_factory=list)
    provenance: Provenance
    module: ModuleSpec | None = None

    @model_validator(mode="after")
    def _module(self) -> Item:
        if (self.category == "module") != (self.module is not None):
            raise ValueError(f"item {self.id}: category 'module' ⇔ a module spec")
        if self.unique and self.stackable:
            raise ValueError(f"item {self.id}: unique items cannot stack")
        return self


class Slot(_C):
    id: Id
    mount: Id
    power_bus: Id | None = None
    data_bus: Id | None = None
    accepts: list[ModuleCategory] = Field(min_length=1)
    required_for_mission: bool = False
    payload: bool = Field(
        False, description="modules in this slot count toward the vehicle payload mass budget"
    )


class VehicleClass(_C):
    id: Id
    name: str
    vehicle_class: Literal["lander", "rover", "transfer_vehicle", "crew_spacecraft", "cargo_lander"]
    mission_role: str
    environment_rating: list[Id]
    mission_rating: list[Id]
    crew_capacity: int = Field(ge=0)
    cargo_mass_limit_kg: float = Field(gt=0)
    cargo_volume_limit_l: float | None = Field(None, gt=0)
    power_budget_kw: float | None = Field(None, gt=0)
    life_support_crew_days: float | None = Field(None, ge=0)
    slots: list[Slot] = Field(default_factory=list)
    qualification: list[CapReq] = Field(default_factory=list)
    provenance: Provenance


class InfrastructureType(_C):
    id: Id
    name: str
    category: Literal[
        "habitat", "power", "communications", "logistics", "science", "isru", "shelter", "mobility"
    ]
    description: str
    depends_on_power: bool = True
    depends_on_comms: bool = False
    depends_on_logistics: bool = False
    requires_capabilities: list[CapReq] = Field(default_factory=list)
    requires_modules: list[ModuleCategory] = Field(default_factory=list)
    initial_state: InfrastructureState = "planned"
    provenance: Provenance


class Catalog(_C):
    items: list[Item]
    vehicle_classes: list[VehicleClass]
    infrastructure_types: list[InfrastructureType]


# ============================================================================ knowledge, crew
class Insight(_C):
    id: Id
    concept: str
    title: str
    observation: str
    explanation: str
    matters_later: str
    simplification: str
    provenance: Provenance
    unlock: GameCondition | None = Field(
        None, description="automatic unlock condition; None = unlocked only by content effects"
    )
    related_objects: list[Id] = Field(default_factory=list)
    why_metric: str | None = Field(
        None, description="Simulation metric the WHY? explanation traces (optional)"
    )


class CrewMember(_C):
    id: Id
    name: str
    role: str
    specialty: str
    sim_crew: dict[Id, Id] = Field(
        default_factory=dict, description="scenario id → crew member id in that scenario"
    )


class Cue(_C):
    id: Id
    speaker: Id
    priority: int = Field(ge=0, le=100)
    cooldown_ticks: int = Field(0, ge=0)
    once: bool = False
    when: GameCondition
    line: str = Field(max_length=140)
    message_key: str


class Narrative(_C):
    crew: list[CrewMember]
    cues: list[Cue]


class Knowledge(_C):
    insights: list[Insight]


# ============================================================================ campaign, readiness
class Prerequisites(_C):
    phases_completed: list[Id] = Field(default_factory=list)
    missions_completed: list[Id] = Field(default_factory=list)
    capabilities: list[CapReq] = Field(default_factory=list)
    discoveries: list[Id] = Field(default_factory=list)
    certifications: list[Id] = Field(default_factory=list)
    readiness_profile: Id | None = None


class ClockSpec(_C):
    start_mode: ClockMode = "PAUSED"
    start_on_zone_entered: bool = True
    realtime_ticks_per_second: float = Field(gt=0, le=10)
    accelerated_multiplier: float = Field(4.0, ge=1, le=60)
    max_catchup_ticks: int = Field(ge=1)


class ScenarioRef(_C):
    source: Literal["game", "registry"]
    id: Id
    file: str | None = None


class AuthorizationGate(_C):
    id: Id
    target: Id
    requirements: list[Requirement] = Field(min_length=1)


class Completion(_C):
    type: Literal["authorization", "simulation_concluded"]
    gate: AuthorizationGate | None = None

    @model_validator(mode="after")
    def _gate(self) -> Completion:
        if (self.type == "authorization") != (self.gate is not None):
            raise ValueError("an authorization completion needs a gate (and only then)")
        return self


class EvidenceRule(_C):
    evidence: Id
    when: GameCondition


class CarryRule(_C):
    """At mission completion the source container/vehicle state becomes the initial state of an
    object in the next mission's world (e.g. the spacecraft cargo hold lands on the Moon)."""

    from_object: Id
    to_object: Id


class NextStep(_C):
    phase: Id
    mission: Id | None = None


class MissionDef(_C):
    id: Id
    phase: Id
    title: str
    summary: str
    kind: Literal["primary", "optional"] = "primary"
    world: Id
    scenario: ScenarioRef
    start_location: Id
    player_kit: Id | None = None
    clock: ClockSpec
    completion: Completion
    completion_evidence: list[EvidenceRule] = Field(
        default_factory=list, description="capability evidence recorded at completion if met"
    )
    carry: list[CarryRule] = Field(default_factory=list)
    inherit_infrastructure: bool = Field(
        False,
        description="start from the campaign's persistent infrastructure records for this world "
        "(installed modules and operational state as last left) instead of the authored state",
    )
    next: NextStep | None = None
    prerequisites: Prerequisites = Field(default_factory=Prerequisites)
    replayable: bool = False


class PhaseDef(_C):
    id: Id
    order: int = Field(ge=1)
    title: str
    summary: str
    authored: bool
    missions: list[Id] = Field(default_factory=list)
    prerequisites: Prerequisites = Field(default_factory=Prerequisites)
    replayable: bool = False


class Campaign(_C):
    id: Id
    title: str
    phases: list[PhaseDef]
    missions: list[MissionDef]


class ReadinessGate(_C):
    id: Id
    category: ReadinessCategory
    title: str
    description: str
    critical: bool
    requires: list[CapReq] = Field(default_factory=list)
    requires_certifications: list[Id] = Field(default_factory=list)


class ReadinessProfile(_C):
    id: Id
    title: str
    lock_code: str
    gates: list[ReadinessGate] = Field(min_length=1)


class Readiness(_C):
    profiles: list[ReadinessProfile]


class Manifest(_C):
    content_id: Id
    content_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    compatible_from: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str


class GameContent(_C):
    """Everything loaded from ``app/game/content/data`` (one immutable object)."""

    manifest: Manifest
    campaign: Campaign
    worlds: list[World]
    progression: Progression
    catalog: Catalog
    knowledge: Knowledge
    narrative: Narrative
    readiness: Readiness


GameCondition.model_rebuild()
