"""REST endpoints of ``odyssey.game.v1`` (mounted at ``/api/game/v1``).

One write path: every mutation goes through :class:`~app.game.application.service.GameService`
in one transaction (session row lock + ``expected_state_version`` + idempotency key). Reads are
small, on-demand and session-token protected; bulk state comes from bootstrap/snapshot/restore
and deltas from the realtime stream (docs/UNREAL_BACKEND_CONTRACT.md).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status

from app.api.deps import rate_limit
from app.core.errors import InvalidRequestError
from app.game.api.deps import game_principal, get_game_service, session_token
from app.game.application.service import GameService
from app.game.contracts import protocol as p
from app.game.contracts.analysis import (
    GameBlackBoxView,
    GameEngineeringProfileView,
    GameFutureLensView,
    GameMissionDNAView,
)
from app.game.contracts.progression import (
    CapabilitiesView,
    CatalogView,
    ExpansionMapView,
    ReadinessView,
    VehicleView,
    WhyView,
)
from app.game.contracts.views import ObjectView
from app.services.idempotency import make_context

_ERR = {"model": p.GameErrorResponse}
# Every game route can answer with the shared error envelope; documented once for all routes.
router = APIRouter(
    responses={
        403: _ERR | {"description": "PERMISSION_DENIED (missing/invalid session token)"},
        404: _ERR | {"description": "SESSION_NOT_FOUND / NOT_FOUND"},
        409: _ERR | {"description": "STALE_STATE / DECISION_UNAVAILABLE / MISSION_COMPLETE"},
        422: _ERR | {"description": "VALIDATION_ERROR / INVALID_REQUEST / IDEMPOTENCY_KEY_REUSED"},
        429: _ERR | {"description": "RATE_LIMITED"},
    }
)

SESSION_ID_PATTERN = r"^gs_[a-z2-7]{20,32}$"
TIMELINE_ID_PATTERN = r"^gt_[a-z2-7]{20,32}$"
SEMANTIC_ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,128}$"

SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN, description="Game session id (gs_…)")]
SemanticId = Annotated[str, Path(pattern=SEMANTIC_ID_PATTERN)]
TimelineQ = Annotated[
    str | None, Query(pattern=TIMELINE_ID_PATTERN, description="Default: the active timeline")
]
Service = Annotated[GameService, Depends(get_game_service)]
Token = Annotated[str | None, Depends(session_token)]
Principal = Annotated[str, Depends(game_principal)]
DEFAULT_RL = [Depends(rate_limit("default"))]
EXPENSIVE_RL = [Depends(rate_limit("expensive"))]
REPLAYED_HEADER = "Idempotent-Replayed"


# ------------------------------------------------------------------------------ server
@router.get("/features", response_model=p.ServerFeatures, tags=["game-server"])
async def features(service: Service) -> p.ServerFeatures:
    """Protocol version, semantic actions, event types, error codes and limits (no auth)."""
    return service.features()


@router.get("/catalog", response_model=CatalogView, tags=["game-server"])
async def catalog(service: Service) -> CatalogView:
    """Static content catalog: items, vehicle classes, infrastructure types (no auth)."""
    return service.catalog()


# ------------------------------------------------------------------------------ sessions
@router.post(
    "/sessions",
    response_model=p.CreateGameSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def create_session(
    body: p.CreateGameSessionRequest, service: Service, principal: Principal
) -> p.CreateGameSessionResponse:
    """Start a new campaign. The ``session_token`` is returned once; keep it."""
    return await service.create_session(body, principal)


@router.get(
    "/sessions/{session_id}/bootstrap",
    response_model=p.GameBootstrap,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def bootstrap(session_id: SessionId, service: Service, token: Token) -> p.GameBootstrap:
    return await service.bootstrap(session_id, token)


@router.get(
    "/sessions/{session_id}/snapshot",
    response_model=p.GameSnapshot,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def snapshot(session_id: SessionId, service: Service, token: Token) -> p.GameSnapshot:
    """Authoritative state as stored (does not advance the clock; use /sync or /restore)."""
    return await service.snapshot(session_id, token)


@router.post(
    "/sessions/{session_id}/restore",
    response_model=p.RestoreResult,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def restore(
    session_id: SessionId, body: p.RestoreRequest, service: Service, token: Token
) -> p.RestoreResult:
    """The single restore/reconnect path: settles the clock, returns the snapshot, what happened
    while disconnected and the retained events after ``last_seq`` (or ``resync_required``)."""
    return await service.restore(session_id, token, body)


@router.post(
    "/sessions/{session_id}/sync",
    response_model=p.SyncResult,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def sync(
    session_id: SessionId, body: p.SyncRequest, service: Service, token: Token
) -> p.SyncResult:
    """Settle the server clock now (advance the simulation by the elapsed trusted time)."""
    return await service.sync(session_id, token, body)


@router.get(
    "/sessions/{session_id}/events",
    response_model=p.EventPage,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def events(
    session_id: SessionId,
    service: Service,
    token: Token,
    after_seq: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> p.EventPage:
    return await service.events(session_id, token, after_seq=after_seq, limit=limit)


@router.get(
    "/sessions/{session_id}/checkpoints",
    response_model=p.CheckpointPage,
    tags=["game-session"],
    dependencies=DEFAULT_RL,
)
async def checkpoints(
    session_id: SessionId,
    service: Service,
    token: Token,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> p.CheckpointPage:
    return await service.checkpoints(session_id, token, limit)


# ------------------------------------------------------------------------------ commands
@router.post(
    "/sessions/{session_id}/commands",
    response_model=p.CommandResult,
    tags=["game-command"],
    dependencies=DEFAULT_RL,
)
async def command(
    session_id: SessionId,
    body: p.GameCommandRequest,
    service: Service,
    token: Token,
    principal: Principal,
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Optional; when sent it must equal the body's idempotency_key",
        ),
    ] = None,
) -> p.CommandResult:
    """Request one semantic action. The backend validates legality and decides the result."""
    if idempotency_key is not None and idempotency_key != body.idempotency_key:
        raise InvalidRequestError(
            "Idempotency-Key header and body idempotency_key differ", code="idempotency_mismatch"
        )
    idem = make_context(
        body.idempotency_key,
        route="game_command",
        session_id=session_id,
        body=body.model_dump(mode="json"),
        principal=principal,
    )
    assert idem is not None
    result, replayed = await service.command(session_id, token, body, idem)
    response.headers[REPLAYED_HEADER] = "true" if replayed else "false"
    return result


@router.post(
    "/sessions/{session_id}/missions/{mission_id}/start",
    response_model=p.GameSnapshot,
    tags=["game-command"],
    dependencies=DEFAULT_RL,
)
async def start_mission(
    session_id: SessionId,
    mission_id: SemanticId,
    body: p.StartMissionRequest,
    service: Service,
    token: Token,
) -> p.GameSnapshot:
    """Start (or replay) an available mission. Locked missions answer DECISION_UNAVAILABLE with
    the missing prerequisites (``MARS_MISSION_LOCKED`` lists the missing capability ids)."""
    return await service.start_mission(session_id, token, mission_id, body)


@router.post(
    "/sessions/{session_id}/phases/{phase_id}/start",
    response_model=p.GameSnapshot,
    tags=["game-command"],
    dependencies=DEFAULT_RL,
)
async def start_phase(
    session_id: SessionId,
    phase_id: SemanticId,
    body: p.StartMissionRequest,
    service: Service,
    token: Token,
) -> p.GameSnapshot:
    """Start the next mission of a campaign phase. Prerequisites are checked first: a locked
    phase answers DECISION_UNAVAILABLE with ``phase_locked`` and what is missing; a phase gated by
    a readiness profile answers ``mars_mission_locked`` (``details.lock_code`` =
    ``MARS_MISSION_LOCKED``) with the missing gate and capability ids."""
    return await service.start_phase(session_id, token, phase_id, body)


@router.get(
    "/sessions/{session_id}/rewind-points",
    response_model=p.RewindPoints,
    tags=["game-command"],
    dependencies=DEFAULT_RL,
)
async def rewind_points(session_id: SessionId, service: Service, token: Token) -> p.RewindPoints:
    return await service.rewind_points(session_id, token)


@router.post(
    "/sessions/{session_id}/rewind",
    response_model=p.RewindResult,
    tags=["game-command"],
    dependencies=EXPENSIVE_RL,
)
async def rewind(
    session_id: SessionId, body: p.RewindRequest, service: Service, token: Token
) -> p.RewindResult:
    """Fork the active mission timeline to just before a recorded command (campaign progress
    is never rewound)."""
    return await service.rewind(session_id, token, body)


# ------------------------------------------------------------------------------ progression
@router.get(
    "/sessions/{session_id}/capabilities",
    response_model=CapabilitiesView,
    tags=["game-progression"],
    dependencies=DEFAULT_RL,
)
async def capabilities(session_id: SessionId, service: Service, token: Token) -> CapabilitiesView:
    return await service.capabilities(session_id, token)


@router.get(
    "/sessions/{session_id}/readiness/{profile_id}",
    response_model=ReadinessView,
    tags=["game-progression"],
    dependencies=DEFAULT_RL,
)
async def readiness(
    session_id: SessionId, profile_id: SemanticId, service: Service, token: Token
) -> ReadinessView:
    return await service.readiness(session_id, token, profile_id)


@router.get(
    "/sessions/{session_id}/expansion-map",
    response_model=ExpansionMapView,
    tags=["game-progression"],
    dependencies=DEFAULT_RL,
)
async def expansion_map(session_id: SessionId, service: Service, token: Token) -> ExpansionMapView:
    return await service.expansion_map(session_id, token)


@router.get(
    "/sessions/{session_id}/insights/{insight_id}/why",
    response_model=WhyView,
    tags=["game-progression"],
    dependencies=DEFAULT_RL,
)
async def why(
    session_id: SessionId, insight_id: SemanticId, service: Service, token: Token
) -> WhyView:
    """WHY? for an unlocked insight: the live causal inputs of its metric (no forecasts)."""
    return await service.why(session_id, token, insight_id)


# ------------------------------------------------------------------------------ world detail
@router.get(
    "/sessions/{session_id}/objects/{object_id}",
    response_model=ObjectView,
    tags=["game-world"],
    dependencies=DEFAULT_RL,
)
async def object_detail(
    session_id: SessionId, object_id: SemanticId, service: Service, token: Token
) -> ObjectView:
    return await service.object_detail(session_id, token, object_id)


@router.get(
    "/sessions/{session_id}/vehicles/{vehicle_id}",
    response_model=VehicleView,
    tags=["game-world"],
    dependencies=DEFAULT_RL,
)
async def vehicle(
    session_id: SessionId, vehicle_id: SemanticId, service: Service, token: Token
) -> VehicleView:
    """Shipyard/loadout view: slots, payload mass vs limit, qualification and blockers."""
    return await service.vehicle(session_id, token, vehicle_id)


# ------------------------------------------------------------------------------ analysis
@router.post(
    "/sessions/{session_id}/future-lens",
    response_model=GameFutureLensView,
    tags=["game-analysis"],
    dependencies=EXPENSIVE_RL,
)
async def future_lens(
    session_id: SessionId, body: p.FutureLensRequestBody, service: Service, token: Token
) -> GameFutureLensView:
    """Project up to three semantic candidate actions (known-only knowledge policy)."""
    return await service.future_lens(session_id, token, body)


@router.get(
    "/sessions/{session_id}/black-box",
    response_model=GameBlackBoxView,
    tags=["game-analysis"],
    dependencies=EXPENSIVE_RL,
)
async def black_box(
    session_id: SessionId,
    service: Service,
    token: Token,
    timeline_id: TimelineQ = None,
    counterfactuals: bool = True,
) -> GameBlackBoxView:
    """Causal node/edge graph of what happened on a timeline (past only)."""
    return await service.black_box(session_id, token, timeline_id, counterfactuals=counterfactuals)


@router.get(
    "/sessions/{session_id}/engineering-profile",
    response_model=GameEngineeringProfileView,
    tags=["game-analysis"],
    dependencies=DEFAULT_RL,
)
async def engineering_profile(
    session_id: SessionId, service: Service, token: Token, timeline_id: TimelineQ = None
) -> GameEngineeringProfileView:
    return await service.engineering_profile(session_id, token, timeline_id)


@router.get(
    "/sessions/{session_id}/mission-dna",
    response_model=GameMissionDNAView,
    tags=["game-analysis"],
    dependencies=DEFAULT_RL,
)
async def mission_dna(
    session_id: SessionId, service: Service, token: Token, timeline_id: TimelineQ = None
) -> GameMissionDNAView:
    return await service.mission_dna(session_id, token, timeline_id)
