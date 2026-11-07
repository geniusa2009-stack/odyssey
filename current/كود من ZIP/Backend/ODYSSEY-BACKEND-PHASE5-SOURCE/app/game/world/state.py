"""Authoritative game state documents.

Two documents, with an explicit ownership rule (docs/SAVE_RESTORE.md, "timeline ownership"):

* :class:`TimelineGameState` — **timeline-local**. Everything that belongs to one play-through
  of one mission on one timeline: player semantic location, world object states, containers and
  cargo, installed modules, incidents, crew intents, cues, flags, the mission clock, and the
  *pending* discoveries/evidence produced in this mission. Rewind forks this document.
* :class:`CampaignMeta` — **campaign-global**, stored on the game session. Phase/mission status,
  completed-mission history, committed capability evidence and stages, certifications,
  committed discoveries and unlocked knowledge. It changes only at mission completion (atomic
  commit of the pending items from the completing timeline) and on knowledge unlock (no gameplay
  power). Rewind never touches it, so rewinding cannot duplicate or farm meta progression.

Both are plain JSON documents (pydantic) so they can be snapshotted, hashed and restored
exactly. They never hold coordinates or engine internals.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.game.content.vocabulary import (
    AccessState,
    ClockMode,
    InfrastructureState,
    ModuleState,
    PhaseStatus,
)
from app.simulation.canonical import sha256_hex

GAME_STATE_SCHEMA_VERSION = 1
MAX_RECENT_CUES = 8


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=False)


class ObjectState(_M):
    access: AccessState = "open"
    known: bool = True
    operational: bool = True
    inspected: bool = False


class IncidentState(_M):
    id: str
    stage: str
    started_tick: int
    resolved_tick: int | None = None
    facts: list[str] = Field(default_factory=list)


class CrewState(_M):
    intent: str | None = None
    location: str | None = None


class InstalledModule(_M):
    item: str
    state: ModuleState = "installed"


class ClockState(_M):
    """Server-authoritative mission clock (see app/game/runtime/clock.py)."""

    mode: ClockMode = "PAUSED"
    started: bool = False
    realtime_ticks_per_second: float
    accelerated_multiplier: float
    max_catchup_ticks: int
    anchor_wall_ms: int = 0
    anchor_tick: int = 0
    pause_reason: str | None = "not_started"


class CueFire(_M):
    cue: str
    speaker: str
    priority: int
    tick: int
    line: str
    message_key: str


class DiscoveryRecord(_M):
    id: str
    mission_id: str
    location: str
    tick: int
    source: str = "player"


class TimelineGameState(_M):
    schema_version: int = GAME_STATE_SCHEMA_VERSION
    mission_id: str
    world_id: str
    status: Literal["active", "completed", "failed"] = "active"
    player_location: str
    visited: list[str] = Field(default_factory=list)
    locations: dict[str, Literal["open", "locked"]]
    objects: dict[str, ObjectState]
    containers: dict[str, dict[str, int]]
    modules: dict[str, dict[str, InstalledModule]] = Field(default_factory=dict)
    incidents: dict[str, IncidentState] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    crew: dict[str, CrewState] = Field(default_factory=dict)
    cue_last_tick: dict[str, int] = Field(default_factory=dict)
    recent_cues: list[CueFire] = Field(default_factory=list)
    once_done: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    discoveries: list[DiscoveryRecord] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    authorized: list[str] = Field(default_factory=list)
    clock: ClockState

    # ---------------------------------------------------------------- small helpers
    def has_flag(self, flag: str) -> bool:
        return flag in self.flags

    def set_flag(self, flag: str) -> bool:
        if flag in self.flags:
            return False
        self.flags.append(flag)
        self.flags.sort()
        return True

    def clear_flag(self, flag: str) -> bool:
        if flag not in self.flags:
            return False
        self.flags.remove(flag)
        return True

    def discovery_ids(self) -> set[str]:
        return {d.id for d in self.discoveries}

    def state_hash(self) -> str:
        return sha256_hex(self.model_dump(mode="json"))


class MissionProgress(_M):
    status: Literal["locked", "available", "active", "completed", "failed"] = "locked"
    attempts: int = 0
    best_tier: str | None = None


class CompletionRecord(_M):
    mission_id: str
    attempt: int
    result: Literal["completed", "failed"]
    tier: str | None = None
    evidence_committed: list[str] = Field(default_factory=list)
    capabilities_progressed: dict[str, str] = Field(default_factory=dict)
    certifications_granted: list[str] = Field(default_factory=list)
    discoveries_committed: list[str] = Field(default_factory=list)


class InfrastructureRecord(_M):
    """Campaign-global record of a piece of infrastructure as the player left it at the end of
    a completed mission (the outpost registry). Seeds later missions that inherit it."""

    type: str
    world: str
    state: InfrastructureState
    modules: dict[str, str] = Field(default_factory=dict)
    mission_id: str
    attempt: int


class CampaignMeta(_M):
    schema_version: int = GAME_STATE_SCHEMA_VERSION
    content_version: str
    active_mission: str | None = None
    phases: dict[str, PhaseStatus]
    missions: dict[str, MissionProgress]
    evidence: list[str] = Field(default_factory=list)
    capabilities: dict[str, str] = Field(default_factory=dict)
    certifications: list[str] = Field(default_factory=list)
    discoveries: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    carried: dict[str, dict[str, int]] = Field(default_factory=dict)
    infrastructure: dict[str, InfrastructureRecord] = Field(default_factory=dict)
    history: list[CompletionRecord] = Field(default_factory=list)

    def state_hash(self) -> str:
        return sha256_hex(self.model_dump(mode="json"))
