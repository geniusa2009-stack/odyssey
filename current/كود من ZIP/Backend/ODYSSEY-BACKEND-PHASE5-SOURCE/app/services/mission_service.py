"""Mission orchestration: the only place where API, persistence, engine and realtime meet.

Transaction boundary = one public method. The realtime bus is notified only *after* commit, so
subscribers never observe uncommitted state. CPU-heavy engine work (Future Lens, replays) runs
in a worker thread so the event loop stays responsive.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import anyio
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.ai.context import ContextFact, build_context
from app.ai.orion import OrionResponse, ORIONService
from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    DecisionRejected,
    ForbiddenError,
    IntegrityFailure,
    InvalidRequestError,
    NotFoundError,
)
from app.core.logging import (
    decision_id_var,
    scenario_version_var,
    session_id_var,
    simulation_run_id_var,
    state_version_var,
    timeline_id_var,
)
from app.db import models as m
from app.read_models.analysis import decision_entry
from app.read_models.mission import build_hud, build_outcome
from app.read_models.objectives import build_objectives
from app.read_models.radiation import build_radiation
from app.read_models.visibility import compute_phase_visibility
from app.realtime.bus import EventBus, session_channel
from app.realtime.contract import Cause, RealtimeEvent, aux_event, build_transition
from app.repositories import missions as repo
from app.schemas import api
from app.science.evidence import default_registry
from app.services import idempotency
from app.services.engine_registry import EngineRegistry
from app.services.idempotency import IdempotencyContext
from app.services.permissions import (
    AllowAllPolicy,
    MissionAction,
    MissionRole,
    PermissionPolicy,
)
from app.simulation.analysis.black_box import BlackBoxReport, build_black_box
from app.simulation.analysis.future_lens import FutureLens, FutureLensRequest, FutureLensResult
from app.simulation.analysis.mission_dna import MissionDNA, build_mission_dna
from app.simulation.analysis.profile import EngineeringProfile, build_profile
from app.simulation.analysis.reconstruct import (
    MissionRecord,
    counterfactual_factory,
    reconstruct,
)
from app.simulation.analysis.root_cause import RootCauseTrace, trace_root_cause
from app.simulation.domain.decisions import DECISION_TYPES, DecisionInput
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import (
    DecisionRejectedError,
    DecisionResult,
    MissionConcludedError,
    SimulationEngine,
)
from app.simulation.engine.metrics import UnknownMetricError
from app.simulation.replay.ledger import (
    GENESIS_HASH,
    DecisionRecord,
    LedgerIntegrityError,
    record_decision,
    verify_chain,
)
from app.simulation.replay.replay import (
    ReplayDecision,
    ReplayDivergenceError,
    replay,
)
from app.simulation.replay.timeline import TimelineError, plan_fork
from app.simulation.scenarios.schema import ScenarioDefinition
from app.telemetry import runtime_stats

log = logging.getLogger(__name__)
R = TypeVar("R", bound=BaseModel)

SUMMARY_METRICS = (
    "power.battery_soc",
    "power.generation_kw",
    "power.demand_kw",
    "thermal.habitat_temp_c",
    "life_support.oxygen_days",
    "life_support.co2_ppm",
    "life_support.water_days",
    "food.food_days",
    "crew.min_health",
    "crew.max_dose_msv",
    "science.points",
    "comms.data_downlinked_mb",
    "risk.mission",
)
MAX_EVENTS_IN_RESPONSE = 500


@dataclass(frozen=True, slots=True)
class Loaded:
    session: m.MissionSession
    timeline: m.MissionTimeline
    scenario_row: m.MissionScenario
    engine: SimulationEngine


@dataclass(slots=True)
class _Transition:
    session_id: str
    timeline: m.MissionTimeline
    prev_version: int | None
    state: MissionState
    engine: SimulationEngine
    events: Sequence[MissionEvent]
    cause: Cause
    from_tick: int
    decision: dict[str, Any] | None = None
    timeline_change: dict[str, Any] | None = None


@dataclass(slots=True)
class _Aux:
    etype: Any
    session_id: str
    timeline: m.MissionTimeline
    tick: int
    tick_hours: float
    payload: dict[str, Any]


@dataclass(slots=True)
class DecisionOutcome:
    """Result of the shared decision core (before the caller builds its response)."""

    loaded: Loaded
    record: DecisionRecord
    result: DecisionResult
    prev_version: int


@dataclass(slots=True)
class AdvanceOutcome:
    loaded: Loaded
    before: MissionState
    final: MissionState
    events: list[MissionEvent]
    ticks_run: int
    prev_version: int


@dataclass(slots=True)
class BranchOutcome:
    loaded: Loaded
    child: m.MissionTimeline
    state: MissionState
    alternative: DecisionRecord | None
    fork_tick: int
    replaced_decision_id: str
    activated: bool


class MissionService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        engines: EngineRegistry,
        bus: EventBus,
        orion: ORIONService,
        policy: PermissionPolicy | None = None,
        *,
        realtime: bool = True,
        game_access: bool = False,
    ) -> None:
        self.db = db
        # Used by the game backend (odyssey.game.v1): realtime=False produces no v1 realtime
        # rows/messages; game_access=True can load game-managed simulation sessions, which the
        # v1 API never sees (they answer session_not_found there).
        self.realtime = realtime
        self.game_access = game_access
        self.policy = policy or AllowAllPolicy()
        self.settings = settings
        self.engines = engines
        self.bus = bus
        self.orion = orion
        self._transitions: list[_Transition] = []
        self._aux: list[_Aux] = []
        self.published: list[RealtimeEvent] = []

    # ================================================================== helpers
    def _summary(self, engine: SimulationEngine, state: MissionState) -> dict[str, float]:
        return {k: engine.metrics.value(k, state) for k in SUMMARY_METRICS}

    @staticmethod
    def scenario_summary(row: m.MissionScenario) -> api.ScenarioSummary:
        sc = ScenarioDefinition.model_validate(row.definition)
        return api.ScenarioSummary(
            id=row.id,
            scenario_key=row.scenario_key,
            version=row.version,
            content_hash=row.content_hash,
            provisional=row.provisional,
            title=sc.title,
            tick_hours=sc.time.tick_hours,
            max_ticks=sc.time.max_ticks,
            # phase visibility rule: phases withheld until entered are not listed here (this
            # view is session-independent; the bootstrap lists them with id null)
            phases=[
                p.id
                for p in sc.phases
                if p.id not in compute_phase_visibility(sc).withheld_until_entered
            ],
            decision_types=list(DECISION_TYPES),
            subsystems=[c.id for c in sc.power.consumers],
            components=[c.id for c in sc.degradation.components],
            opportunities=[o.id for o in sc.science.opportunities],
            crew=[{"id": c.id, "role": c.role.value} for c in sc.crew],
        )

    @staticmethod
    def timeline_view(t: m.MissionTimeline) -> api.TimelineView:
        return api.TimelineView(
            id=t.id,
            parent_timeline_id=t.parent_timeline_id,
            fork_sequence=t.fork_sequence,
            fork_tick=t.fork_tick,
            label=t.label,
            status=t.status,
            head_tick=t.head_tick,
            head_sequence=t.head_sequence,
            head_state_hash=t.head_state_hash,
            state_version=t.version,
            created_at=t.created_at,
        )

    @staticmethod
    def record_view(r: DecisionRecord) -> api.DecisionRecordView:
        return api.DecisionRecordView(
            decision_id=r.decision_id,
            timeline_id=r.timeline_id,
            sequence=r.sequence,
            tick=r.tick,
            phase=r.phase,
            decision_type=r.decision_type,
            inputs=r.inputs,
            affected_systems=list(r.affected_systems),
            state_before_hash=r.state_before_hash,
            state_after_hash=r.state_after_hash,
            prev_record_hash=r.prev_record_hash,
            record_hash=r.record_hash,
            metadata=r.metadata,
        )

    async def _load(
        self, session_id: str, timeline_id: str | None, *, lock: bool = False
    ) -> Loaded:
        sess = await repo.get_session_row(self.db, session_id, allow_game_managed=self.game_access)
        tid = timeline_id or sess.active_timeline_id
        if tid is None:
            raise IntegrityFailure("session has no active timeline", code="no_active_timeline")
        timeline = await repo.get_timeline_row(self.db, session_id, tid, lock=lock)
        scenario_row = await self.db.get(m.MissionScenario, sess.scenario_id)
        if scenario_row is None:
            raise IntegrityFailure("session scenario missing", code="scenario_missing")
        engine = self.engines.get(scenario_row.content_hash, scenario_row.definition)
        session_id_var.set(session_id)
        timeline_id_var.set(timeline.id)
        state_version_var.set(timeline.version)
        scenario_version_var.set(scenario_row.version)
        return Loaded(sess, timeline, scenario_row, engine)

    @staticmethod
    def check_version(
        tl: m.MissionTimeline,
        expected_state_version: int | None,
        expected_sequence: int | None = None,
    ) -> None:
        """Optimistic concurrency: refuse commands based on an older state."""
        details = {
            "timeline_id": tl.id,
            "head_tick": tl.head_tick,
            "head_sequence": tl.head_sequence,
        }
        if expected_state_version is not None and expected_state_version != tl.version:
            raise ConflictError(
                "the timeline has changed since the state you based this request on",
                code="stale_state",
                details={**details, "expected_state_version": expected_state_version},
                state_version=tl.version,
            )
        if expected_sequence is not None and expected_sequence != tl.head_sequence:
            raise ConflictError(
                "timeline has advanced since you last read it",
                code="stale_sequence",
                details=details,
                state_version=tl.version,
            )

    def _snapshot(self, timeline_id: str, state: MissionState, reason: str) -> None:
        self.db.add(
            m.MissionSnapshot(
                timeline_id=timeline_id,
                tick=state.tick,
                decisions_applied=state.decisions_applied,
                state=state.model_dump(mode="json"),
                state_hash=state.state_hash(),
                reason=reason,
            )
        )

    def _events(self, session_id: str, timeline_id: str, events: Sequence[MissionEvent]) -> None:
        for e in events:
            self.db.add(
                m.MissionEvent(
                    session_id=session_id,
                    timeline_id=timeline_id,
                    event_id=e.id,
                    tick=e.tick,
                    kind=e.kind.value,
                    key=e.key,
                    severity=e.severity.value if e.severity else None,
                    data=e.model_dump(mode="json")["data"],
                )
            )

    def _run(
        self,
        session: m.MissionSession,
        timeline_id: str,
        kind: str,
        from_tick: int,
        to_tick: int,
        started: float,
        state_hash: str | None,
    ) -> str:
        run_id = str(uuid.uuid4())
        simulation_run_id_var.set(run_id)
        duration_ms = (time.perf_counter() - started) * 1000
        self.db.add(
            m.SimulationRun(
                id=run_id,
                session_id=session.id,
                timeline_id=timeline_id,
                kind=kind,
                from_tick=from_tick,
                to_tick=to_tick,
                seed=session.seed,
                duration_ms=duration_ms,
                state_hash_out=state_hash,
            )
        )
        runtime_stats.record(kind, duration_ms, to_tick - from_tick)
        log.info(
            "simulation_run",
            extra={
                "event_type": kind,
                "duration_ms": round(duration_ms, 3),
                "ticks": to_tick - from_tick,
            },
        )
        return run_id

    # ================================================================== realtime
    def _stage(
        self,
        ld: Loaded,
        timeline: m.MissionTimeline,
        prev_version: int | None,
        state: MissionState,
        events: Sequence[MissionEvent],
        cause: Cause,
        from_tick: int,
        *,
        decision: DecisionRecord | None = None,
        timeline_change: dict[str, Any] | None = None,
    ) -> None:
        if not self.realtime:
            return
        dpayload = None
        if decision is not None:
            dpayload = decision_entry(decision, timeline.id).model_dump(mode="json")
        self._transitions.append(
            _Transition(
                session_id=ld.session.id,
                timeline=timeline,
                prev_version=prev_version,
                state=state,
                engine=ld.engine,
                events=events,
                cause=cause,
                from_tick=from_tick,
                decision=dpayload,
                timeline_change=timeline_change,
            )
        )

    def _stage_aux(self, ld: Loaded, etype: Any, tick: int, payload: dict[str, Any]) -> None:
        if not self.realtime:
            return
        self._aux.append(
            _Aux(
                etype=etype,
                session_id=ld.session.id,
                timeline=ld.timeline,
                tick=tick,
                tick_hours=ld.engine.scenario.time.tick_hours,
                payload=payload,
            )
        )

    async def _write_transitions(self) -> list[RealtimeEvent]:
        """After a flush: build envelopes with the new versions and add the retained rows."""
        out: list[RealtimeEvent] = []
        retain = self.settings.realtime_retained_versions
        for tr in self._transitions:
            version = tr.timeline.version
            outcome = None
            if tr.state.status == MissionStatus.CONCLUDED and tr.cause != "session_created":
                o = build_outcome(tr.engine, tr.state)
                outcome = o.model_dump(mode="json") if o else None
            change = None
            if tr.timeline_change is not None:
                change = {**tr.timeline_change, "state_version": version}
            envelopes = build_transition(
                session_id=tr.session_id,
                timeline_id=tr.timeline.id,
                state_version=version,
                prev_state_version=tr.prev_version,
                tick=tr.state.tick,
                tick_hours=tr.engine.scenario.time.tick_hours,
                cause=tr.cause,
                from_tick=tr.from_tick,
                phase=tr.state.phase,
                status=tr.state.status.value,
                state_hash=tr.state.state_hash(),
                engine_events=tr.events,
                hud=build_hud(tr.engine, tr.state).model_dump(mode="json"),
                decision=tr.decision,
                timeline_change=change,
                outcome=outcome,
            )
            for ev in envelopes:
                self.db.add(
                    m.MissionRealtimeEvent(
                        session_id=ev.session_id,
                        timeline_id=ev.timeline_id,
                        state_version=ev.state_version,
                        seq=ev.seq,
                        event_id=ev.event_id,
                        type=ev.type,
                        envelope=ev.model_dump(mode="json"),
                    )
                )
            await self.db.execute(
                delete(m.MissionRealtimeEvent).where(
                    m.MissionRealtimeEvent.timeline_id == tr.timeline.id,
                    m.MissionRealtimeEvent.state_version <= version - retain,
                )
            )
            state_version_var.set(version)
            out.extend(envelopes)
        for aux in self._aux:
            out.append(
                aux_event(
                    etype=aux.etype,
                    session_id=aux.session_id,
                    timeline_id=aux.timeline.id,
                    state_version=aux.timeline.version,
                    tick=aux.tick,
                    tick_hours=aux.tick_hours,
                    payload=aux.payload,
                )
            )
        return out

    def _discard_staged(self) -> None:
        self._transitions.clear()
        self._aux.clear()

    async def _flush(self) -> None:
        """Flush with the same conflict mapping as commit (unique/version violations → 409)."""
        try:
            await self.db.flush()
        except StaleDataError as exc:
            await self.db.rollback()
            self._discard_staged()
            raise ConflictError(
                "the timeline was modified concurrently; refresh and retry",
                code="concurrent_modification",
            ) from exc
        except IntegrityError as exc:
            await self.db.rollback()
            self._discard_staged()
            raise ConflictError("conflicting write; retry", code="write_conflict") from exc

    async def _commit_and_publish(self, *, record: Callable[[], None] | None = None) -> None:
        """Flush, write the realtime log (and idempotency record), commit, then publish."""
        try:
            await self.db.flush()
            envelopes = await self._write_transitions()
            if record is not None:
                record()
            await self.db.commit()
        except StaleDataError as exc:
            await self.db.rollback()
            self._transitions.clear()
            self._aux.clear()
            raise ConflictError(
                "the timeline was modified concurrently; refresh and retry",
                code="concurrent_modification",
            ) from exc
        except IntegrityError as exc:
            await self.db.rollback()
            self._transitions.clear()
            self._aux.clear()
            raise ConflictError("conflicting write; retry", code="write_conflict") from exc
        self._transitions.clear()
        self._aux.clear()
        for message in envelopes:
            try:
                await self.bus.publish(session_channel(message.session_id), message)
            except Exception:  # realtime is best-effort; DB is the source of truth
                log.warning("realtime_publish_failed", extra={"error_code": "publish_failed"})
        self.published.extend(envelopes)
        if envelopes:
            log.info(
                "realtime_published",
                extra={"event_id": envelopes[-1].event_id, "events_published": len(envelopes)},
            )

    async def _idempotent(
        self,
        idem: IdempotencyContext | None,
        scope: str,
        session_key: str,
        model: type[R],
        status_code: int,
        run: Callable[[Callable[[R], Callable[[], None]] | None], Awaitable[R]],
    ) -> tuple[R, bool]:
        """Run a mutation once per idempotency key. Returns ``(response, replayed)``.

        ``run`` receives ``make_record`` (or ``None`` without a key): calling
        ``make_record(response)`` returns the callback that adds the idempotency row; the
        mutation passes it to :meth:`_commit_and_publish` so the row commits atomically.
        """
        if idem is None:
            return await run(None), False
        stored = await idempotency.find(self.db, idem, scope, session_key)
        if stored is not None:
            log.info("idempotent_replay", extra={"idempotent_replay": True})
            return model.model_validate(stored.response), True

        def make_record(response: R) -> Callable[[], None]:
            def add() -> None:
                idempotency.record(
                    self.db, idem, scope, session_key, status_code, response.model_dump(mode="json")
                )

            return add

        try:
            return await run(make_record), False
        except ConflictError:
            # A retry racing its own original request loses the row lock and then fails the
            # version check (stale_state) or the unique insert (write_conflict). If the
            # original has committed meanwhile, the retry gets the original response.
            stored = await idempotency.find(self.db, idem, scope, session_key)
            if stored is None:
                raise
            log.info("idempotent_replay", extra={"idempotent_replay": True})
            return model.model_validate(stored.response), True

    # ================================================================== catalogue
    async def list_missions(self) -> list[api.MissionView]:
        missions = (
            await self.db.execute(
                select(m.Mission).where(m.Mission.managed_by.is_(None)).order_by(m.Mission.id)
            )
        ).scalars()
        out = []
        for mission in missions:
            rows = (
                (
                    await self.db.execute(
                        select(m.MissionScenario)
                        .where(m.MissionScenario.mission_id == mission.id)
                        .order_by(m.MissionScenario.created_at)
                    )
                )
                .scalars()
                .all()
            )
            out.append(
                api.MissionView(
                    id=mission.id,
                    title=mission.title,
                    description=mission.description,
                    scenarios=[self.scenario_summary(r) for r in rows],
                )
            )
        return out

    async def get_mission(self, mission_id: str) -> api.MissionView:
        for mission in await self.list_missions():
            if mission.id == mission_id:
                return mission
        raise NotFoundError(f"mission '{mission_id}' not found", code="mission_not_found")

    async def metric_catalog(self, mission_id: str) -> list[api.MetricInfo]:
        mission = await self.get_mission(mission_id)
        if not mission.scenarios:
            raise NotFoundError("mission has no scenario", code="scenario_not_found")
        row = await self.db.get(m.MissionScenario, mission.scenarios[-1].id)
        assert row is not None
        engine = self.engines.get(row.content_hash, row.definition)
        out: list[api.MetricInfo] = []
        for name in engine.metrics.names():
            spec = engine.metrics.spec(name)
            sev = (
                None
                if spec.severity is None
                else {
                    "direction": spec.severity.direction,
                    "nominal": spec.severity.nominal,
                    "critical": spec.severity.critical,
                }
            )
            out.append(api.MetricInfo(name=name, unit=spec.unit, label=spec.label, severity=sev))
        return out

    # ================================================================== lifecycle
    async def create_session(
        self, req: api.CreateSessionRequest, idem: IdempotencyContext | None = None
    ) -> tuple[api.SessionView, bool]:
        async def run(make_record: Any) -> api.SessionView:
            session_id = await self._create_session(req)
            view = await self.get_session(session_id)
            await self._commit_and_publish(record=make_record(view) if make_record else None)
            return view

        return await self._idempotent(idem, "create_session", "-", api.SessionView, 201, run)

    async def _create_session(self, req: api.CreateSessionRequest) -> str:
        stmt = (
            select(m.MissionScenario)
            .join(m.Mission, m.Mission.id == m.MissionScenario.mission_id)
            .where(m.MissionScenario.mission_id == req.mission_id, m.Mission.managed_by.is_(None))
        )
        if req.scenario_version:
            stmt = stmt.where(m.MissionScenario.version == req.scenario_version)
        scenario_row = (
            await self.db.execute(stmt.order_by(m.MissionScenario.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        if scenario_row is None:
            raise NotFoundError("no scenario for that mission/version", code="scenario_not_found")
        seed = req.seed if req.seed is not None else secrets.randbelow(api.MAX_SEED)
        return await self.create_session_for(scenario_row, seed, req.participants)

    async def create_session_for(
        self,
        scenario_row: m.MissionScenario,
        seed: int,
        participants: Sequence[api.ParticipantIn] = (),
        *,
        managed_by: str | None = None,
    ) -> str:
        """Create a session (main timeline + initial snapshot) for a pinned scenario row.

        ``managed_by='game'`` marks a simulation session owned by the game backend (hidden from
        the v1 API); v1 session creation always passes ``None``."""
        engine = self.engines.get(scenario_row.content_hash, scenario_row.definition)
        state = engine.initial_state(seed)

        started = time.perf_counter()
        session_id, timeline_id = str(uuid.uuid4()), str(uuid.uuid4())
        sess = m.MissionSession(
            id=session_id,
            scenario_id=scenario_row.id,
            seed=seed,
            status="active",
            active_timeline_id=timeline_id,
            managed_by=managed_by,
        )
        self.db.add(sess)
        await self._flush()
        timeline = m.MissionTimeline(
            id=timeline_id,
            session_id=session_id,
            label="main",
            head_tick=0,
            head_sequence=0,
            head_state_hash=state.state_hash(),
            head_record_hash=GENESIS_HASH,
        )
        self.db.add(timeline)
        await self._flush()
        self._snapshot(timeline_id, state, "initial")
        for p in participants:
            self.db.add(
                m.MissionParticipant(
                    id=str(uuid.uuid4()), session_id=session_id, handle=p.handle, role=p.role.value
                )
            )
        self._run(sess, timeline_id, "initialize", 0, 0, started, state.state_hash())
        session_id_var.set(session_id)
        ld = Loaded(sess, timeline, scenario_row, engine)
        self._stage(ld, timeline, None, state, [], "session_created", 0)
        await self._flush()
        return session_id

    async def get_session(self, session_id: str) -> api.SessionView:
        sess = await repo.get_session_row(self.db, session_id, allow_game_managed=self.game_access)
        scenario_row = await self.db.get(m.MissionScenario, sess.scenario_id)
        assert scenario_row is not None
        participants = await repo.participants(self.db, session_id)
        timelines = await repo.list_timelines(self.db, session_id)
        return api.SessionView(
            id=sess.id,
            mission_id=scenario_row.mission_id,
            scenario=self.scenario_summary(scenario_row),
            seed=sess.seed if self.settings.internals_exposed else None,
            status=sess.status,
            active_timeline_id=sess.active_timeline_id,
            future_lens_requests=sess.future_lens_requests,
            created_at=sess.created_at,
            participants=[
                api.ParticipantView(id=p.id, handle=p.handle, role=p.role, joined_at=p.joined_at)
                for p in participants
            ],
            timelines=[self.timeline_view(t) for t in timelines],
        )

    async def get_state(self, session_id: str, timeline_id: str | None) -> api.StateView:
        ld = await self._load(session_id, timeline_id)
        state = await repo.head_state(self.db, ld.timeline)
        return api.StateView(
            session_id=session_id,
            timeline_id=ld.timeline.id,
            tick=state.tick,
            elapsed_hours=state.tick * ld.engine.scenario.time.tick_hours,
            phase=state.phase,
            status=state.status.value,
            state_hash=state.state_hash(),
            state_version=ld.timeline.version,
            metrics=self._summary(ld.engine, state),
            state=state,
        )

    async def _authorize(
        self,
        session_id: str,
        participant_id: str | None,
        action: MissionAction,
        decision_type: str | None = None,
    ) -> None:
        role: MissionRole | None = None
        if participant_id is not None:
            row = await self.db.get(m.MissionParticipant, participant_id)
            if row is None or row.session_id != session_id:
                raise InvalidRequestError(
                    "participant does not belong to this session", code="unknown_participant"
                )
            role = MissionRole(row.role)
        if not self.policy.allows(role, action, decision_type):
            raise ForbiddenError("this role may not perform that action", code="role_forbidden")

    # ------------------------------------------------------------------ decisions
    async def decide(
        self,
        session_id: str,
        timeline_id: str | None,
        decision: DecisionInput,
        *,
        participant_id: str | None,
        metadata: dict[str, Any],
        expected_state_version: int | None,
        expected_sequence: int | None = None,
    ) -> DecisionOutcome:
        """Shared decision core: validate, record, stage the transition (no commit)."""
        ld = await self._load(session_id, timeline_id, lock=True)
        await self._authorize(session_id, participant_id, MissionAction.DECIDE, decision.type)
        tl = ld.timeline
        self.check_version(tl, expected_state_version, expected_sequence)
        state = await repo.head_state(self.db, tl)
        started = time.perf_counter()
        meta: dict[str, Any] = dict(metadata)
        if participant_id:
            meta["participant_id"] = participant_id
        try:
            record, result = record_decision(
                ld.engine,
                state,
                decision,
                session_id=session_id,
                timeline_id=tl.id,
                sequence=tl.head_sequence + 1,
                prev_record_hash=tl.head_record_hash,
                metadata=meta,
            )
        except DecisionRejectedError as exc:
            raise DecisionRejected(exc.message, code=exc.code, state_version=tl.version) from exc
        decision_id_var.set(record.decision_id)
        prev_version = tl.version
        self._persist_decision(record, participant_id)
        self._events(session_id, tl.id, result.events)
        self._snapshot(tl.id, result.state, "decision")
        tl.head_sequence = record.sequence
        tl.head_record_hash = record.record_hash
        tl.head_state_hash = record.state_after_hash
        self._run(
            ld.session, tl.id, "decision", state.tick, state.tick, started, record.state_after_hash
        )
        self._stage(
            ld,
            tl,
            prev_version,
            result.state,
            result.events,
            "decision",
            state.tick,
            decision=record,
        )
        return DecisionOutcome(ld, record, result, prev_version)

    async def apply_decision(
        self,
        session_id: str,
        req: api.DecisionRequest,
        idem: IdempotencyContext | None = None,
    ) -> tuple[api.DecisionResponse, bool]:
        async def run(make_record: Any) -> api.DecisionResponse:
            out = await self.decide(
                session_id,
                req.timeline_id,
                req.decision,
                participant_id=req.participant_id,
                metadata=dict(req.metadata),
                expected_state_version=req.expected_state_version,
                expected_sequence=req.expected_sequence,
            )
            await self._flush()
            response = api.DecisionResponse(
                decision=self.record_view(out.record),
                tick=out.result.state.tick,
                state_hash=out.record.state_after_hash,
                state_version=out.loaded.timeline.version,
                events=list(out.result.events),
                metrics=self._summary(out.loaded.engine, out.result.state),
            )
            await self._commit_and_publish(record=make_record(response) if make_record else None)
            return response

        return await self._idempotent(idem, "decision", session_id, api.DecisionResponse, 201, run)

    def _persist_decision(self, record: DecisionRecord, participant_id: str | None) -> None:
        assert record.state_before is not None
        assert record.state_after is not None
        self.db.add(
            m.MissionDecision(
                decision_id=record.decision_id,
                session_id=record.session_id,
                timeline_id=record.timeline_id,
                sequence=record.sequence,
                tick=record.tick,
                decision_type=record.decision_type,
                inputs=record.inputs,
                phase=record.phase,
                affected_systems=list(record.affected_systems),
                state_before=record.state_before,
                state_after=record.state_after,
                state_before_hash=record.state_before_hash,
                state_after_hash=record.state_after_hash,
                prev_record_hash=record.prev_record_hash,
                record_hash=record.record_hash,
                meta=record.metadata,
                participant_id=participant_id,
            )
        )

    def _conclude(self, ld: Loaded, tl: m.MissionTimeline, final: MissionState) -> None:
        if final.status == MissionStatus.CONCLUDED and final.outcome is not None:
            tl.status = "concluded"
            self.db.add(
                m.MissionOutcome(
                    timeline_id=tl.id,
                    session_id=ld.session.id,
                    outcome_code=final.outcome.code,
                    tick=final.outcome.tick,
                    rule_id=final.outcome.rule_id,
                    objectives_achieved=final.outcome.objectives_achieved,
                    objectives_failed=final.outcome.objectives_failed,
                )
            )
            if ld.session.active_timeline_id == tl.id:
                ld.session.status = "concluded"

    # ------------------------------------------------------------------ time
    async def run_advance(
        self,
        session_id: str,
        timeline_id: str | None,
        ticks: int,
        *,
        participant_id: str | None,
        expected_state_version: int | None,
        stop_when: Callable[[MissionState], bool] | None = None,
    ) -> AdvanceOutcome:
        """Shared advance core: run the engine, stage the transition (no commit).

        ``stop_when`` (optional, used by the game clock) stops after the first tick where it
        holds; see :meth:`SimulationEngine.advance`."""
        if ticks > self.settings.max_advance_ticks:
            raise InvalidRequestError(
                f"ticks must be <= {self.settings.max_advance_ticks}", code="too_many_ticks"
            )
        ld = await self._load(session_id, timeline_id, lock=True)
        await self._authorize(session_id, participant_id, MissionAction.ADVANCE)
        tl = ld.timeline
        self.check_version(tl, expected_state_version)
        state = await repo.head_state(self.db, tl)
        if state.status == MissionStatus.CONCLUDED:
            raise ConflictError(
                "the mission has concluded", code="mission_concluded", state_version=tl.version
            )
        started = time.perf_counter()
        interval = self.settings.snapshot_interval_ticks
        periodic: list[MissionState] = []

        def on_tick(s: MissionState, _: list[MissionEvent]) -> None:
            if s.tick % interval == 0:
                periodic.append(s.clone())

        try:
            result = await anyio.to_thread.run_sync(
                lambda: ld.engine.advance(state, ticks, on_tick=on_tick, stop_when=stop_when)
            )
        except MissionConcludedError as exc:  # pragma: no cover - guarded above
            raise ConflictError(str(exc), code="mission_concluded") from exc
        final = result.state
        prev_version = tl.version
        for snap in periodic:
            if snap.tick != final.tick:
                self._snapshot(tl.id, snap, "periodic")
        self._snapshot(tl.id, final, "advance")
        self._events(session_id, tl.id, result.events)
        tl.head_tick = final.tick
        tl.head_state_hash = final.state_hash()
        self._conclude(ld, tl, final)
        self._run(ld.session, tl.id, "advance", state.tick, final.tick, started, tl.head_state_hash)
        self._stage(ld, tl, prev_version, final, result.events, "advance", state.tick)
        return AdvanceOutcome(ld, state, final, list(result.events), result.ticks_run, prev_version)

    async def advance(
        self,
        session_id: str,
        req: api.AdvanceRequest,
        idem: IdempotencyContext | None = None,
    ) -> tuple[api.AdvanceResponse, bool]:
        async def run(make_record: Any) -> api.AdvanceResponse:
            out = await self.run_advance(
                session_id,
                req.timeline_id,
                req.ticks,
                participant_id=req.participant_id,
                expected_state_version=req.expected_state_version,
            )
            await self._flush()
            tl, final = out.loaded.timeline, out.final
            events = out.events[:MAX_EVENTS_IN_RESPONSE]
            response = api.AdvanceResponse(
                timeline_id=tl.id,
                from_tick=out.before.tick,
                to_tick=final.tick,
                ticks_run=out.ticks_run,
                concluded=final.status == MissionStatus.CONCLUDED,
                phase=final.phase,
                outcome=final.outcome,
                state_hash=tl.head_state_hash,
                state_version=tl.version,
                events=events,
                events_truncated=len(out.events) > len(events),
                metrics=self._summary(out.loaded.engine, final),
            )
            await self._commit_and_publish(record=make_record(response) if make_record else None)
            return response

        return await self._idempotent(idem, "advance", session_id, api.AdvanceResponse, 200, run)

    # ================================================================== reconstruction
    async def _record(self, ld: Loaded) -> tuple[MissionRecord, list[DecisionRecord], MissionState]:
        records = await repo.effective_records(self.db, ld.session.id, ld.timeline)
        initial = ld.engine.initial_state(ld.session.seed)
        try:
            record = await anyio.to_thread.run_sync(
                lambda: reconstruct(ld.engine, initial, records, ld.timeline.head_tick)
            )
        except (ReplayDivergenceError, DecisionRejectedError) as exc:
            raise IntegrityFailure(
                "replay diverged from the recorded ledger", code="replay_divergence"
            ) from exc
        if record.final_state.state_hash() != ld.timeline.head_state_hash:
            raise IntegrityFailure(
                "replayed head does not match stored head", code="replay_divergence"
            )
        return record, records, initial

    async def verify(self, session_id: str, timeline_id: str | None) -> api.VerifyResponse:
        ld = await self._load(session_id, timeline_id)
        records = await repo.effective_records(self.db, session_id, ld.timeline)
        ledger_ok = True
        try:
            verify_chain(records)
        except LedgerIntegrityError:
            ledger_ok = False
        initial = ld.engine.initial_state(ld.session.seed)
        try:
            res = await anyio.to_thread.run_sync(
                lambda: replay(
                    ld.engine,
                    initial,
                    [ReplayDecision.from_record(r) for r in records],
                    ld.timeline.head_tick,
                    verify_hashes=True,
                )
            )
            replayed = res.state.state_hash()
        except (ReplayDivergenceError, DecisionRejectedError):
            replayed = ""
        return api.VerifyResponse(
            timeline_id=ld.timeline.id,
            ledger_ok=ledger_ok,
            replay_ok=replayed == ld.timeline.head_state_hash,
            decisions_verified=len(records),
            head_state_hash=ld.timeline.head_state_hash,
            replayed_state_hash=replayed,
        )

    async def get_timeline(
        self,
        session_id: str,
        timeline_id: str | None,
        *,
        kinds: set[str] | None,
        from_tick: int | None,
        to_tick: int | None,
        limit: int,
    ) -> api.TimelineResponse:
        ld = await self._load(session_id, timeline_id)
        record, records, _ = await self._record(ld)
        events = [
            e
            for e in record.events
            if (kinds is None or e.kind.value in kinds)
            and (from_tick is None or e.tick >= from_tick)
            and (to_tick is None or e.tick <= to_tick)
        ]
        rows = {t.id: t for t in await repo.list_timelines(self.db, session_id)}
        ancestry: list[api.TimelineView] = []
        cur = ld.timeline
        while cur.parent_timeline_id is not None and cur.parent_timeline_id in rows:
            cur = rows[cur.parent_timeline_id]
            ancestry.append(self.timeline_view(cur))
        return api.TimelineResponse(
            timeline=self.timeline_view(ld.timeline),
            ancestry=ancestry,
            decisions=[self.record_view(r) for r in records],
            phase_history=record.final_state.phase_history,
            events=events[:limit],
            total_events=len(events),
        )

    # ================================================================== analysis
    async def black_box(
        self, session_id: str, timeline_id: str | None, *, counterfactuals: bool
    ) -> BlackBoxReport:
        report, _ = await self._black_box(session_id, timeline_id, counterfactuals=counterfactuals)
        return report

    async def _black_box(
        self, session_id: str, timeline_id: str | None, *, counterfactuals: bool
    ) -> tuple[BlackBoxReport, Loaded]:
        ld = await self._load(session_id, timeline_id)
        started = time.perf_counter()
        record, records, initial = await self._record(ld)
        cf = (
            counterfactual_factory(ld.engine, initial, records, ld.timeline.head_tick)
            if counterfactuals
            else None
        )
        report = await anyio.to_thread.run_sync(
            lambda: build_black_box(ld.engine, record, counterfactual=cf)
        )
        self._run(
            ld.session,
            ld.timeline.id,
            "black_box",
            0,
            ld.timeline.head_tick,
            started,
            report.final_state_hash,
        )
        await self.db.commit()
        return report, ld

    async def trace(
        self, session_id: str, timeline_id: str | None, metric: str, tick: int | None
    ) -> RootCauseTrace:
        ld = await self._load(session_id, timeline_id)
        record, records, initial = await self._record(ld)
        target_tick = ld.timeline.head_tick if tick is None else tick
        if not 0 <= target_tick <= ld.timeline.head_tick:
            raise InvalidRequestError("tick outside the timeline's history", code="bad_tick")
        cf = counterfactual_factory(ld.engine, initial, records, ld.timeline.head_tick)
        try:
            return await anyio.to_thread.run_sync(
                lambda: trace_root_cause(
                    ld.engine,
                    record.history,
                    metric,
                    target_tick,
                    decision_info=record.decision_info(),
                    counterfactual=cf,
                )
            )
        except UnknownMetricError as exc:
            raise InvalidRequestError(f"unknown metric '{metric}'", code="unknown_metric") from exc

    async def future_lens(self, session_id: str, req: api.FutureLensBody) -> FutureLensResult:
        lens_req = FutureLensRequest.model_validate(
            req.model_dump(exclude={"timeline_id", "participant_id"})
        )
        result, _, _ = await self.run_future_lens(
            session_id, req.timeline_id, req.participant_id, lens_req
        )
        return result

    async def run_future_lens(
        self,
        session_id: str,
        timeline_id: str | None,
        participant_id: str | None,
        lens_req: FutureLensRequest,
    ) -> tuple[FutureLensResult, Loaded, MissionState]:
        if (
            lens_req.knowledge_policy == "omniscient"
            and not self.settings.future_lens_omniscient_enabled
        ):
            raise ForbiddenError(
                "omniscient prediction is disabled on this server", code="omniscient_disabled"
            )
        ld = await self._load(session_id, timeline_id)
        # The knowledge policy is passed as the "decision type" so a role table can allow
        # e.g. {"future_lens": ["known_only"]} for students and ["*"] for teachers (D6).
        await self._authorize(
            session_id, participant_id, MissionAction.FUTURE_LENS, lens_req.knowledge_policy
        )
        state = await repo.head_state(self.db, ld.timeline)
        started = time.perf_counter()
        result = await anyio.to_thread.run_sync(
            lambda: FutureLens(ld.engine).predict(state, lens_req)
        )
        ld.session.future_lens_requests += 1
        self._run(
            ld.session,
            ld.timeline.id,
            "future_lens",
            state.tick,
            state.tick + lens_req.horizon_ticks,
            started,
            None,
        )
        self._stage_aux(
            ld,
            "FUTURE_LENS_READY",
            state.tick,
            {
                "request_hash": result.request_hash,
                "branches": [p.label for p in result.predictions],
                "prediction_mode": result.knowledge_policy,
            },
        )
        await self._commit_and_publish()
        return result, ld, state

    async def profile(self, session_id: str, timeline_id: str | None) -> EngineeringProfile:
        prof, _, _ = await self._profile(session_id, timeline_id)
        return prof

    async def _profile(
        self, session_id: str, timeline_id: str | None
    ) -> tuple[EngineeringProfile, Loaded, MissionRecord]:
        ld = await self._load(session_id, timeline_id)
        record, _, _ = await self._record(ld)
        prof = build_profile(ld.engine, record, lens_requests=ld.session.future_lens_requests)
        exists = (
            await self.db.execute(
                select(func.count())
                .select_from(m.MissionProfile)
                .where(
                    m.MissionProfile.timeline_id == ld.timeline.id,
                    m.MissionProfile.weights_version == prof.weights_version,
                    m.MissionProfile.head_state_hash == ld.timeline.head_state_hash,
                )
            )
        ).scalar_one()
        if not exists:
            self.db.add(
                m.MissionProfile(
                    timeline_id=ld.timeline.id,
                    weights_version=prof.weights_version,
                    head_state_hash=ld.timeline.head_state_hash,
                    profile=prof.model_dump(mode="json"),
                )
            )
            await self._commit_and_publish()
        return prof, ld, record

    async def mission_dna(self, session_id: str, timeline_id: str | None) -> MissionDNA:
        dna, _ = await self._mission_dna(session_id, timeline_id)
        return dna

    async def _mission_dna(
        self, session_id: str, timeline_id: str | None
    ) -> tuple[MissionDNA, Loaded]:
        ld = await self._load(session_id, timeline_id)
        record, _, _ = await self._record(ld)
        prof = build_profile(ld.engine, record, lens_requests=ld.session.future_lens_requests)
        dna = build_mission_dna(ld.engine, record, prof)
        exists = (
            await self.db.execute(
                select(func.count())
                .select_from(m.MissionDNARecord)
                .where(
                    m.MissionDNARecord.timeline_id == ld.timeline.id,
                    m.MissionDNARecord.head_state_hash == ld.timeline.head_state_hash,
                )
            )
        ).scalar_one()
        if not exists:
            self.db.add(
                m.MissionDNARecord(
                    timeline_id=ld.timeline.id,
                    head_state_hash=ld.timeline.head_state_hash,
                    dna_code=dna.code,
                    dna_version=dna.version,
                    genes=dna.genes,
                )
            )
            await self._commit_and_publish()
        return dna, ld

    async def orion_explain(self, session_id: str, req: api.OrionRequest) -> OrionResponse:
        ld = await self._load(session_id, req.timeline_id)
        await self._authorize(session_id, req.participant_id, MissionAction.ORION, req.topic)
        state = await repo.head_state(self.db, ld.timeline)
        records = await repo.effective_records(self.db, session_id, ld.timeline)
        trace = None
        evidence = []
        if req.topic == "why":
            if req.metric is None:
                raise InvalidRequestError("topic 'why' requires a metric", code="metric_required")
            trace = await self.trace(session_id, ld.timeline.id, req.metric, req.tick)
            registry = default_registry()
            evidence = [
                e
                for e in registry.all()
                if any(u.split(".")[0] in req.metric for u in e.simulation_usage)
            ]
        context = build_context(
            state,
            ld.engine.metrics,
            decisions=records,
            trace=trace,
            evidence=evidence,
            extra_facts=read_model_facts(ld.engine, state),
        )
        response = await self.orion.explain(context, req.topic, req.question)
        self._stage_aux(ld, "ORION_MESSAGE", state.tick, response.model_dump(mode="json"))
        await self._commit_and_publish()
        return response

    async def branch(
        self,
        session_id: str,
        *,
        decision_id: str,
        alternative: DecisionInput | None,
        timeline_id: str | None,
        continue_ticks: int,
        activate: bool,
        label: str | None,
        participant_id: str | None,
    ) -> BranchOutcome:
        """Shared rewind core: fork a new timeline (the source timeline is never modified)."""
        if continue_ticks > self.settings.max_advance_ticks:
            raise InvalidRequestError(
                f"continue_ticks must be <= {self.settings.max_advance_ticks}",
                code="too_many_ticks",
            )
        ld = await self._load(session_id, timeline_id)
        await self._authorize(
            session_id,
            participant_id,
            MissionAction.REWIND,
            alternative.type if alternative else None,
        )
        parent = ld.timeline
        records = await repo.effective_records(self.db, session_id, parent)
        try:
            plan = plan_fork(records, decision_id)
        except TimelineError as exc:
            raise NotFoundError(str(exc), code="decision_not_in_timeline") from exc

        initial = ld.engine.initial_state(ld.session.seed)
        started = time.perf_counter()
        try:
            fork = await anyio.to_thread.run_sync(
                lambda: replay(
                    ld.engine,
                    initial,
                    [ReplayDecision.from_record(r) for r in plan.inherited],
                    plan.fork_tick,
                    verify_hashes=True,
                )
            )
        except ReplayDivergenceError as exc:
            raise IntegrityFailure("ledger replay diverged", code="replay_divergence") from exc
        state = fork.state

        child_id = str(uuid.uuid4())
        child = m.MissionTimeline(
            id=child_id,
            session_id=session_id,
            parent_timeline_id=parent.id,
            fork_sequence=plan.fork_sequence,
            fork_tick=plan.fork_tick,
            label=label or f"rewind:{decision_id}",
            head_tick=state.tick,
            head_sequence=plan.fork_sequence,
            head_state_hash=state.state_hash(),
            head_record_hash=plan.prev_record_hash,
        )
        self.db.add(child)
        await self._flush()
        self._snapshot(child_id, state, "fork")
        alt_record: DecisionRecord | None = None
        all_events: list[MissionEvent] = []
        if alternative is not None:
            state, alt_record, events = self._apply_on_new_timeline(
                ld.engine, state, alternative, session_id, child, participant_id
            )
            all_events.extend(events)
        if continue_ticks and state.status != MissionStatus.CONCLUDED:
            current = state
            adv = await anyio.to_thread.run_sync(lambda: ld.engine.advance(current, continue_ticks))
            state = adv.state
            self._snapshot(child_id, state, "advance")
            self._events(session_id, child_id, adv.events)
            all_events.extend(adv.events)
            child.head_tick = state.tick
            child.head_state_hash = state.state_hash()
            self._conclude(Loaded(ld.session, child, ld.scenario_row, ld.engine), child, state)
        self.db.add(
            m.MissionTimelineBranch(
                id=str(uuid.uuid4()),
                session_id=session_id,
                parent_timeline_id=parent.id,
                child_timeline_id=child_id,
                replaced_decision_id=decision_id,
                alternative_inputs=alternative.model_dump(mode="json") if alternative else None,
                participant_id=participant_id,
            )
        )
        if activate:
            ld.session.active_timeline_id = child_id
            ld.session.status = "concluded" if state.status == MissionStatus.CONCLUDED else "active"
        self._run(
            ld.session,
            child_id,
            "rewind",
            plan.fork_tick,
            state.tick,
            started,
            child.head_state_hash,
        )
        self._stage(
            ld,
            child,
            None,
            state,
            all_events,
            "timeline_created",
            plan.fork_tick,
            decision=alt_record,
            timeline_change={
                "timeline_id": child_id,
                "parent_timeline_id": parent.id,
                "replaced_decision_id": decision_id,
                "fork_tick": plan.fork_tick,
                "active": activate,
            },
        )
        return BranchOutcome(ld, child, state, alt_record, plan.fork_tick, decision_id, activate)

    async def rewind(
        self, session_id: str, req: api.RewindRequest, idem: IdempotencyContext | None = None
    ) -> tuple[api.RewindResponse, bool]:
        async def run(make_record: Any) -> api.RewindResponse:
            out = await self.branch(
                session_id,
                decision_id=req.decision_id,
                alternative=req.alternative,
                timeline_id=req.timeline_id,
                continue_ticks=req.continue_ticks,
                activate=req.activate,
                label=req.label,
                participant_id=req.participant_id,
            )
            await self._flush()
            response = api.RewindResponse(
                timeline=self.timeline_view(out.child),
                parent_timeline_id=out.loaded.timeline.id,
                replaced_decision_id=req.decision_id,
                alternative_decision=self.record_view(out.alternative) if out.alternative else None,
                tick=out.state.tick,
                state_hash=out.child.head_state_hash,
                state_version=out.child.version,
                active=req.activate,
            )
            await self._commit_and_publish(record=make_record(response) if make_record else None)
            return response

        return await self._idempotent(idem, "branch", session_id, api.RewindResponse, 201, run)

    def _apply_on_new_timeline(
        self,
        engine: SimulationEngine,
        state: MissionState,
        decision: DecisionInput,
        session_id: str,
        child: m.MissionTimeline,
        participant_id: str | None,
    ) -> tuple[MissionState, DecisionRecord, tuple[MissionEvent, ...]]:
        meta: dict[str, Any] = {"rewind_alternative": True}
        if participant_id:
            meta["participant_id"] = participant_id
        try:
            record, result = record_decision(
                engine,
                state,
                decision,
                session_id=session_id,
                timeline_id=child.id,
                sequence=child.head_sequence + 1,
                prev_record_hash=child.head_record_hash,
                metadata=meta,
            )
        except DecisionRejectedError as exc:
            raise DecisionRejected(exc.message, code=exc.code) from exc
        self._persist_decision(record, participant_id)
        self._events(session_id, child.id, result.events)
        self._snapshot(child.id, result.state, "decision")
        child.head_sequence = record.sequence
        child.head_record_hash = record.record_hash
        child.head_state_hash = record.state_after_hash
        return result.state, record, result.events


def read_model_facts(engine: SimulationEngine, state: MissionState) -> list[ContextFact]:
    """ORION context facts taken from the frontend-safe read models (radiation budget and
    objective statuses), so ORION speaks from the same structured state the client sees."""
    facts: list[ContextFact] = []
    rad = build_radiation(engine, state)
    if rad.dose_limit_msv is not None:
        facts.append(
            ContextFact(
                id="read_model:radiation.dose_margin_msv",
                label="Remaining mission dose margin of the most exposed crew member",
                value=rad.dose_margin_msv,
                unit="mSv",
                source="read_model",
            )
        )
        facts.append(
            ContextFact(
                id="read_model:radiation.budget_state",
                label="Radiation budget state",
                value=rad.budget_state,
                source="read_model",
            )
        )
    facts.append(
        ContextFact(
            id="read_model:radiation.exposure_status",
            label="Current radiation exposure status",
            value=rad.exposure_status,
            source="read_model",
        )
    )
    for obj in build_objectives(engine, state).objectives:
        facts.append(
            ContextFact(
                id=f"objective:{obj.id}",
                label=f"Objective {obj.id} ({obj.category}, required={obj.required})",
                value=obj.status,
                source="read_model",
            )
        )
    return facts


async def evidence_list(db: AsyncSession) -> list[m.ScienceEvidenceRecord]:
    return list(
        (
            await db.execute(select(m.ScienceEvidenceRecord).order_by(m.ScienceEvidenceRecord.id))
        ).scalars()
    )


async def evidence_get(db: AsyncSession, evidence_id: str) -> m.ScienceEvidenceRecord:
    row = await db.get(m.ScienceEvidenceRecord, evidence_id)
    if row is None:
        raise NotFoundError(f"evidence '{evidence_id}' not found", code="evidence_not_found")
    return row


async def nasa_sources(db: AsyncSession) -> list[m.NASASourceRecord]:
    return list(
        (await db.execute(select(m.NASASourceRecord).order_by(m.NASASourceRecord.id))).scalars()
    )
