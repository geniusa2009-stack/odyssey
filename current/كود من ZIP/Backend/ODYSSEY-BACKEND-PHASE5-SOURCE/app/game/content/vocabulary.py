"""Closed vocabularies shared by content, domain and protocol (no imports from the domain)."""

from __future__ import annotations

from typing import Literal

# Semantic action types the backend understands. Movement, camera, animation, physics and
# presentation are Unreal concerns and are deliberately absent.
ACTION_TYPES: tuple[str, ...] = (
    "world.zone_entered",
    "world.poi_discovered",
    "system.inspect",
    "system.set_mode",
    "power.reroute",
    "repair.perform",
    "science.instrument_operate",
    "science.sample_collect",
    "cargo.transfer",
    "inventory.move",
    "module.install",
    "module.remove",
    "infrastructure.activate",
    "infrastructure.deactivate",
    "vehicle.inspect",
    "vehicle.dispatch",
    "crew.assign_location",
    "npc.context_request",
    "mission.authorize",
    "mission.clock_set",
    "checkpoint.save",
)
# Actions whose effect is defined per target object in content (interactions); the others have
# dedicated handlers with generic rules (cargo, modules, authorization, clock, checkpoints, ...).
INTERACTION_ACTIONS: frozenset[str] = frozenset(
    {
        "system.inspect",
        "system.set_mode",
        "power.reroute",
        "repair.perform",
        "science.instrument_operate",
        "science.sample_collect",
        "world.poi_discovered",
        "infrastructure.activate",
        "infrastructure.deactivate",
        "vehicle.inspect",
        "vehicle.dispatch",
    }
)

ObjectKind = Literal[
    "system",
    "interactable",
    "vehicle",
    "subsystem",
    "container",
    "facility",
    "poi",
    "science_site",
    "resource_site",
    "mission_object",
    "artifact",
    "infrastructure",
]
AccessState = Literal["open", "locked", "restricted", "inspection_ready"]
ProvenanceClass = Literal[
    "verified_evidence",
    "educational_abstraction",
    "gameplay_parameter",
    "story_assumption",
    "unverified",
]
ItemCategory = Literal["spare", "sample", "tool", "consumable", "cargo", "module", "equipment"]
ModuleCategory = Literal[
    "power",
    "storage",
    "life_support",
    "science",
    "communications",
    "mobility",
    "radiation_protection",
    "cargo",
    "robotics",
    "isru",
]
CapabilityDomain = Literal[
    "transportation",
    "habitation",
    "power",
    "life_support",
    "logistics",
    "communications",
    "autonomy",
    "robotics",
    "mobility",
    "isru",
    "science",
    "infrastructure",
]
ReadinessCategory = Literal[
    "transport",
    "long_duration_habitation",
    "life_support",
    "power",
    "radiation_protection",
    "communications",
    "autonomy",
    "robotics",
    "logistics",
    "surface_systems",
    "entry_descent_landing",
    "return_capability",
]
InfrastructureState = Literal[
    "planned", "under_construction", "operational", "degraded", "offline", "damaged"
]
ModuleState = Literal[
    "stored", "installed", "operational", "offline", "damaged", "maintenance_required"
]
DiscoveryCategory = Literal[
    "science",
    "resource",
    "terrain",
    "historical_artifact",
    "engineering_observation",
    "mission_anomaly",
]
ClockMode = Literal["PAUSED", "REALTIME", "ACCELERATED", "DECISION_PAUSED"]
PhaseStatus = Literal["locked", "available", "active", "completed", "failed"]
CAMPAIGN_PHASES: tuple[str, ...] = (
    "EARTH_COMMAND",
    "LUNA_01",
    "LUNAR_SURVIVAL",
    "LUNAR_EXPLORATION",
    "LUNAR_NETWORK",
    "DEEP_SPACE_READINESS",
    "PATH_TO_MARS",
    "MARS_01",
)
