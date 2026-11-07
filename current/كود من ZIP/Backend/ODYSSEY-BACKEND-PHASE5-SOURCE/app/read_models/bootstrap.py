"""Mission bootstrap: one response that initialises a client.

API and contract versions, capability flags, the static scenario description (phases,
objectives, outcome tiers, crew, subsystems, components, resources), the session, the current
snapshot, the realtime connection details and the endpoint map. No history is included.
"""

from __future__ import annotations

from pydantic import Field

from app import __version__
from app.core.config import Settings
from app.core.errors import PUBLIC_CODES
from app.read_models.common import READ_MODEL_VERSION, View
from app.read_models.mission import MissionSnapshotView, TimelineRef
from app.read_models.resources import resource_defs
from app.read_models.systems import MODE_ORDER
from app.read_models.visibility import entered_phases, phase_is_visible
from app.realtime.contract import REALTIME_CONTRACT
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

API_VERSION = "v1"


class ApiInfo(View):
    api_version: str = API_VERSION
    server_version: str = __version__
    read_model_version: int = READ_MODEL_VERSION
    realtime_contract: str = REALTIME_CONTRACT
    error_codes: list[str] = Field(default_factory=lambda: sorted(PUBLIC_CODES))


class CapabilitiesView(View):
    """What the backend supports. Flags describe backend support, not frontend features."""

    future_lens: bool
    future_lens_omniscient: bool
    black_box: bool
    rewind: bool
    orion: bool
    orion_ai_provider: bool
    multiplayer_ready: bool
    science_evidence: bool
    radiation_budget: bool
    mission_dna: bool
    engineering_profile: bool
    idempotency: bool
    optimistic_concurrency: bool
    realtime_resume: bool
    nasa_live_data: bool
    internal_endpoints: bool


CAPABILITY_DESCRIPTIONS: dict[str, str] = {
    "future_lens": "what-if projections that never change mission state",
    "future_lens_omniscient": "omniscient projections (reveal hidden events); off unless the "
    "server switch ODYSSEY_FUTURE_LENS_OMNISCIENT_ENABLED is set",
    "black_box": "post-mission analysis with counterfactual root causes",
    "rewind": "fork a timeline before any decision; the source timeline is never modified",
    "orion": "grounded explanations (degrades to a grounded mock without an AI provider)",
    "orion_ai_provider": "an external AI provider is configured for ORION",
    "multiplayer_ready": "participants, roles and permissions are modelled; multiplayer "
    "sessions are not offered as a product feature yet",
    "science_evidence": "evidence and provenance behind scientific values",
    "internal_endpoints": "raw engineering endpoints (tag 'internal'); not part of the frozen "
    "contract and disabled in production because they expose engine internals and the seed",
    "radiation_budget": "per scenario: the scenario defines a mission dose limit",
    "mission_dna": "share-safe, comparable mission fingerprints",
    "engineering_profile": "engineering-style profile from decisions (provisional weights)",
    "idempotency": "Idempotency-Key on mutation endpoints",
    "optimistic_concurrency": "expected_state_version on commands (409 STALE_STATE)",
    "realtime_resume": "WebSocket and REST resume from the last event or state version",
    "nasa_live_data": "live NASA data (otherwise bundled fixtures)",
}


def build_capabilities(settings: Settings, *, radiation_budget: bool = True) -> CapabilitiesView:
    return CapabilitiesView(
        future_lens=True,
        future_lens_omniscient=settings.future_lens_omniscient_enabled,
        black_box=True,
        rewind=True,
        orion=True,
        orion_ai_provider=settings.ai_provider != "mock",
        multiplayer_ready=False,
        science_evidence=True,
        radiation_budget=radiation_budget,
        mission_dna=True,
        engineering_profile=True,
        idempotency=True,
        optimistic_concurrency=True,
        realtime_resume=True,
        nasa_live_data=settings.nasa_remote_enabled and settings.nasa_api_key is not None,
        internal_endpoints=settings.internals_exposed,
    )


class CapabilitiesResponse(View):
    api: ApiInfo
    capabilities: CapabilitiesView
    descriptions: dict[str, str] = Field(default_factory=lambda: dict(CAPABILITY_DESCRIPTIONS))


class PhaseDef(View):
    """One phase of the scenario, in order. A phase that is withheld until entered (phase
    visibility rule, app/read_models/visibility.py) keeps its position with ``id: null``."""

    id: str | None
    kind: str
    withheld: bool = False


class ObjectiveDef(View):
    id: str
    category: str
    required: bool
    evaluated: str
    message_key: str


class OutcomeDef(View):
    code: str
    tier: str | None
    message_key: str


class CrewDef(View):
    id: str
    role: str


class SubsystemDef(View):
    id: str
    label: str
    system: str
    priority: int
    modes: list[str]


class ComponentDef(View):
    id: str
    maintenance_ticks: int


class ResourceDefView(View):
    id: str
    label: str
    metric: str
    unit: str


class ScenarioView(View):
    mission_id: str
    scenario_id: str
    scenario_version: str
    content_hash: str
    provisional: bool
    title: str
    tick_hours: float
    max_ticks: int
    phases: list[PhaseDef]
    objectives: list[ObjectiveDef]
    outcomes: list[OutcomeDef]
    crew: list[CrewDef]
    subsystems: list[SubsystemDef]
    components: list[ComponentDef]
    resources: list[ResourceDefView]
    dose_limit_msv: float | None


class ParticipantInfo(View):
    id: str
    handle: str
    role: str


class SessionInfo(View):
    session_id: str
    status: str
    active_timeline_id: str | None
    participants: list[ParticipantInfo]
    timelines: list[TimelineRef]
    future_lens_requests: int


class RealtimeInfo(View):
    path: str
    contract: str = REALTIME_CONTRACT
    resume_query: list[str] = Field(
        default_factory=lambda: ["last_event_id", "timeline_id", "last_state_version", "last_seq"]
    )
    events_path: str


class MissionBootstrap(View):
    api: ApiInfo
    capabilities: CapabilitiesView
    scenario: ScenarioView
    session: SessionInfo
    snapshot: MissionSnapshotView
    realtime: RealtimeInfo
    endpoints: dict[str, str]


ENDPOINTS: tuple[str, ...] = (
    "bootstrap",
    "snapshot",
    "decision-options",
    "decision-commands",
    "advance-commands",
    "objectives",
    "radiation-budget",
    "events",
    "history",
    "timelines",
    "rewind-points",
    "timeline-branches",
    "future-lens/projections",
    "black-box/summary",
    "completion",
    "engineering-profile",
    "mission-dna/share",
)


def endpoint_map(session_id: str) -> dict[str, str]:
    base = f"/api/v1/mission-sessions/{session_id}"
    out = {name.replace("/", "_").replace("-", "_"): f"{base}/{name}" for name in ENDPOINTS}
    out["resources"] = f"{base}/resources/{{resource_id}}"
    out["science_claims"] = "/api/v1/science/claims"
    out["capabilities"] = "/api/v1/capabilities"
    return out


def build_scenario_view(
    engine: SimulationEngine,
    *,
    content_hash: str,
    provisional: bool,
    state: MissionState | None,
) -> ScenarioView:
    """Static scenario description. ``state`` (the session's head state) decides which
    withheld phases have been entered and may be named."""
    sc = engine.scenario
    entered = entered_phases(state)
    return ScenarioView(
        mission_id=sc.mission_id,
        scenario_id=sc.id,
        scenario_version=sc.version,
        content_hash=content_hash,
        provisional=provisional,
        title=sc.title,
        tick_hours=sc.time.tick_hours,
        max_ticks=sc.time.max_ticks,
        phases=[
            PhaseDef(id=p.id, kind=p.kind)
            if phase_is_visible(engine, p.id, entered)
            else PhaseDef(id=None, kind=p.kind, withheld=True)
            for p in sc.phases
        ],
        objectives=[
            ObjectiveDef(
                id=o.id,
                category=o.effective_category,
                required=o.required,
                evaluated="at_mission_end" if o.evaluate == "at_end" else "continuously",
                message_key=f"objective.{o.id}",
            )
            for o in sc.objectives
        ],
        outcomes=[
            OutcomeDef(code=r.code, tier=r.effective_tier, message_key=f"outcome.{r.code}")
            for r in sc.outcomes
        ],
        crew=[CrewDef(id=c.id, role=c.role.value) for c in sc.crew],
        subsystems=[
            SubsystemDef(
                id=c.id,
                label=c.label,
                system=c.system,
                priority=c.priority,
                modes=[m for m in MODE_ORDER if m in {x.value for x in c.mode_factors}],
            )
            for c in sc.power.consumers
        ],
        components=[
            ComponentDef(id=c.id, maintenance_ticks=c.maintenance_ticks)
            for c in sc.degradation.components
        ],
        resources=[
            ResourceDefView(
                id=r.id,
                label=r.label,
                metric=r.metric,
                unit=engine.metrics.spec(r.metric).unit,
            )
            for r in resource_defs(engine)
        ],
        dose_limit_msv=sc.radiation.dose_limit_msv,
    )
