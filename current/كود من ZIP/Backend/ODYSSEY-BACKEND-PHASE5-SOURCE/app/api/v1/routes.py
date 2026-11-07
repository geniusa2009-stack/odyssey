"""Versioned REST API (/api/v1).

Frozen frontend-safe endpoints (tags ``contract-*``, docs/API_FREEZE_V1.md) sit next to the
earlier engineering endpoints, which are tagged ``internal`` and hidden (404) in production.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.ai.orion import OrionResponse
from app.api.container import Container
from app.api.deps import (
    get_container,
    get_contract_service,
    get_db,
    get_principal,
    get_service,
    internal_endpoint,
    rate_limit,
)
from app.core.errors import InvalidRequestError, NotFoundError
from app.nasa.models import DataEnvelope, NASADataSource, SpaceWeatherEvent
from app.read_models.analysis import (
    BlackBoxView,
    EngineeringProfileView,
    ForkPreviewView,
    FutureLensView,
    MissionDNAView,
    MissionHistoryView,
    RewindPointsView,
    ScienceClaimView,
    TimelineChangeView,
    TimelineTreeView,
    build_claim,
)
from app.read_models.bootstrap import (
    ApiInfo,
    CapabilitiesResponse,
    MissionBootstrap,
    build_capabilities,
)
from app.read_models.decisions import AvailableDecisionsView
from app.read_models.mission import MissionCompletionView, MissionSnapshotView
from app.read_models.objectives import ObjectiveOutlookView
from app.read_models.radiation import RadiationBudgetView
from app.read_models.resources import ResourceDetailView
from app.read_models.results import AdvanceResultView, DecisionResultView, EventsPage
from app.read_models.visibility import redact_usage, unforeseeable_event_ids
from app.schemas import api
from app.schemas.commands import (
    AdvanceCommand,
    BranchCommand,
    DecisionCommand,
    FutureLensCommand,
)
from app.science.evidence import ScienceEvidence
from app.services import mission_service as svc_mod
from app.services.contract_service import MAX_HISTORY_EVENTS, ContractService
from app.services.idempotency import IdempotencyContext, make_context
from app.services.mission_service import MissionService
from app.simulation.analysis.black_box import BlackBoxReport
from app.simulation.analysis.future_lens import FutureLensResult
from app.simulation.analysis.mission_dna import MissionDNA
from app.simulation.analysis.profile import EngineeringProfile
from app.simulation.analysis.root_cause import RootCauseTrace
from app.simulation.scenarios.loader import list_scenarios
from app.telemetry import runtime_stats
from app.telemetry.stats import OperationStats

router = APIRouter(prefix="/api/v1")

SessionId = Annotated[str, Path(min_length=1, max_length=36, pattern=r"^[0-9a-fA-F\-]+$")]
TimelineQ = Annotated[str | None, Query(max_length=36)]
Service = Annotated[MissionService, Depends(get_service)]
Contract = Annotated[ContractService, Depends(get_contract_service)]
Principal = Annotated[str, Depends(get_principal)]
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Optional; 8-128 characters of [A-Za-z0-9_.:-] (docs/API_CONTRACT.md)",
    ),
]
DEFAULT_RL = [Depends(rate_limit("default"))]
EXPENSIVE_RL = [Depends(rate_limit("expensive"))]
# Internal engineering endpoints: 404 unless settings.internals_exposed (off in production).
INTERNAL = [Depends(internal_endpoint)]
REPLAYED_HEADER = "Idempotent-Replayed"


def _idem(
    key: str | None, route: str, session_id: str | None, body: Any, principal: str
) -> IdempotencyContext | None:
    payload = body.model_dump(mode="json") if hasattr(body, "model_dump") else body
    return make_context(key, route=route, session_id=session_id, body=payload, principal=principal)


def _replayed(response: Response, replayed: bool) -> None:
    response.headers[REPLAYED_HEADER] = "true" if replayed else "false"


# ------------------------------------------------------------------------------ health
@router.get("/health", response_model=api.HealthResponse, tags=["ops"])
async def health() -> api.HealthResponse:
    return api.HealthResponse(status="ok", version=__version__)


@router.get("/ready", response_model=api.ReadyResponse, tags=["ops"])
async def ready(
    db: AsyncSession = Depends(get_db), container: Container = Depends(get_container)
) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # readiness must report, not raise
        checks["database"] = "unavailable"
    if container.redis is not None:
        try:
            await container.redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
    else:
        checks["redis"] = "not_configured"
    checks["scenarios"] = "ok" if list_scenarios() else "missing"
    ok = all(v in ("ok", "not_configured") for v in checks.values())
    body = api.ReadyResponse(status="ready" if ok else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


@router.get("/ops/stats", response_model=list[OperationStats], tags=["ops"])
async def ops_stats(container: Container = Depends(get_container)) -> list[OperationStats]:
    """In-process engine run statistics. Disabled in production (exposes load information)."""
    if container.settings.environment == "production":
        raise NotFoundError("not found", code="not_found")
    return runtime_stats.snapshot()


# ------------------------------------------------------------------------------ missions
@router.get(
    "/missions", response_model=list[api.MissionView], tags=["missions"], dependencies=DEFAULT_RL
)
async def list_missions(service: Service) -> list[api.MissionView]:
    return await service.list_missions()


@router.get(
    "/missions/{mission_id}",
    response_model=api.MissionView,
    tags=["missions"],
    dependencies=DEFAULT_RL,
)
async def get_mission(
    mission_id: Annotated[str, Path(max_length=64)], service: Service
) -> api.MissionView:
    return await service.get_mission(mission_id)


@router.get(
    "/missions/{mission_id}/metrics",
    response_model=list[api.MetricInfo],
    tags=["missions"],
    dependencies=DEFAULT_RL,
)
async def mission_metrics(
    mission_id: Annotated[str, Path(max_length=64)], service: Service
) -> list[api.MetricInfo]:
    """Catalogue of metric names usable in traces and ORION questions for the latest scenario."""
    return await service.metric_catalog(mission_id)


# ------------------------------------------------------------------------------ sessions
@router.post(
    "/mission-sessions",
    response_model=api.SessionView,
    status_code=status.HTTP_201_CREATED,
    tags=["sessions"],
    dependencies=DEFAULT_RL,
)
async def create_session(
    body: api.CreateSessionRequest,
    service: Service,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> api.SessionView:
    idem = _idem(idempotency_key, "create_session", None, body, principal)
    view, replayed = await service.create_session(body, idem)
    _replayed(response, replayed)
    return view


@router.get(
    "/mission-sessions/{session_id}",
    response_model=api.SessionView,
    tags=["sessions"],
    dependencies=DEFAULT_RL,
)
async def get_session(session_id: SessionId, service: Service) -> api.SessionView:
    return await service.get_session(session_id)


@router.post(
    "/mission-sessions/{session_id}/decisions",
    response_model=api.DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
    dependencies=INTERNAL + DEFAULT_RL,
)
async def post_decision(
    session_id: SessionId,
    body: api.DecisionRequest,
    service: Service,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> api.DecisionResponse:
    idem = _idem(idempotency_key, "decision", session_id, body, principal)
    result, replayed = await service.apply_decision(session_id, body, idem)
    _replayed(response, replayed)
    return result


@router.post(
    "/mission-sessions/{session_id}/advance",
    response_model=api.AdvanceResponse,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def advance(
    session_id: SessionId,
    body: api.AdvanceRequest,
    service: Service,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> api.AdvanceResponse:
    idem = _idem(idempotency_key, "advance", session_id, body, principal)
    result, replayed = await service.advance(session_id, body, idem)
    _replayed(response, replayed)
    return result


@router.get(
    "/mission-sessions/{session_id}/state",
    response_model=api.StateView,
    tags=["internal"],
    dependencies=INTERNAL + DEFAULT_RL,
)
async def get_state(
    session_id: SessionId, service: Service, timeline_id: TimelineQ = None
) -> api.StateView:
    return await service.get_state(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/timeline",
    response_model=api.TimelineResponse,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def get_timeline(
    session_id: SessionId,
    service: Service,
    timeline_id: TimelineQ = None,
    kinds: Annotated[str | None, Query(max_length=400, description="Comma-separated kinds")] = None,
    from_tick: Annotated[int | None, Query(ge=0)] = None,
    to_tick: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> api.TimelineResponse:
    kind_set = {k.strip() for k in kinds.split(",") if k.strip()} if kinds else None
    return await service.get_timeline(
        session_id, timeline_id, kinds=kind_set, from_tick=from_tick, to_tick=to_tick, limit=limit
    )


@router.get(
    "/mission-sessions/{session_id}/verify",
    response_model=api.VerifyResponse,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def verify(
    session_id: SessionId, service: Service, timeline_id: TimelineQ = None
) -> api.VerifyResponse:
    return await service.verify(session_id, timeline_id)


@router.post(
    "/mission-sessions/{session_id}/future-lens",
    response_model=FutureLensResult,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def future_lens(
    session_id: SessionId, body: api.FutureLensBody, service: Service
) -> FutureLensResult:
    return await service.future_lens(session_id, body)


@router.get(
    "/mission-sessions/{session_id}/black-box",
    response_model=BlackBoxReport,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def black_box(
    session_id: SessionId,
    service: Service,
    timeline_id: TimelineQ = None,
    counterfactuals: bool = True,
) -> BlackBoxReport:
    return await service.black_box(session_id, timeline_id, counterfactuals=counterfactuals)


@router.get(
    "/mission-sessions/{session_id}/trace",
    response_model=RootCauseTrace,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def trace(
    session_id: SessionId,
    service: Service,
    metric: Annotated[str, Query(min_length=1, max_length=96)],
    tick: Annotated[int | None, Query(ge=0)] = None,
    timeline_id: TimelineQ = None,
) -> RootCauseTrace:
    return await service.trace(session_id, timeline_id, metric, tick)


@router.post(
    "/mission-sessions/{session_id}/rewind",
    response_model=api.RewindResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def rewind(
    session_id: SessionId,
    body: api.RewindRequest,
    service: Service,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> api.RewindResponse:
    idem = _idem(idempotency_key, "branch", session_id, body, principal)
    result, replayed = await service.rewind(session_id, body, idem)
    _replayed(response, replayed)
    return result


@router.get(
    "/mission-sessions/{session_id}/profile",
    response_model=EngineeringProfile,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def profile(
    session_id: SessionId, service: Service, timeline_id: TimelineQ = None
) -> EngineeringProfile:
    return await service.profile(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/mission-dna",
    response_model=MissionDNA,
    tags=["internal"],
    dependencies=INTERNAL + EXPENSIVE_RL,
)
async def mission_dna(
    session_id: SessionId, service: Service, timeline_id: TimelineQ = None
) -> MissionDNA:
    return await service.mission_dna(session_id, timeline_id)


@router.post(
    "/mission-sessions/{session_id}/orion/explain",
    response_model=OrionResponse,
    tags=["orion"],
    dependencies=EXPENSIVE_RL,
)
async def orion_explain(
    session_id: SessionId, body: api.OrionRequest, service: Service
) -> OrionResponse:
    return await service.orion_explain(session_id, body)


# ------------------------------------------------------------------------------ science / nasa
def _evidence(row: Any) -> ScienceEvidence:
    ev = ScienceEvidence.model_validate({k: getattr(row, k) for k in ScienceEvidence.model_fields})
    # event visibility rule: never name an unforeseeable scenario event in static content
    hidden = unforeseeable_event_ids(list_scenarios())
    return ev.model_copy(update={"simulation_usage": redact_usage(ev.simulation_usage, hidden)})


@router.get(
    "/science/evidence",
    response_model=list[ScienceEvidence],
    tags=["science"],
    dependencies=DEFAULT_RL,
)
async def list_evidence(db: AsyncSession = Depends(get_db)) -> list[ScienceEvidence]:
    return [_evidence(r) for r in await svc_mod.evidence_list(db)]


@router.get(
    "/science/evidence/{evidence_id}",
    response_model=ScienceEvidence,
    tags=["science"],
    dependencies=DEFAULT_RL,
)
async def get_evidence(
    evidence_id: Annotated[str, Path(max_length=64, pattern=r"^[a-z0-9_]+$")],
    db: AsyncSession = Depends(get_db),
) -> ScienceEvidence:
    return _evidence(await svc_mod.evidence_get(db, evidence_id))


@router.get(
    "/nasa/sources", response_model=list[NASADataSource], tags=["nasa"], dependencies=DEFAULT_RL
)
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[NASADataSource]:
    return [
        NASADataSource.model_validate({k: getattr(r, k) for k in NASADataSource.model_fields})
        for r in await svc_mod.nasa_sources(db)
    ]


@router.get(
    "/nasa/space-weather/sep",
    response_model=DataEnvelope[list[SpaceWeatherEvent]],
    tags=["nasa"],
    dependencies=EXPENSIVE_RL,
)
async def sep_events(
    start: date, end: date, container: Container = Depends(get_container)
) -> DataEnvelope[list[SpaceWeatherEvent]]:
    if end < start or end - start > timedelta(days=31):
        raise InvalidRequestError("date window must be 0–31 days", code="bad_window")
    return await container.solar_provider.sep_events(start, end)


# ============================================================================== API v1 contract
# Frozen frontend-safe endpoints (docs/API_FREEZE_V1.md). Thin: validate → ContractService →
# read model. Tags start with "contract-".
ResourceId = Annotated[str, Path(max_length=32, pattern=r"^[a-z][a-z0-9_]*$")]
DecisionId = Annotated[str, Path(min_length=1, max_length=40)]


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    tags=["contract-bootstrap"],
    dependencies=DEFAULT_RL,
)
async def capabilities(container: Container = Depends(get_container)) -> CapabilitiesResponse:
    """API info, the public error codes and what this backend supports."""
    return CapabilitiesResponse(api=ApiInfo(), capabilities=build_capabilities(container.settings))


@router.get(
    "/mission-sessions/{session_id}/bootstrap",
    response_model=MissionBootstrap,
    tags=["contract-bootstrap"],
    dependencies=DEFAULT_RL,
)
async def bootstrap(session_id: SessionId, contract: Contract) -> MissionBootstrap:
    """Everything a client needs to start or resume a mission (no history)."""
    return await contract.bootstrap(session_id)


@router.get(
    "/mission-sessions/{session_id}/snapshot",
    response_model=MissionSnapshotView,
    tags=["contract-mission"],
    dependencies=DEFAULT_RL,
)
async def snapshot(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> MissionSnapshotView:
    """The authoritative current state of one timeline (default: the active one)."""
    return await contract.snapshot(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/decision-options",
    response_model=AvailableDecisionsView,
    tags=["contract-decisions"],
    dependencies=DEFAULT_RL,
)
async def decision_options(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> AvailableDecisionsView:
    return await contract.decision_options(session_id, timeline_id)


@router.post(
    "/mission-sessions/{session_id}/decision-commands",
    response_model=DecisionResultView,
    status_code=status.HTTP_201_CREATED,
    tags=["contract-decisions"],
    dependencies=DEFAULT_RL,
)
async def decision_command(
    session_id: SessionId,
    body: DecisionCommand,
    contract: Contract,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> DecisionResultView:
    """Submit a decision by ``option_id``; refused with 409 STALE_STATE when
    ``expected_state_version`` is not the current version."""
    idem = _idem(idempotency_key, "decision_command", session_id, body, principal)
    result, replayed = await contract.decision_command(session_id, body, idem)
    _replayed(response, replayed)
    return result


@router.post(
    "/mission-sessions/{session_id}/advance-commands",
    response_model=AdvanceResultView,
    tags=["contract-decisions"],
    dependencies=EXPENSIVE_RL,
)
async def advance_command(
    session_id: SessionId,
    body: AdvanceCommand,
    contract: Contract,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> AdvanceResultView:
    idem = _idem(idempotency_key, "advance_command", session_id, body, principal)
    result, replayed = await contract.advance_command(session_id, body, idem)
    _replayed(response, replayed)
    return result


@router.get(
    "/mission-sessions/{session_id}/objectives",
    response_model=ObjectiveOutlookView,
    tags=["contract-mission"],
    dependencies=DEFAULT_RL,
)
async def objectives(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> ObjectiveOutlookView:
    return await contract.objectives(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/radiation-budget",
    response_model=RadiationBudgetView,
    tags=["contract-mission"],
    dependencies=DEFAULT_RL,
)
async def radiation_budget(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> RadiationBudgetView:
    return await contract.radiation_budget(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/resources/{resource_id}",
    response_model=ResourceDetailView,
    tags=["contract-mission"],
    dependencies=DEFAULT_RL,
)
async def resource_detail(
    session_id: SessionId,
    resource_id: ResourceId,
    contract: Contract,
    timeline_id: TimelineQ = None,
) -> ResourceDetailView:
    return await contract.resource_detail(session_id, resource_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/completion",
    response_model=MissionCompletionView,
    tags=["contract-mission"],
    dependencies=DEFAULT_RL,
)
async def completion(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> MissionCompletionView:
    return await contract.completion(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/events",
    response_model=EventsPage,
    tags=["contract-realtime"],
    dependencies=DEFAULT_RL,
)
async def events(
    session_id: SessionId,
    contract: Contract,
    last_event_id: Annotated[str | None, Query(max_length=128)] = None,
    timeline_id: Annotated[
        str | None, Query(max_length=36, pattern=r"^[0-9a-fA-F\-]{1,36}$")
    ] = None,
    last_state_version: Annotated[int | None, Query(ge=0)] = None,
    last_seq: Annotated[int | None, Query(ge=0)] = None,
) -> EventsPage:
    """Retained realtime events after a cursor (REST equivalent of WebSocket resume)."""
    return await contract.events_after(
        session_id,
        last_event_id=last_event_id,
        timeline_id=timeline_id,
        last_state_version=last_state_version,
        last_seq=last_seq,
    )


@router.get(
    "/mission-sessions/{session_id}/history",
    response_model=MissionHistoryView,
    tags=["contract-mission"],
    dependencies=EXPENSIVE_RL,
)
async def history(
    session_id: SessionId,
    contract: Contract,
    timeline_id: TimelineQ = None,
    limit: Annotated[int, Query(ge=1, le=MAX_HISTORY_EVENTS)] = 500,
) -> MissionHistoryView:
    return await contract.history(session_id, timeline_id, limit)


@router.post(
    "/mission-sessions/{session_id}/future-lens/projections",
    response_model=FutureLensView,
    tags=["contract-analysis"],
    dependencies=EXPENSIVE_RL,
)
async def future_lens_projections(
    session_id: SessionId, body: FutureLensCommand, contract: Contract
) -> FutureLensView:
    """What-if projections; never changes mission state."""
    return await contract.future_lens_projection(session_id, body)


@router.get(
    "/mission-sessions/{session_id}/black-box/summary",
    response_model=BlackBoxView,
    tags=["contract-analysis"],
    dependencies=EXPENSIVE_RL,
)
async def black_box_summary(
    session_id: SessionId,
    contract: Contract,
    timeline_id: TimelineQ = None,
    counterfactuals: bool = True,
) -> BlackBoxView:
    return await contract.black_box_summary(
        session_id, timeline_id, counterfactuals=counterfactuals
    )


@router.get(
    "/mission-sessions/{session_id}/timelines",
    response_model=TimelineTreeView,
    tags=["contract-timelines"],
    dependencies=DEFAULT_RL,
)
async def timelines(session_id: SessionId, contract: Contract) -> TimelineTreeView:
    return await contract.timeline_tree(session_id)


@router.get(
    "/mission-sessions/{session_id}/rewind-points",
    response_model=RewindPointsView,
    tags=["contract-timelines"],
    dependencies=DEFAULT_RL,
)
async def rewind_points(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> RewindPointsView:
    return await contract.rewind_points(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/rewind-points/{decision_id}/preview",
    response_model=ForkPreviewView,
    tags=["contract-timelines"],
    dependencies=EXPENSIVE_RL,
)
async def rewind_preview(
    session_id: SessionId,
    decision_id: DecisionId,
    contract: Contract,
    timeline_id: TimelineQ = None,
) -> ForkPreviewView:
    """What replacing a decision would keep and discard; creates nothing."""
    return await contract.rewind_preview(session_id, decision_id, timeline_id)


@router.post(
    "/mission-sessions/{session_id}/timeline-branches",
    response_model=TimelineChangeView,
    status_code=status.HTTP_201_CREATED,
    tags=["contract-timelines"],
    dependencies=EXPENSIVE_RL,
)
async def timeline_branch(
    session_id: SessionId,
    body: BranchCommand,
    contract: Contract,
    response: Response,
    principal: Principal,
    idempotency_key: IdempotencyKey = None,
) -> TimelineChangeView:
    """Create an alternate timeline; the source timeline is never modified."""
    idem = _idem(idempotency_key, "timeline_branch", session_id, body, principal)
    result, replayed = await contract.branch_command(session_id, body, idem)
    _replayed(response, replayed)
    return result


@router.get(
    "/mission-sessions/{session_id}/engineering-profile",
    response_model=EngineeringProfileView,
    tags=["contract-analysis"],
    dependencies=EXPENSIVE_RL,
)
async def engineering_profile(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> EngineeringProfileView:
    return await contract.engineering_profile(session_id, timeline_id)


@router.get(
    "/mission-sessions/{session_id}/mission-dna/share",
    response_model=MissionDNAView,
    tags=["contract-analysis"],
    dependencies=EXPENSIVE_RL,
)
async def mission_dna_share(
    session_id: SessionId, contract: Contract, timeline_id: TimelineQ = None
) -> MissionDNAView:
    """Share-safe Mission DNA: no session, timeline or participant ids and no seed."""
    return await contract.mission_dna_share(session_id, timeline_id)


@router.get(
    "/science/claims",
    response_model=list[ScienceClaimView],
    tags=["contract-science"],
    dependencies=DEFAULT_RL,
)
async def science_claims(db: AsyncSession = Depends(get_db)) -> list[ScienceClaimView]:
    return [build_claim(_evidence(r)) for r in await svc_mod.evidence_list(db)]


@router.get(
    "/science/claims/{claim_id}",
    response_model=ScienceClaimView,
    tags=["contract-science"],
    dependencies=DEFAULT_RL,
)
async def science_claim(
    claim_id: Annotated[str, Path(max_length=64, pattern=r"^[a-z0-9_]+$")],
    db: AsyncSession = Depends(get_db),
) -> ScienceClaimView:
    return build_claim(_evidence(await svc_mod.evidence_get(db, claim_id)))
