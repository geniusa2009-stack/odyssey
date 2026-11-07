"""HTTP request/response schemas (API layer contracts)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.provider import Topic
from app.simulation.analysis.future_lens import FutureLensRequest
from app.simulation.domain.decisions import DecisionInput
from app.simulation.domain.enums import CrewRole
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState, OutcomeState, PhaseTransition

MAX_SEED = 2**53 - 1
Handle = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")]
MetaValue = str | int | float | bool


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------------- requests
class ParticipantIn(_Req):
    handle: Handle
    role: CrewRole


class CreateSessionRequest(_Req):
    mission_id: str = Field("luna-01", max_length=64)
    scenario_version: str | None = Field(None, max_length=32)
    seed: int | None = Field(None, ge=0, le=MAX_SEED)
    participants: list[ParticipantIn] = Field(default_factory=list, max_length=8)


class DecisionRequest(_Req):
    decision: DecisionInput
    timeline_id: str | None = Field(None, max_length=36)
    participant_id: str | None = Field(None, max_length=36)
    expected_state_version: int | None = Field(
        None, ge=1, description="Optimistic concurrency: the state version the client saw"
    )
    expected_sequence: int | None = Field(
        None, ge=0, description="Optimistic concurrency: current head sequence the client saw"
    )
    metadata: dict[Annotated[str, Field(max_length=64)], MetaValue] = Field(
        default_factory=dict, max_length=16
    )


class AdvanceRequest(_Req):
    ticks: int = Field(1, ge=1, description="Upper bound; settings.max_advance_ticks applies")
    timeline_id: str | None = Field(None, max_length=36)
    participant_id: str | None = Field(None, max_length=36)
    expected_state_version: int | None = Field(
        None, ge=1, description="Optimistic concurrency: the state version the client saw"
    )


class FutureLensBody(FutureLensRequest):
    timeline_id: str | None = Field(None, max_length=36)
    participant_id: str | None = Field(None, max_length=36)


class RewindRequest(_Req):
    decision_id: str = Field(max_length=40)
    alternative: DecisionInput | None = None
    timeline_id: str | None = Field(None, max_length=36)
    continue_ticks: int = Field(0, ge=0)
    activate: bool = True
    label: str | None = Field(None, max_length=64)
    participant_id: str | None = Field(None, max_length=36)


class OrionRequest(_Req):
    topic: Topic = "state_summary"
    question: str = Field("", max_length=500)
    metric: str | None = Field(None, max_length=96)
    tick: int | None = Field(None, ge=0)
    timeline_id: str | None = Field(None, max_length=36)
    participant_id: str | None = Field(None, max_length=36)


# ------------------------------------------------------------------------------- responses
class ScenarioSummary(BaseModel):
    id: str
    scenario_key: str
    version: str
    content_hash: str
    provisional: bool
    title: str
    tick_hours: float
    max_ticks: int
    phases: list[str]
    decision_types: list[str]
    subsystems: list[str]
    components: list[str]
    opportunities: list[str]
    crew: list[dict[str, str]]


class MissionView(BaseModel):
    id: str
    title: str
    description: str
    scenarios: list[ScenarioSummary]


class ParticipantView(BaseModel):
    id: str
    handle: str
    role: str
    joined_at: datetime | None = None


class TimelineView(BaseModel):
    id: str
    parent_timeline_id: str | None
    fork_sequence: int | None
    fork_tick: int | None
    label: str | None
    status: str
    head_tick: int
    head_sequence: int
    head_state_hash: str
    state_version: int
    created_at: datetime | None = None


class SessionView(BaseModel):
    id: str
    mission_id: str
    scenario: ScenarioSummary
    seed: int | None = Field(
        description="Random seed; null when internal endpoints are disabled (production)"
    )
    status: str
    active_timeline_id: str | None
    future_lens_requests: int
    created_at: datetime | None = None
    participants: list[ParticipantView]
    timelines: list[TimelineView]


class StateView(BaseModel):
    session_id: str
    timeline_id: str
    tick: int
    elapsed_hours: float
    phase: str
    status: str
    state_hash: str
    state_version: int
    metrics: dict[str, float]
    state: MissionState


class DecisionRecordView(BaseModel):
    decision_id: str
    timeline_id: str
    sequence: int
    tick: int
    phase: str
    decision_type: str
    inputs: dict[str, Any]
    affected_systems: list[str]
    state_before_hash: str
    state_after_hash: str
    prev_record_hash: str
    record_hash: str
    metadata: dict[str, Any]


class DecisionResponse(BaseModel):
    decision: DecisionRecordView
    tick: int
    state_hash: str
    state_version: int
    events: list[MissionEvent]
    metrics: dict[str, float]


class AdvanceResponse(BaseModel):
    timeline_id: str
    from_tick: int
    to_tick: int
    ticks_run: int
    concluded: bool
    phase: str
    outcome: OutcomeState | None
    state_hash: str
    state_version: int
    events: list[MissionEvent]
    events_truncated: bool
    metrics: dict[str, float]


class TimelineResponse(BaseModel):
    timeline: TimelineView
    ancestry: list[TimelineView]
    decisions: list[DecisionRecordView]
    phase_history: list[PhaseTransition]
    events: list[MissionEvent]
    total_events: int


class RewindResponse(BaseModel):
    timeline: TimelineView
    parent_timeline_id: str
    replaced_decision_id: str
    alternative_decision: DecisionRecordView | None
    tick: int
    state_hash: str
    state_version: int
    active: bool


class VerifyResponse(BaseModel):
    timeline_id: str
    ledger_ok: bool
    replay_ok: bool
    decisions_verified: int
    head_state_hash: str
    replayed_state_hash: str


class MetricInfo(BaseModel):
    name: str
    unit: str
    label: str
    severity: dict[str, Any] | None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
