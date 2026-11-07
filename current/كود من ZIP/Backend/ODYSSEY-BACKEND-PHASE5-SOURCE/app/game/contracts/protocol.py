"""``odyssey.game.v1`` request/response contract (frozen; see docs/UNREAL_BACKEND_CONTRACT.md).

Every command carries what the backend needs for legality, concurrency, idempotency and
tracing. The client *requests*; the backend *decides*. Nothing here lets a client set resource
values, mission completion, certification, inventory quantities, repairs or unlocks.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.game.contracts.views import (
    CampaignView,
    ClockView,
    DiscoveryView,
    GameView,
    InsightView,
    MissionView,
    WorldView,
)

GAME_PROTOCOL: Literal["odyssey.game.v1"] = "odyssey.game.v1"
_ID = r"^[A-Za-z0-9_.:\-]{1,128}$"
_KEY = r"^[A-Za-z0-9_.:\-]{8,128}$"
ParamValue = str | int


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameSessionRequest(_Req):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    display_name: str = Field("Commander", min_length=1, max_length=64)


class GameCommandRequest(_Req):
    """One semantic action. ``expected_state_version`` must equal the session's current
    ``state_version`` (else ``STALE_STATE``); ``idempotency_key`` makes retries safe."""

    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    command_id: str = Field(pattern=_ID, description="Client-generated unique id (trace id)")
    session_id: str = Field(pattern=_ID)
    timeline_id: str | None = Field(
        None, pattern=_ID, description="Optional: rejected (STALE_STATE) if not the active one"
    )
    expected_state_version: int = Field(ge=1)
    idempotency_key: str = Field(pattern=_KEY)
    action: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$", max_length=48)
    actor: str = Field("commander", pattern=_ID)
    target: str | None = Field(None, pattern=_ID)
    params: dict[str, ParamValue] = Field(default_factory=dict, max_length=8)
    client_timestamp: str | None = Field(None, max_length=40, description="Informational only")
    anchor: str | None = Field(
        None, pattern=_ID, description="Unreal world anchor the action happened at (logged only)"
    )


class SyncRequest(_Req):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    expected_state_version: int | None = Field(None, ge=1)


class RestoreRequest(_Req):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    last_seq: int | None = Field(None, ge=0, description="Last realtime seq the client applied")


class StartMissionRequest(_Req):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    expected_state_version: int = Field(ge=1)


class RewindRequest(_Req):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    command_id: str = Field(pattern=_ID, description="Rewind to just before this command")
    expected_state_version: int = Field(ge=1)


class FutureLensRequestBody(_Req):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    candidates: list[GameCandidate] = Field(min_length=1, max_length=3)
    horizon_ticks: int = Field(12, ge=1, le=48)


class GameCandidate(_Req):
    """A semantic action to preview (same shape as a command's action/target/params)."""

    id: str = Field(pattern=r"^[a-z0-9_\-]{1,32}$")
    action: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$", max_length=48)
    target: str | None = Field(None, pattern=_ID)
    params: dict[str, ParamValue] = Field(default_factory=dict, max_length=8)


FutureLensRequestBody.model_rebuild()


# ------------------------------------------------------------------ envelopes and responses
class GameEventEnvelope(GameView):
    """A realtime event. ``seq`` is per session, gap-free and strictly increasing."""

    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    event_id: str
    seq: int
    session_id: str
    timeline_id: str
    state_version: int
    prev_state_version: int
    type: str
    scope: Literal["world", "mission", "crew", "campaign", "session"]
    sim_tick: int
    sim_time_hours: float
    server_time: str
    payload: dict[str, Any]


class GameControlFrame(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    type: Literal["CONNECTED", "RESUMED", "RESYNC_REQUIRED", "PONG"]
    session_id: str
    state_version: int | None = None
    last_seq: int | None = None
    replayed: int | None = None
    reason: str | None = None
    restore_path: str | None = None


class TimelineRef(GameView):
    id: str
    mission_id: str
    attempt: int
    status: str
    parent_timeline_id: str | None = None


class SessionRef(GameView):
    id: str
    status: str
    content_id: str
    content_version: str
    state_version: int
    last_seq: int
    created_at: str


class ResumeInfo(GameView):
    last_seq: int
    ws_path: str
    events_path: str
    restore_path: str
    retained_events: int


class GameSnapshot(GameView):
    """The authoritative state a client needs to (re)build its world. Contains nothing hidden."""

    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session: SessionRef
    timeline: TimelineRef
    state_version: int
    campaign: CampaignView
    mission: MissionView
    clock: ClockView
    world: WorldView
    discoveries: list[DiscoveryView]
    insights: list[InsightView]
    resume: ResumeInfo


class ActionParamInfo(GameView):
    name: str
    kind: str
    required: bool
    values: list[str] = Field(default_factory=list)


class ActionInfo(GameView):
    type: str
    target: str
    summary: str
    mutates: bool
    content_defined: bool
    params: list[ActionParamInfo]


class ServerFeatures(GameView):
    protocol: str
    content_version: str
    clock_modes: list[str]
    actions: list[ActionInfo]
    event_types: list[str]
    error_codes: list[str]
    limits: dict[str, int]
    auth: str


class GameBootstrap(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    features: ServerFeatures
    snapshot: GameSnapshot


class CreateGameSessionResponse(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_token: str = Field(description="Shown once; send as 'Authorization: Bearer <token>'")
    bootstrap: GameBootstrap


class CommandResult(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    command_id: str
    action: str
    target: str | None
    result: Literal["applied", "no_change"]
    reason: str | None = None
    session_id: str
    timeline_id: str
    state_version: int
    prev_state_version: int
    sim_tick: int
    last_seq: int
    events: list[GameEventEnvelope]
    context: dict[str, Any] | None = None
    mission_transition: dict[str, Any] | None = None


class SyncResult(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    timeline_id: str
    state_version: int
    sim_tick: int
    ticks_advanced: int
    clock: ClockView
    last_seq: int
    events: list[GameEventEnvelope]


class DisconnectSummary(GameView):
    ticks_advanced: int
    from_tick: int
    to_tick: int
    event_types: dict[str, int]


class RestoreResult(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    snapshot: GameSnapshot
    resync_required: bool
    reason: str | None = None
    events: list[GameEventEnvelope]
    while_disconnected: DisconnectSummary


class EventPage(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    after_seq: int
    last_seq: int
    resync_required: bool
    events: list[GameEventEnvelope]
    has_more: bool


class CheckpointView(GameView):
    id: str
    kind: str
    label: str
    mission_id: str
    timeline_id: str
    state_version: int
    sim_tick: int
    location: str
    created_at: str


class CheckpointPage(GameView):
    checkpoints: list[CheckpointView]


class RewindPointView(GameView):
    command_id: str
    action: str
    target: str | None
    sim_tick: int
    state_version: int


class RewindPoints(GameView):
    timeline_id: str
    points: list[RewindPointView]


class RewindResult(GameView):
    protocol: Literal["odyssey.game.v1"] = GAME_PROTOCOL
    session_id: str
    previous_timeline_id: str
    timeline: TimelineRef
    state_version: int
    sim_tick: int
    events: list[GameEventEnvelope]


# ------------------------------------------------------------------ errors (documentation)
class GameErrorBody(GameView):
    """The shared public error envelope (app/core/errors.py; identical to API v1)."""

    code: str = Field(description="One of the frozen public codes (STALE_STATE, …)")
    reason: str = Field(description="Specific machine-readable cause (e.g. not_at_location)")
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    recoverable: bool
    state_version: int | None = None


class GameErrorResponse(GameView):
    error: GameErrorBody
