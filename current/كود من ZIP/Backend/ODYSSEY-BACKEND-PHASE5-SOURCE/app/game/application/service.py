"""Game application service: the only write path of ``odyssey.game.v1``.

Every mutation runs in one database transaction:

1. lock the game session row (``SELECT ... FOR UPDATE``; plus optimistic ``state_version``),
2. verify the session token, then the idempotency key (a committed retry returns the stored
   response), then ``expected_state_version`` (``STALE_STATE``),
3. run one :func:`~app.game.application.turn.run_turn` through :class:`ServiceSimPort`
   (decisions and clock advancement are recorded in the simulation ledger by ``MissionService``),
4. persist timeline document, campaign meta, rewind anchors, command log, checkpoints, mission
   transitions and realtime events, store the idempotency record, commit,
5. publish the events (best effort; clients resume by ``seq``).

A rejection anywhere rolls the whole transaction back: no partial state.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Table, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.api.container import Container
from app.core.errors import (
    AppError,
    ConflictError,
    DecisionRejected,
    InvalidRequestError,
    NotFoundError,
)
from app.game.actions.errors import GameRuleError
from app.game.actions.planner import Command
from app.game.actions.registry import ACTIONS
from app.game.adapters.black_box import CommandRef, build_game_black_box
from app.game.adapters.future_lens import build_game_future_lens, plan_candidates
from app.game.application.identity import (
    hash_token,
    new_public_id,
    new_token,
    verify_token,
)
from app.game.application.memory import mission_seed
from app.game.application.ports import StopWhen
from app.game.application.readviews import (
    capabilities_view,
    catalog_view,
    expansion_map,
    readiness_view,
    vehicle_view,
    why_view,
)
from app.game.application.reference import GAME_MANAGED, scenario_row
from app.game.application.runtime import GameRuntime
from app.game.application.turn import (
    TurnResult,
    public_state,
    run_turn,
    settle_new_mission,
)
from app.game.campaign.campaign import (
    check_can_start_phase,
    first_mission,
    new_campaign,
    start_mission,
)
from app.game.content.loader import LoadedContent
from app.game.contracts import protocol as p
from app.game.contracts.analysis import (
    GameBlackBoxView,
    GameEngineeringProfileView,
    GameFutureLensView,
    GameMissionDNAView,
    ProfileDimension,
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
from app.game.realtime.bus import game_channel
from app.game.realtime.derive import DerivedEvent, PublicState, campaign_events, derive
from app.game.runtime import clock as clockmod
from app.game.world.conditions import Ctx
from app.game.world.sim import SimView
from app.game.world.state import CampaignMeta, TimelineGameState
from app.game.world.views import object_view
from app.read_models.analysis import build_black_box_view, build_future_lens_view
from app.read_models.visibility import entered_phases
from app.repositories import missions as repo
from app.services import idempotency
from app.services.contract_service import ContractService
from app.services.idempotency import IdempotencyContext
from app.services.mission_service import MissionService
from app.simulation.analysis.future_lens import CandidateBranch, FutureLensRequest
from app.simulation.domain.decisions import DecisionInput
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

log = logging.getLogger("odyssey.game")

EVENT_TYPES = (
    "mission.updated",
    "mission.transitioned",
    "objective.updated",
    "system.state_changed",
    "system.alert_changed",
    "resource.threshold_changed",
    "incident.started",
    "incident.updated",
    "incident.resolved",
    "capability.progressed",
    "certification.granted",
    "discovery.recorded",
    "inventory.changed",
    "cargo.changed",
    "infrastructure.changed",
    "knowledge.unlocked",
    "world.access_changed",
    "world.object_revealed",
    "interactions.changed",
    "crew.updated",
    "crew.cue",
    "clock.updated",
    "time.advanced",
    "campaign.updated",
    "timeline.changed",
    "checkpoint.saved",
    "future_lens.ready",
    "black_box.ready",
)
CRITICAL_ACTIONS = frozenset(
    {
        "repair.perform",
        "mission.authorize",
        "crew.assign_location",
        "module.install",
        "module.remove",
        "vehicle.dispatch",
    }
)


def _semver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def content_compatible(save_version: str, content: LoadedContent) -> bool:
    """A save loads only with content in ``[compatible_from, content_version]`` (manifest)."""
    manifest = content.content.manifest
    return (
        _semver(manifest.compatible_from)
        <= _semver(save_version)
        <= _semver(manifest.content_version)
    )


class GameMissionComplete(AppError):
    code = "mission_not_active"
    public_code = "MISSION_COMPLETE"


def to_app_error(exc: GameRuleError, state_version: int | None) -> AppError:
    details = dict(exc.details)
    if exc.kind == "invalid":
        return InvalidRequestError(
            exc.message, code=exc.reason, details=details, state_version=state_version
        )
    if exc.kind == "not_found":
        return NotFoundError(exc.message, code=exc.reason, details=details)
    if exc.kind == "complete":
        return GameMissionComplete(
            exc.message, code=exc.reason, details=details, state_version=state_version
        )
    return DecisionRejected(
        exc.message, code=exc.reason, details=details, state_version=state_version
    )


class ServiceSimPort:
    """Simulation port backed by MissionService (same transaction, recorded in the ledger)."""

    def __init__(
        self,
        svc: MissionService,
        sim_session_id: str,
        sim_timeline_id: str,
        engine: SimulationEngine,
        state: MissionState,
    ) -> None:
        self._svc = svc
        self._sid = sim_session_id
        self._tid = sim_timeline_id
        self._engine = engine
        self._state = state

    @property
    def engine(self) -> SimulationEngine:
        return self._engine

    async def state(self) -> MissionState:
        return self._state

    async def apply(
        self, decision: DecisionInput, metadata: Mapping[str, Any]
    ) -> tuple[MissionState, str]:
        out = await self._svc.decide(
            self._sid,
            self._tid,
            decision,
            participant_id=None,
            metadata=dict(metadata),
            expected_state_version=None,
        )
        # Several decisions (and a clock catch-up) can be recorded in one game turn. The
        # session does not autoflush, so flush now: the next ledger step must read this head.
        await self._svc._flush()
        self._state = out.result.state
        return self._state, out.record.decision_id

    async def advance(self, ticks: int, stop_when: StopWhen | None) -> MissionState:
        out = await self._svc.run_advance(
            self._sid,
            self._tid,
            ticks,
            participant_id=None,
            expected_state_version=None,
            stop_when=stop_when,
        )
        await self._svc._flush()
        self._state = out.final
        return self._state


@dataclass
class Loaded:
    sess: Any
    tl: Any
    doc: TimelineGameState
    meta: CampaignMeta
    port: ServiceSimPort
    tl_id: str = ""  # captured at load: usable after a rollback expired the ORM rows


def _iso(dt: datetime | None) -> str:
    return (dt or datetime.now(UTC)).astimezone(UTC).isoformat()


class GameService:
    def __init__(self, db: AsyncSession, container: Container, runtime: GameRuntime) -> None:
        from app.game.persistence import models as gm

        self.gm = gm
        self.db = db
        self.c = container
        self.rt = runtime
        self.content = runtime.content
        # ContractService is the superset of MissionService (it adds the v1 safe read models);
        # realtime=False: game sessions emit odyssey.game.v1 events only, never v1 ones.
        self.missions = ContractService(
            db,
            container.settings,
            container.engines,
            container.bus,
            container.orion,
            container.policy,
            realtime=False,
            game_access=True,
        )
        self._outbox: list[p.GameEventEnvelope] = []

    # ================================================================== loading
    async def _session(self, session_id: str, token: str | None, *, lock: bool = False) -> Any:
        gm = self.gm
        stmt = select(gm.GameSession).where(gm.GameSession.id == session_id)
        if lock:
            stmt = stmt.with_for_update()
        sess = (await self.db.execute(stmt)).scalar_one_or_none()
        if sess is None:
            raise NotFoundError("game session not found", code="session_not_found")
        verify_token(token, sess.token_hash)
        if not content_compatible(sess.content_version, self.content):
            # docs/SAVE_RESTORE.md#content-versions: never silently load incompatible content
            raise InvalidRequestError(
                "this save was made with an incompatible content version",
                code="content_version_mismatch",
                details={
                    "save": sess.content_version,
                    "server": self.content.version,
                    "compatible_from": self.content.content.manifest.compatible_from,
                },
            )
        return sess

    async def _load(self, sess: Any) -> Loaded:
        gm = self.gm
        if sess.active_timeline_id is None:
            raise ConflictError("no active timeline", code="no_active_timeline")
        tl = await self.db.get(gm.GameTimeline, sess.active_timeline_id)
        assert tl is not None
        doc = TimelineGameState.model_validate(tl.doc)
        meta = CampaignMeta.model_validate(sess.meta)
        port = await self._port(tl)
        return Loaded(sess, tl, doc, meta, port, tl.id)

    async def _port(self, tl: Any) -> ServiceSimPort:
        ld = await self.missions._load(tl.sim_session_id, tl.sim_timeline_id)
        state = await repo.head_state(self.db, ld.timeline)
        return ServiceSimPort(
            self.missions, tl.sim_session_id, tl.sim_timeline_id, ld.engine, state
        )

    def _public(self, ld: Loaded) -> PublicState:
        return public_state(self.content, ld.doc, ld.meta, SimView(ld.port.engine, ld.port._state))

    # ================================================================== creation
    async def _new_timeline(
        self, sess: Any, meta: CampaignMeta, mission_id: str, *, parent: str | None = None
    ) -> tuple[Any, TimelineGameState]:
        doc = start_mission(self.content, meta, mission_id)
        attempt = meta.missions[mission_id].attempts
        scenario = self.content.mission_scenario(mission_id)
        row = await scenario_row(self.db, scenario)
        sim_session_id = await self.missions.create_session_for(
            row, mission_seed(sess.seed, mission_id, attempt), managed_by=GAME_MANAGED
        )
        sim = await repo.get_session_row(self.db, sim_session_id, allow_game_managed=True)
        sim_ld = await self.missions._load(sim_session_id, sim.active_timeline_id)
        settle_new_mission(
            self.content, doc, meta, sim_ld.engine, await repo.head_state(self.db, sim_ld.timeline)
        )
        tl = self.gm.GameTimeline(
            id=new_public_id("gt_"),
            session_id=sess.id,
            mission_id=mission_id,
            attempt=attempt,
            sim_session_id=sim_session_id,
            sim_timeline_id=sim.active_timeline_id,
            parent_timeline_id=parent,
            status="active",
            doc=doc.model_dump(mode="json"),
            doc_hash=doc.state_hash(),
        )
        self.db.add(tl)
        return tl, doc

    async def create_session(
        self, req: p.CreateGameSessionRequest, principal: str
    ) -> p.CreateGameSessionResponse:
        gm = self.gm
        token = new_token()
        profile = gm.GameProfile(
            id=new_public_id("gp_"), display_name=req.display_name, principal=principal
        )
        self.db.add(profile)
        meta = new_campaign(self.content)
        sess = gm.GameSession(
            id=new_public_id("gs_"),
            profile_id=profile.id,
            content_id=self.content.content.manifest.content_id,
            content_version=self.content.version,
            content_hash=self.content.content_hash,
            seed=secrets.randbelow(2**31 - 1),
            token_hash=hash_token(token),
            status="active",
            meta=meta.model_dump(mode="json"),
            event_seq=0,
        )
        self.db.add(sess)
        await self._flush()
        tl, doc = await self._new_timeline(sess, meta, first_mission(self.content).id)
        sess.meta = meta.model_dump(mode="json")
        sess.active_timeline_id = tl.id
        await self._flush()
        self._checkpoint(sess, tl, doc, meta, "mission_transition", "session_created", 0)
        await self._commit()
        log.info("game_session_created", extra={"game_session_id": sess.id})
        return p.CreateGameSessionResponse(
            session_token=token, bootstrap=await self.bootstrap(sess.id, token)
        )

    # ================================================================== reads
    def features(self) -> p.ServerFeatures:
        actions = [
            p.ActionInfo(
                type=a.type,
                target=a.target,
                summary=a.summary,
                mutates=a.mutates,
                content_defined=a.handler == "interaction",
                params=[
                    p.ActionParamInfo(
                        name=x.name, kind=x.kind, required=x.required, values=list(x.values)
                    )
                    for x in a.params
                ],
            )
            for a in ACTIONS.values()
        ]
        from app.core.errors import PUBLIC_CODES

        return p.ServerFeatures(
            protocol=p.GAME_PROTOCOL,
            content_version=self.content.version,
            clock_modes=["PAUSED", "REALTIME", "ACCELERATED", "DECISION_PAUSED"],
            actions=actions,
            event_types=list(EVENT_TYPES),
            error_codes=sorted(PUBLIC_CODES),
            limits={
                "max_params": 8,
                "event_retention": self.rt.event_retention,
                "max_catchup_ticks_default": 24,
                "events_page_max": 500,
            },
            auth="session_token (Authorization: Bearer); anonymous principal",
        )

    def _snapshot(self, ld: Loaded, pub: PublicState | None = None) -> p.GameSnapshot:
        pub = pub or self._public(ld)
        sess, tl = ld.sess, ld.tl
        return p.GameSnapshot(
            session=p.SessionRef(
                id=sess.id,
                status=sess.status,
                content_id=sess.content_id,
                content_version=sess.content_version,
                state_version=sess.state_version,
                last_seq=sess.event_seq,
                created_at=_iso(sess.created_at),
            ),
            timeline=p.TimelineRef(
                id=tl.id,
                mission_id=tl.mission_id,
                attempt=tl.attempt,
                status=tl.status,
                parent_timeline_id=tl.parent_timeline_id,
            ),
            state_version=sess.state_version,
            campaign=pub.campaign,
            mission=pub.mission,
            clock=pub.clock,
            world=pub.world,
            discoveries=list(pub.discoveries),
            insights=list(pub.insights),
            resume=p.ResumeInfo(
                last_seq=sess.event_seq,
                ws_path=f"/api/game/v1/ws/sessions/{sess.id}",
                events_path=f"/api/game/v1/sessions/{sess.id}/events",
                restore_path=f"/api/game/v1/sessions/{sess.id}/restore",
                retained_events=self.rt.event_retention,
            ),
        )

    async def snapshot(self, session_id: str, token: str | None) -> p.GameSnapshot:
        sess = await self._session(session_id, token)
        return self._snapshot(await self._load(sess))

    async def bootstrap(self, session_id: str, token: str | None) -> p.GameBootstrap:
        return p.GameBootstrap(
            features=self.features(), snapshot=await self.snapshot(session_id, token)
        )

    async def loaded(self, session_id: str, token: str | None) -> Loaded:
        return await self._load(await self._session(session_id, token))

    # ================================================================== writes
    async def _flush(self) -> None:
        try:
            await self.db.flush()
        except StaleDataError as exc:
            await self.db.rollback()
            raise ConflictError(
                "the session was modified concurrently; refresh and retry",
                code="concurrent_modification",
            ) from exc
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("conflicting write; retry", code="write_conflict") from exc

    async def _commit(self) -> None:
        try:
            await self.db.commit()
        except StaleDataError as exc:
            await self.db.rollback()
            self._outbox.clear()
            raise ConflictError(
                "the session was modified concurrently; refresh and retry",
                code="concurrent_modification",
            ) from exc
        except IntegrityError as exc:
            await self.db.rollback()
            self._outbox.clear()
            raise ConflictError("conflicting write; retry", code="write_conflict") from exc
        for env in self._outbox:
            try:
                await self.rt.bus.publish(game_channel(env.session_id), env)
            except Exception:  # best effort: the database is the source of truth
                log.warning("game_publish_failed", extra={"error_code": "publish_failed"})
        self._outbox.clear()

    def _checkpoint(
        self,
        sess: Any,
        tl: Any,
        doc: TimelineGameState,
        meta: CampaignMeta,
        kind: str,
        label: str,
        sim_tick: int,
    ) -> str:
        cid = new_public_id("ck_")
        self.db.add(
            self.gm.GameCheckpoint(
                id=cid,
                session_id=sess.id,
                timeline_id=tl.id,
                kind=kind,
                label=label[:64],
                mission_id=doc.mission_id,
                state_version=sess.state_version,
                sim_tick=sim_tick,
                location=doc.player_location,
                doc=doc.model_dump(mode="json"),
                meta=meta.model_dump(mode="json"),
            )
        )
        return cid

    async def _trim(self, sess: Any, *, auto_checkpoint_added: bool) -> None:
        """Bounded retention: realtime events beyond ``event_retention`` and automatic
        checkpoints beyond ``auto_checkpoints_kept`` (statements only issued when needed)."""
        gm = self.gm
        if sess.event_seq > self.rt.event_retention:
            await self.db.execute(
                delete(gm.GameEvent).where(
                    gm.GameEvent.session_id == sess.id,
                    gm.GameEvent.seq <= sess.event_seq - self.rt.event_retention,
                )
            )
        if not auto_checkpoint_added:
            return
        keep = self.rt.auto_checkpoints_kept
        old = (
            (
                await self.db.execute(
                    select(gm.GameCheckpoint.id)
                    .where(
                        gm.GameCheckpoint.session_id == sess.id, gm.GameCheckpoint.kind == "auto"
                    )
                    .order_by(gm.GameCheckpoint.state_version.desc(), gm.GameCheckpoint.id)
                    .offset(keep)
                )
            )
            .scalars()
            .all()
        )
        if old:
            await self.db.execute(delete(gm.GameCheckpoint).where(gm.GameCheckpoint.id.in_(old)))

    def _envelopes(
        self,
        sess: Any,
        timeline_id: str,
        prev_version: int,
        events: Sequence[DerivedEvent],
        sim_tick: int,
        tick_hours: float,
    ) -> list[p.GameEventEnvelope]:
        now = _iso(None)
        out = []
        for ev in events:
            sess.event_seq += 1
            env = p.GameEventEnvelope(
                event_id=f"{sess.id}:{sess.event_seq}",
                seq=sess.event_seq,
                session_id=sess.id,
                timeline_id=timeline_id,
                state_version=prev_version + 1,
                prev_state_version=prev_version,
                type=ev.type,
                scope=ev.scope,
                sim_tick=sim_tick,
                sim_time_hours=round(sim_tick * tick_hours, 3),
                server_time=now,
                payload=ev.payload,
            )
            self.db.add(
                self.gm.GameEvent(
                    session_id=sess.id,
                    seq=env.seq,
                    event_id=env.event_id,
                    timeline_id=timeline_id,
                    state_version=env.state_version,
                    type=env.type,
                    envelope=env.model_dump(mode="json"),
                )
            )
            out.append(env)
        self._outbox.extend(out)
        return out

    async def _apply_turn(
        self,
        ld: Loaded,
        before: PublicState,
        result: TurnResult,
        *,
        command_id: str | None,
        action: str | None,
        target: str | None,
    ) -> tuple[list[p.GameEventEnvelope], dict[str, Any] | None, bool]:
        """Persist one turn. Returns (envelopes, mission_transition, mutated)."""
        sess, tl = ld.sess, ld.tl
        prev_version = sess.state_version
        engine = ld.port.engine
        tick_hours = engine.scenario.time.tick_hours
        doc_changed = result.doc.state_hash() != ld.doc.state_hash()
        meta_changed = result.meta.state_hash() != ld.meta.state_hash()
        auto_added = False
        mutated = bool(
            doc_changed
            or meta_changed
            or result.decision_ids
            or result.ticks_advanced
            or (result.outcome is not None and result.outcome.checkpoint_label)
        )
        if not mutated:
            return [], None, False
        # Exactly one authoritative version step per accepted turn (application-managed
        # version counter: every flush of this transaction checks WHERE state_version = prev).
        sess.state_version = prev_version + 1
        after_doc, after_meta = result.doc, result.meta
        if result.pre_decision_doc is not None and command_id is not None:
            self.db.add(
                self.gm.GameStateSnapshot(
                    session_id=sess.id,
                    timeline_id=tl.id,
                    kind="pre_decision",
                    command_id=command_id,
                    decision_id=result.decision_ids[0],
                    sim_tick=result.pre_decision_tick or 0,
                    state_version=prev_version,
                    doc=result.pre_decision_doc.model_dump(mode="json"),
                )
            )
        tl.doc = after_doc.model_dump(mode="json")
        tl.doc_hash = after_doc.state_hash()
        sess.meta = after_meta.model_dump(mode="json")
        transition = None
        sim_after = SimView(engine, result.state)
        if result.mission_ended:
            tl.status = after_doc.status
            events = derive(before, public_state(self.content, after_doc, after_meta, sim_after))
            nxt = result.completion.next_mission if result.completion else None
            record = result.completion.record if result.completion else result.failure
            assert record is not None
            transition = {
                "from_mission": after_doc.mission_id,
                "result": record.result,
                "tier": record.tier,
                "next_mission": nxt,
                "capabilities_progressed": dict(record.capabilities_progressed),
                "certifications_granted": list(record.certifications_granted),
            }
            events.append(
                DerivedEvent(
                    "black_box.ready",
                    "mission",
                    {"mission": after_doc.mission_id, "timeline_id": tl.id},
                )
            )
            self._checkpoint(
                sess,
                tl,
                after_doc,
                after_meta,
                "mission_transition",
                f"{after_doc.mission_id}:{record.result}",
                result.state.tick,
            )
            if nxt is not None:
                new_tl, new_doc = await self._new_timeline(sess, after_meta, nxt, parent=None)
                sess.meta = after_meta.model_dump(mode="json")
                sess.active_timeline_id = new_tl.id
                transition["timeline_id"] = new_tl.id
                events.append(
                    DerivedEvent(
                        "mission.transitioned",
                        "campaign",
                        {
                            "from_mission": after_doc.mission_id,
                            "to_mission": nxt,
                            "timeline_id": new_tl.id,
                            "snapshot_required": True,
                        },
                    )
                )
                await self._flush()
                self._checkpoint(
                    sess, new_tl, new_doc, after_meta, "mission_transition", f"{nxt}:start", 0
                )
        else:
            events = derive(before, public_state(self.content, after_doc, after_meta, sim_after))
            resolved = any(r.incidents_resolved for r in result.reactions)
            label = result.outcome.checkpoint_label if result.outcome else None
            if label:
                cid = self._checkpoint(
                    sess, tl, after_doc, after_meta, "manual", label, result.state.tick
                )
                events.append(
                    DerivedEvent(
                        "checkpoint.saved",
                        "session",
                        {"checkpoint": cid, "kind": "manual", "label": label},
                    )
                )
            if resolved:
                self._checkpoint(
                    sess,
                    tl,
                    after_doc,
                    after_meta,
                    "incident_resolved",
                    "incident_resolved",
                    result.state.tick,
                )
            if action in CRITICAL_ACTIONS and result.decision_ids:
                self._checkpoint(
                    sess, tl, after_doc, after_meta, "critical_decision", action, result.state.tick
                )
            if (prev_version + 1) % self.rt.auto_checkpoint_every == 0:
                self._checkpoint(sess, tl, after_doc, after_meta, "auto", "auto", result.state.tick)
                auto_added = True
        envelopes = self._envelopes(
            sess, tl.id, prev_version, events, result.state.tick, tick_hours
        )
        if command_id is not None and action is not None:
            self.db.add(
                self.gm.GameCommand(
                    session_id=sess.id,
                    timeline_id=tl.id,
                    command_id=command_id,
                    action=action,
                    target=target,
                    result=(result.outcome.result if result.outcome else "applied"),
                    server_time_ms=self.rt.clock.now_ms(),
                    state_version=prev_version + 1,
                    decision_ids=list(result.decision_ids),
                )
            )
        sess.updated_at = datetime.now(UTC)
        await self._flush()
        await self._trim(sess, auto_checkpoint_added=auto_added)
        return envelopes, transition, True

    # ------------------------------------------------------------------ commands
    async def command(
        self,
        session_id: str,
        token: str | None,
        req: p.GameCommandRequest,
        idem: IdempotencyContext,
    ) -> tuple[p.CommandResult, bool]:
        started = time.perf_counter()
        if req.session_id != session_id:
            raise InvalidRequestError("session_id does not match the path", code="session_mismatch")
        sess = await self._session(session_id, token, lock=True)
        stored = await idempotency.find(self.db, idem, "game_command", session_id)
        if stored is not None:
            log.info(
                "game_command",
                extra={
                    "idempotent_replay": True,
                    "action_id": req.command_id,
                    "game_session_id": session_id,
                },
            )
            return p.CommandResult.model_validate(stored.response), True
        if req.expected_state_version != sess.state_version:
            raise ConflictError(
                "the session has changed since the state this command was based on",
                code="stale_state",
                state_version=sess.state_version,
                details={"expected_state_version": req.expected_state_version},
            )
        if req.timeline_id is not None and req.timeline_id != sess.active_timeline_id:
            raise ConflictError(
                "that timeline is not the active one",
                code="stale_state",
                state_version=sess.state_version,
                details={"active_timeline_id": sess.active_timeline_id},
            )
        gm = self.gm
        dup = (
            await self.db.execute(
                select(gm.GameCommand.id).where(
                    gm.GameCommand.session_id == session_id,
                    gm.GameCommand.command_id == req.command_id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise InvalidRequestError("command_id was already used", code="duplicate_command_id")
        ld = await self._load(sess)
        before = self._public(ld)
        prev_version = sess.state_version
        cmd = Command(
            action=req.action, target=req.target, params=dict(req.params), actor=req.actor
        )
        try:
            result = await run_turn(
                self.content,
                ld.doc,
                ld.meta,
                ld.port,
                self.rt.clock.now_ms(),
                cmd,
                decision_metadata={"game_command_id": req.command_id, "game_action": req.action},
            )
        except GameRuleError as exc:
            await self.db.rollback()
            self._log(req, session_id, ld, "rejected", started, exc.reason)
            raise to_app_error(exc, prev_version) from None
        try:
            return await self._finish_command(
                req, session_id, ld, before, prev_version, result, idem, started
            )
        except ConflictError:
            # Lost a race (another request committed first). If that request was this very
            # command (same idempotency key), return its committed response, never a second
            # mutation; otherwise the caller refreshes and retries (STALE_STATE).
            stored = await idempotency.find(self.db, idem, "game_command", session_id)
            if stored is not None:
                return p.CommandResult.model_validate(stored.response), True
            raise

    async def _finish_command(
        self,
        req: p.GameCommandRequest,
        session_id: str,
        ld: Loaded,
        before: PublicState,
        prev_version: int,
        result: TurnResult,
        idem: IdempotencyContext,
        started: float,
    ) -> tuple[p.CommandResult, bool]:
        sess = ld.sess
        envelopes, transition, _ = await self._apply_turn(
            ld, before, result, command_id=req.command_id, action=req.action, target=req.target
        )
        outcome = result.outcome
        response = p.CommandResult(
            command_id=req.command_id,
            action=req.action,
            target=req.target,
            result=outcome.result if outcome else "applied",
            reason=outcome.reason if outcome else None,
            session_id=session_id,
            timeline_id=sess.active_timeline_id or ld.tl.id,
            state_version=sess.state_version,
            prev_state_version=prev_version,
            sim_tick=result.state.tick,
            last_seq=sess.event_seq,
            events=envelopes,
            context=outcome.context if outcome else None,
            mission_transition=transition,
        )
        idempotency.record(
            self.db, idem, "game_command", session_id, 200, response.model_dump(mode="json")
        )
        await self._commit()
        self._log(
            req,
            session_id,
            ld,
            response.result,
            started,
            response.reason,
            version=response.state_version,
        )
        return response, False

    def _log(
        self,
        req: p.GameCommandRequest,
        session_id: str,
        ld: Loaded,
        result: str,
        started: float,
        reason: str | None,
        version: int | None = None,
    ) -> None:
        log.info(
            "game_command",
            extra={
                "action_id": req.command_id,
                "action_type": req.action,
                "game_session_id": session_id,
                "game_timeline_id": ld.tl_id,
                "mission": ld.doc.mission_id,
                "game_state_version": version,
                "result": result,
                "reason": reason,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )

    # ------------------------------------------------------------------ clock sync / restore
    async def _sync_locked(
        self, sess: Any
    ) -> tuple[Loaded, TurnResult, list[p.GameEventEnvelope], int]:
        ld = await self._load(sess)
        before = self._public(ld)
        from_tick = ld.port._state.tick
        result = await run_turn(
            self.content, ld.doc, ld.meta, ld.port, self.rt.clock.now_ms(), None
        )
        envelopes, _, _ = await self._apply_turn(
            ld, before, result, command_id=None, action=None, target=None
        )
        return ld, result, envelopes, from_tick

    async def sync(self, session_id: str, token: str | None, req: p.SyncRequest) -> p.SyncResult:
        sess = await self._session(session_id, token, lock=True)
        if (
            req.expected_state_version is not None
            and req.expected_state_version != sess.state_version
        ):
            raise ConflictError("stale state", code="stale_state", state_version=sess.state_version)
        _, result, envelopes, _ = await self._sync_locked(sess)
        await self._commit()
        ld2 = await self._load(sess)
        return p.SyncResult(
            session_id=session_id,
            timeline_id=ld2.tl.id,
            state_version=sess.state_version,
            sim_tick=ld2.port._state.tick,
            ticks_advanced=result.ticks_advanced,
            clock=self._public(ld2).clock,
            last_seq=sess.event_seq,
            events=envelopes,
        )

    async def restore(
        self, session_id: str, token: str | None, req: p.RestoreRequest
    ) -> p.RestoreResult:
        """The single restore/reconnect path: settle the clock, then return the authoritative
        snapshot plus everything retained since ``last_seq`` (or ``resync_required``)."""
        sess = await self._session(session_id, token, lock=True)
        last_seen = req.last_seq if req.last_seq is not None else sess.event_seq
        _, result, _, from_tick = await self._sync_locked(sess)
        await self._commit()
        page = await self.events(session_id, token, after_seq=last_seen, limit=500)
        ld = await self._load(sess)
        counts = Counter(e.type for e in page.events)
        # More missed events than one page: the snapshot is the truth (same rule as the socket).
        resync = page.resync_required or page.has_more
        reason = (
            "events_expired" if page.resync_required else "backlog_too_large" if resync else None
        )
        return p.RestoreResult(
            snapshot=self._snapshot(ld),
            resync_required=resync,
            reason=reason,
            events=[] if resync else page.events,
            while_disconnected=p.DisconnectSummary(
                ticks_advanced=result.ticks_advanced,
                from_tick=from_tick,
                to_tick=ld.port._state.tick,
                event_types=dict(sorted(counts.items())),
            ),
        )

    async def events(
        self, session_id: str, token: str | None, *, after_seq: int, limit: int
    ) -> p.EventPage:
        sess = await self._session(session_id, token)
        gm = self.gm
        limit = max(1, min(limit, 500))
        last = sess.event_seq
        if after_seq > last:
            resync = True  # unknown position (ahead of the server)
        elif after_seq == last:
            resync = False
        else:
            oldest = (
                await self.db.execute(
                    select(func.min(gm.GameEvent.seq)).where(gm.GameEvent.session_id == session_id)
                )
            ).scalar_one_or_none()
            resync = oldest is None or oldest > after_seq + 1  # events expired
        rows = (
            []
            if resync
            else (
                await self.db.execute(
                    select(gm.GameEvent)
                    .where(gm.GameEvent.session_id == session_id, gm.GameEvent.seq > after_seq)
                    .order_by(gm.GameEvent.seq)
                    .limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )
        events = [p.GameEventEnvelope.model_validate(r.envelope) for r in rows[:limit]]
        return p.EventPage(
            session_id=session_id,
            after_seq=after_seq,
            last_seq=sess.event_seq,
            resync_required=resync,
            events=events,
            has_more=len(rows) > limit,
        )

    # ------------------------------------------------------------------ missions
    async def start_phase(
        self, session_id: str, token: str | None, phase_id: str, req: p.StartMissionRequest
    ) -> p.GameSnapshot:
        """Start the next mission of a campaign phase (e.g. walking up to the MARS-01 board).
        A phase whose readiness gates are missing answers ``mars_mission_locked``."""
        sess = await self._session(session_id, token, lock=True)
        meta = CampaignMeta.model_validate(sess.meta)
        version = sess.state_version
        try:
            mission = check_can_start_phase(self.content, meta, phase_id)
        except GameRuleError as exc:
            await self.db.rollback()
            raise to_app_error(exc, version) from None
        return await self._start_mission(sess, session_id, token, mission.id, req)

    async def start_mission(
        self, session_id: str, token: str | None, mission_id: str, req: p.StartMissionRequest
    ) -> p.GameSnapshot:
        sess = await self._session(session_id, token, lock=True)
        return await self._start_mission(sess, session_id, token, mission_id, req)

    async def _start_mission(
        self,
        sess: Any,
        session_id: str,
        token: str | None,
        mission_id: str,
        req: p.StartMissionRequest,
    ) -> p.GameSnapshot:
        if req.expected_state_version != sess.state_version:
            raise ConflictError("stale state", code="stale_state", state_version=sess.state_version)
        meta = CampaignMeta.model_validate(sess.meta)
        before = meta.model_copy(deep=True)
        prev_version = sess.state_version
        sess.state_version = prev_version + 1
        try:
            tl, doc = await self._new_timeline(sess, meta, mission_id)
        except GameRuleError as exc:
            await self.db.rollback()
            raise to_app_error(exc, prev_version) from None
        await self._flush()
        sess.meta = meta.model_dump(mode="json")
        sess.active_timeline_id = tl.id
        from app.game.world.views import campaign_view

        events = campaign_events(
            campaign_view(self.content, before), campaign_view(self.content, meta)
        )
        events.append(
            DerivedEvent(
                "mission.transitioned",
                "campaign",
                {"to_mission": mission_id, "timeline_id": tl.id, "snapshot_required": True},
            )
        )
        self._checkpoint(sess, tl, doc, meta, "mission_transition", f"{mission_id}:start", 0)
        self._envelopes(
            sess,
            tl.id,
            prev_version,
            events,
            0,
            self.content.mission_scenario(mission_id).time.tick_hours,
        )
        sess.updated_at = datetime.now(UTC)
        await self._flush()
        await self._commit()
        return await self.snapshot(session_id, token)

    # ------------------------------------------------------------------ rewind
    async def rewind_points(self, session_id: str, token: str | None) -> p.RewindPoints:
        sess = await self._session(session_id, token)
        gm = self.gm
        rows = (
            await self.db.execute(
                select(gm.GameCommand, gm.GameStateSnapshot.sim_tick)
                .join(
                    gm.GameStateSnapshot,
                    (gm.GameStateSnapshot.timeline_id == gm.GameCommand.timeline_id)
                    & (gm.GameStateSnapshot.command_id == gm.GameCommand.command_id),
                )
                .where(
                    gm.GameCommand.session_id == session_id,
                    gm.GameCommand.timeline_id == sess.active_timeline_id,
                )
                .order_by(gm.GameCommand.id.desc())
                .limit(100)
            )
        ).all()
        return p.RewindPoints(
            timeline_id=sess.active_timeline_id or "",
            points=[
                p.RewindPointView(
                    command_id=c.command_id,
                    action=c.action,
                    target=c.target,
                    sim_tick=tick,
                    state_version=c.state_version,
                )
                for c, tick in rows
            ],
        )

    async def rewind(
        self, session_id: str, token: str | None, req: p.RewindRequest
    ) -> p.RewindResult:
        """Fork the active mission timeline to just before a command that changed the
        simulation. Timeline-local state comes from the rewind anchor; campaign meta is untouched,
        so nothing committed can be duplicated or undone."""
        sess = await self._session(session_id, token, lock=True)
        if req.expected_state_version != sess.state_version:
            raise ConflictError("stale state", code="stale_state", state_version=sess.state_version)
        gm = self.gm
        ld = await self._load(sess)
        if ld.doc.status != "active":
            raise GameMissionComplete(
                "the mission has ended; rewind is not available",
                code="mission_not_active",
                state_version=sess.state_version,
            )
        snap = (
            await self.db.execute(
                select(gm.GameStateSnapshot).where(
                    gm.GameStateSnapshot.timeline_id == ld.tl.id,
                    gm.GameStateSnapshot.command_id == req.command_id,
                    gm.GameStateSnapshot.kind == "pre_decision",
                )
            )
        ).scalar_one_or_none()
        if snap is None or snap.decision_id is None:
            raise NotFoundError(
                "no rewind point for that command on the active timeline",
                code="command_not_rewindable",
            )
        prev_version = sess.state_version
        sess.state_version = prev_version + 1
        out = await self.missions.branch(
            ld.tl.sim_session_id,
            decision_id=snap.decision_id,
            alternative=None,
            timeline_id=ld.tl.sim_timeline_id,
            continue_ticks=0,
            activate=True,
            label=f"game:{req.command_id}"[:64],
            participant_id=None,
        )
        doc = TimelineGameState.model_validate(snap.doc)
        now = self.rt.clock.now_ms()
        clockmod.set_mode(doc.clock, "PAUSED", now, out.state.tick, reason="rewound")
        new_tl = gm.GameTimeline(
            id=new_public_id("gt_"),
            session_id=sess.id,
            mission_id=ld.tl.mission_id,
            attempt=ld.tl.attempt,
            sim_session_id=ld.tl.sim_session_id,
            sim_timeline_id=out.child.id,
            parent_timeline_id=ld.tl.id,
            fork_command_id=req.command_id,
            status="active",
            doc=doc.model_dump(mode="json"),
            doc_hash=doc.state_hash(),
        )
        self.db.add(new_tl)
        ld.tl.status = "rewound"
        sess.active_timeline_id = new_tl.id
        await self._flush()
        events = [
            DerivedEvent(
                "timeline.changed",
                "session",
                {
                    "previous_timeline_id": ld.tl.id,
                    "timeline_id": new_tl.id,
                    "fork_command_id": req.command_id,
                    "sim_tick": out.state.tick,
                    "snapshot_required": True,
                },
            )
        ]
        self._checkpoint(sess, new_tl, doc, ld.meta, "critical_decision", "rewind", out.state.tick)
        envelopes = self._envelopes(
            sess,
            new_tl.id,
            prev_version,
            events,
            out.state.tick,
            ld.port.engine.scenario.time.tick_hours,
        )
        sess.updated_at = datetime.now(UTC)
        await self._flush()
        await self._commit()
        return p.RewindResult(
            session_id=session_id,
            previous_timeline_id=ld.tl.id,
            timeline=p.TimelineRef(
                id=new_tl.id,
                mission_id=new_tl.mission_id,
                attempt=new_tl.attempt,
                status=new_tl.status,
                parent_timeline_id=new_tl.parent_timeline_id,
            ),
            state_version=sess.state_version,
            sim_tick=out.state.tick,
            events=envelopes,
        )

    # ------------------------------------------------------------------ checkpoints
    async def checkpoints(
        self, session_id: str, token: str | None, limit: int = 50
    ) -> p.CheckpointPage:
        await self._session(session_id, token)
        gm = self.gm
        rows = (
            (
                await self.db.execute(
                    select(gm.GameCheckpoint)
                    .where(gm.GameCheckpoint.session_id == session_id)
                    .order_by(
                        gm.GameCheckpoint.created_at.desc(), gm.GameCheckpoint.state_version.desc()
                    )
                    .limit(max(1, min(limit, 200)))
                )
            )
            .scalars()
            .all()
        )
        return p.CheckpointPage(
            checkpoints=[
                p.CheckpointView(
                    id=r.id,
                    kind=r.kind,
                    label=r.label,
                    mission_id=r.mission_id,
                    timeline_id=r.timeline_id,
                    state_version=r.state_version,
                    sim_tick=r.sim_tick,
                    location=r.location,
                    created_at=_iso(r.created_at),
                )
                for r in rows
            ]
        )

    # ------------------------------------------------------------------ on-demand detail reads
    async def read_ctx(self, session_id: str, token: str | None) -> tuple[Loaded, Ctx]:
        ld = await self.loaded(session_id, token)
        return ld, Ctx(self.content, ld.doc, ld.meta, SimView(ld.port.engine, ld.port._state))

    async def capabilities(self, session_id: str, token: str | None) -> CapabilitiesView:
        ld = await self.loaded(session_id, token)
        return capabilities_view(self.content, ld.meta, ld.doc)

    async def readiness(self, session_id: str, token: str | None, profile_id: str) -> ReadinessView:
        sess = await self._session(session_id, token)
        if profile_id not in self.content.index.profiles:
            raise NotFoundError("unknown readiness profile", code="unknown_readiness_profile")
        return readiness_view(self.content, CampaignMeta.model_validate(sess.meta), profile_id)

    async def expansion_map(self, session_id: str, token: str | None) -> ExpansionMapView:
        sess = await self._session(session_id, token)
        return expansion_map(self.content, CampaignMeta.model_validate(sess.meta))

    async def why(self, session_id: str, token: str | None, insight_id: str) -> WhyView:
        ld, ctx = await self.read_ctx(session_id, token)
        if insight_id not in ld.doc.insights and insight_id not in ld.meta.insights:
            # unknown and not-yet-unlocked insights are indistinguishable (no spoilers)
            raise NotFoundError("no such unlocked insight", code="insight_not_unlocked")
        return why_view(ctx, insight_id)

    async def object_detail(self, session_id: str, token: str | None, object_id: str) -> ObjectView:
        ld, ctx = await self.read_ctx(session_id, token)
        obj = self.content.index.objects.get(object_id)
        state = ld.doc.objects.get(object_id)
        if obj is None or state is None or not state.known:
            raise NotFoundError("no such known object in this world", code="unknown_target")
        return object_view(ctx, obj)

    async def vehicle(self, session_id: str, token: str | None, vehicle_id: str) -> VehicleView:
        ld, ctx = await self.read_ctx(session_id, token)
        obj = self.content.index.objects.get(vehicle_id)
        state = ld.doc.objects.get(vehicle_id)
        if obj is None or state is None or not state.known or obj.vehicle_class is None:
            raise NotFoundError("no such known vehicle in this world", code="unknown_vehicle")
        return vehicle_view(ctx, vehicle_id)

    def catalog(self) -> CatalogView:
        return catalog_view(self.content)

    # ------------------------------------------------------------------ informational events
    async def _emit_info(
        self,
        session_id: str,
        timeline_id: str,
        events: Sequence[DerivedEvent],
        sim_tick: int,
        tick_hours: float,
    ) -> list[p.GameEventEnvelope]:
        """Append session-scope informational events (``future_lens.ready``) that change no
        authoritative state: ``state_version`` stays as it is (prev == current) and only the
        realtime sequence advances. Best effort: a lost race just skips the event."""
        table = cast(Table, self.gm.GameSession.__table__)
        try:
            row = (
                await self.db.execute(
                    select(table.c.event_seq, table.c.state_version)
                    .where(table.c.id == session_id)
                    .with_for_update()
                )
            ).one()
            seq, version = int(row.event_seq), int(row.state_version)
            now = _iso(None)
            out = []
            for ev in events:
                seq += 1
                env = p.GameEventEnvelope(
                    event_id=f"{session_id}:{seq}",
                    seq=seq,
                    session_id=session_id,
                    timeline_id=timeline_id,
                    state_version=version,
                    prev_state_version=version,
                    type=ev.type,
                    scope=ev.scope,
                    sim_tick=sim_tick,
                    sim_time_hours=round(sim_tick * tick_hours, 3),
                    server_time=now,
                    payload=ev.payload,
                )
                self.db.add(
                    self.gm.GameEvent(
                        session_id=session_id,
                        seq=seq,
                        event_id=env.event_id,
                        timeline_id=timeline_id,
                        state_version=version,
                        type=env.type,
                        envelope=env.model_dump(mode="json"),
                    )
                )
                out.append(env)
            # Core UPDATE: bypasses the ORM version counter on purpose (no state change).
            await self.db.execute(
                update(table).where(table.c.id == session_id).values(event_seq=seq)
            )
            self._outbox.extend(out)
            await self._commit()
        except (ConflictError, IntegrityError, StaleDataError):
            await self.db.rollback()
            self._outbox.clear()
            log.warning("game_info_event_skipped", extra={"game_session_id": session_id})
            return []
        finally:
            self.db.expire_all()
        return out

    # ------------------------------------------------------------------ Future Lens adapter
    async def future_lens(
        self, session_id: str, token: str | None, req: p.FutureLensRequestBody
    ) -> GameFutureLensView:
        """Settle the clock (same path as sync), then project the semantic candidates with the
        ``known_only`` Future Lens. The projection itself changes no game state."""
        sess = await self._session(session_id, token, lock=True)
        await self._sync_locked(sess)
        await self._commit()
        ld = await self.loaded(session_id, token)
        if ld.doc.status != "active":
            raise GameMissionComplete(
                "the mission has ended; Future Lens is not available",
                code="mission_not_active",
                state_version=ld.sess.state_version,
            )
        engine, state = ld.port.engine, ld.port._state
        planned = plan_candidates(self.content, ld.doc, ld.meta, engine, state, req.candidates)
        branches = [
            CandidateBranch(label=pc.id, decisions=pc.decisions)
            for pc in planned
            if pc.rejection is None
        ] or [CandidateBranch(label="_noop", decisions=[])]
        lens_req = FutureLensRequest(
            candidates=branches,
            include_baseline=True,
            horizon_ticks=req.horizon_ticks,
            samples=4,
            knowledge_policy="known_only",
            explain=False,
        )
        tl_id, mission_id, version = ld.tl.id, ld.tl.mission_id, ld.sess.state_version
        result, _, base_state = await self.missions.run_future_lens(
            ld.tl.sim_session_id, ld.tl.sim_timeline_id, None, lens_req
        )
        tick_hours = engine.scenario.time.tick_hours
        view = build_future_lens_view(
            engine,
            result,
            session_id=session_id,
            timeline_id=tl_id,
            state_version=version,
            requested_ticks=req.horizon_ticks,
            entered=entered_phases(base_state),
        )
        out = build_game_future_lens(
            view,
            planned,
            session_id=session_id,
            timeline_id=tl_id,
            mission_id=mission_id,
            state_version=version,
            tick_hours=tick_hours,
        )
        await self._emit_info(
            session_id,
            tl_id,
            [
                DerivedEvent(
                    "future_lens.ready",
                    "session",
                    {
                        "base_tick": out.base_tick,
                        "branches": [b.id for b in out.branches],
                        "prediction_mode": "known_only",
                    },
                )
            ],
            out.base_tick,
            tick_hours,
        )
        return out

    # ------------------------------------------------------------------ Black Box adapter
    async def _timeline_row(self, sess: Any, timeline_id: str | None) -> Any:
        tid = timeline_id or sess.active_timeline_id
        tl = await self.db.get(self.gm.GameTimeline, tid) if tid else None
        if tl is None or tl.session_id != sess.id:
            raise NotFoundError("no such timeline in this session", code="timeline_not_found")
        return tl

    async def black_box(
        self, session_id: str, token: str | None, timeline_id: str | None, *, counterfactuals: bool
    ) -> GameBlackBoxView:
        gm = self.gm
        sess = await self._session(session_id, token)
        tl = await self._timeline_row(sess, timeline_id)
        tl_id, mission_id, version = tl.id, tl.mission_id, sess.state_version
        tl_status = tl.status
        doc = TimelineGameState.model_validate(tl.doc)
        rows = (
            await self.db.execute(
                select(
                    gm.GameCommand.command_id,
                    gm.GameCommand.action,
                    gm.GameCommand.target,
                    gm.GameCommand.decision_ids,
                ).where(gm.GameCommand.session_id == session_id)
            )
        ).all()
        commands: dict[str, CommandRef] = {}
        for command_id, action, target, decision_ids in rows:
            for did in decision_ids or []:
                commands.setdefault(did, CommandRef(command_id, action, target))
        report, sim_ld = await self.missions._black_box(
            tl.sim_session_id, tl.sim_timeline_id, counterfactuals=counterfactuals
        )
        view = build_black_box_view(
            sim_ld.engine,
            report,
            session_id=session_id,
            timeline_id=tl_id,
            state_version=version,
            counterfactuals=counterfactuals,
        )
        return build_game_black_box(
            self.content,
            view,
            commands,
            session_id=session_id,
            timeline_id=tl_id,
            mission_id=mission_id,
            world_id=doc.world_id,
            state_version=version,
            tick_hours=sim_ld.engine.scenario.time.tick_hours,
            known_objects={oid for oid, st in doc.objects.items() if st.known},
            mission_status=tl_status,
        )

    # ------------------------------------------------------------------ profile / DNA adapters
    async def engineering_profile(
        self, session_id: str, token: str | None, timeline_id: str | None
    ) -> GameEngineeringProfileView:
        sess = await self._session(session_id, token)
        tl = await self._timeline_row(sess, timeline_id)
        tl_id, mission_id = tl.id, tl.mission_id
        v = await self.missions.engineering_profile(tl.sim_session_id, tl.sim_timeline_id)
        return GameEngineeringProfileView(
            session_id=session_id,
            timeline_id=tl_id,
            mission_id=mission_id,
            weights_version=v.weights_version,
            provisional=v.provisional,
            dimensions=[
                ProfileDimension(id=d.id, value=d.value, contributions=dict(d.contributions))
                for d in v.dimensions
            ],
            coverage=dict(v.coverage),
            notes=list(v.notes),
        )

    async def mission_dna(
        self, session_id: str, token: str | None, timeline_id: str | None
    ) -> GameMissionDNAView:
        sess = await self._session(session_id, token)
        tl = await self._timeline_row(sess, timeline_id)
        tl_id, mission_id = tl.id, tl.mission_id
        v = await self.missions.mission_dna_share(tl.sim_session_id, tl.sim_timeline_id)
        return GameMissionDNAView(
            session_id=session_id,
            timeline_id=tl_id,
            mission_id=mission_id,
            code=v.code,
            dna_version=v.dna_version,
            scenario_id=v.scenario_id,
            scenario_version=v.scenario_version,
            outcome_code=v.outcome_code,
            outcome_tier=v.outcome_tier,
            concluded=v.concluded,
            genes=dict(v.genes),
        )
