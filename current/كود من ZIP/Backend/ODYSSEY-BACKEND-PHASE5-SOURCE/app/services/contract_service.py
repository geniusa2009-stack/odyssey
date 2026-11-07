"""The frozen frontend-safe application contract (API v1, docs/API_FREEZE_V1.md).

``ContractService`` extends the orchestrator (:class:`MissionService`) with the read-model
projections and the option-based commands. It never re-implements simulation logic: the engine
computes every state, the orchestrator persists, versions and publishes, and this class maps
commands to engine decisions and projects results through ``app/read_models``.
"""

from __future__ import annotations

import re
from typing import Any

import anyio

from app.core.errors import InvalidRequestError, NotFoundError
from app.db import models as m
from app.read_models.analysis import (
    BlackBoxView,
    EngineeringProfileView,
    ForkPreviewView,
    FutureLensView,
    MissionDNAView,
    MissionHistoryView,
    RewindPointsView,
    TimelineChangeView,
    TimelineNodeView,
    TimelineTreeView,
    build_black_box_view,
    build_dna_view,
    build_future_lens_view,
    build_history,
    build_profile_view,
    build_rewind_points,
    decision_entry,
)
from app.read_models.bootstrap import (
    ApiInfo,
    MissionBootstrap,
    ParticipantInfo,
    RealtimeInfo,
    SessionInfo,
    build_capabilities,
    build_scenario_view,
    endpoint_map,
)
from app.read_models.decisions import (
    AvailableDecisionsView,
    build_decision_options,
    command_to_decision,
    decision_to_option_id,
)
from app.read_models.events import event_view
from app.read_models.mission import (
    MissionCompletionView,
    MissionSnapshotView,
    TimelineRef,
    build_completion,
    build_hud,
    build_outcome,
    build_snapshot,
    outcome_tier,
)
from app.read_models.objectives import ObjectiveOutlookView, build_objectives
from app.read_models.radiation import RadiationBudgetView, build_radiation
from app.read_models.resources import (
    ResourceDetailView,
    build_resource_detail,
    get_resource_def,
)
from app.read_models.results import AdvanceResultView, DecisionResultView, EventsPage
from app.read_models.visibility import entered_phases
from app.realtime.contract import RealtimeEvent
from app.repositories import missions as repo
from app.schemas.commands import (
    AdvanceCommand,
    BranchCommand,
    DecisionCommand,
    FutureLensCommand,
)
from app.services.idempotency import IdempotencyContext
from app.services.mission_service import MAX_EVENTS_IN_RESPONSE, Loaded, MissionService
from app.simulation.analysis.future_lens import CandidateBranch, FutureLensRequest
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.replay import ReplayDecision, ReplayDivergenceError, replay
from app.simulation.replay.timeline import TimelineError, plan_fork

MAX_EVENTS_PAGE = 1000
MAX_HISTORY_EVENTS = 2000
_EVENT_ID = re.compile(r"^([0-9a-fA-F\-]{1,36}):(\d{1,9}):(\d{1,6}|aux:[0-9a-f]{16})$")
_END_OF_GROUP = 10**9


class ContractService(MissionService):
    # ================================================================== helpers
    @staticmethod
    def timeline_ref(tl: m.MissionTimeline, active_id: str | None) -> TimelineRef:
        return TimelineRef(
            id=tl.id,
            label=tl.label or "",
            parent_timeline_id=tl.parent_timeline_id,
            fork_tick=tl.fork_tick,
            fork_sequence=tl.fork_sequence,
            status=tl.status,
            is_active=tl.id == active_id,
            head_tick=tl.head_tick,
            head_sequence=tl.head_sequence,
            state_version=tl.version,
        )

    async def _engine_for(self, session_id: str) -> SimulationEngine:
        sess = await repo.get_session_row(self.db, session_id, allow_game_managed=self.game_access)
        row = await self.db.get(m.MissionScenario, sess.scenario_id)
        if row is None:
            raise NotFoundError("session scenario missing", code="scenario_missing")
        return self.engines.get(row.content_hash, row.definition)

    async def _head(self, session_id: str, timeline_id: str | None) -> tuple[Loaded, MissionState]:
        ld = await self._load(session_id, timeline_id)
        return ld, await repo.head_state(self.db, ld.timeline)

    async def _snapshot_of(
        self, ld: Loaded, state: MissionState | None = None
    ) -> MissionSnapshotView:
        state = state or await repo.head_state(self.db, ld.timeline)
        previous = await repo.previous_state(self.db, ld.timeline.id, state.tick)
        return build_snapshot(
            ld.engine,
            state,
            session_id=ld.session.id,
            timeline=self.timeline_ref(ld.timeline, ld.session.active_timeline_id),
            previous=previous,
        )

    # ================================================================== read models
    async def snapshot(self, session_id: str, timeline_id: str | None) -> MissionSnapshotView:
        return await self._snapshot_of(await self._load(session_id, timeline_id))

    async def bootstrap(self, session_id: str) -> MissionBootstrap:
        ld = await self._load(session_id, None)
        state = await repo.head_state(self.db, ld.timeline)
        snap = await self._snapshot_of(ld, state)
        timelines = await repo.list_timelines(self.db, session_id)
        participants = await repo.participants(self.db, session_id)
        sc_row = ld.scenario_row
        active = ld.session.active_timeline_id
        return MissionBootstrap(
            api=ApiInfo(),
            capabilities=build_capabilities(
                self.settings,
                radiation_budget=ld.engine.scenario.radiation.dose_limit_msv is not None,
            ),
            scenario=build_scenario_view(
                ld.engine,
                content_hash=sc_row.content_hash,
                provisional=sc_row.provisional,
                state=state,
            ),
            session=SessionInfo(
                session_id=session_id,
                status=ld.session.status,
                active_timeline_id=active,
                participants=[
                    ParticipantInfo(id=p.id, handle=p.handle, role=p.role) for p in participants
                ],
                timelines=[self.timeline_ref(t, active) for t in timelines],
                future_lens_requests=ld.session.future_lens_requests,
            ),
            snapshot=snap,
            realtime=RealtimeInfo(
                path=f"/api/v1/ws/mission-sessions/{session_id}",
                events_path=f"/api/v1/mission-sessions/{session_id}/events",
            ),
            endpoints=endpoint_map(session_id),
        )

    async def decision_options(
        self, session_id: str, timeline_id: str | None
    ) -> AvailableDecisionsView:
        ld, state = await self._head(session_id, timeline_id)
        return build_decision_options(ld.engine, state)

    async def objectives(self, session_id: str, timeline_id: str | None) -> ObjectiveOutlookView:
        ld, state = await self._head(session_id, timeline_id)
        return build_objectives(ld.engine, state)

    async def radiation_budget(
        self, session_id: str, timeline_id: str | None
    ) -> RadiationBudgetView:
        ld, state = await self._head(session_id, timeline_id)
        return build_radiation(ld.engine, state)

    async def resource_detail(
        self, session_id: str, resource_id: str, timeline_id: str | None
    ) -> ResourceDetailView:
        ld, state = await self._head(session_id, timeline_id)
        rdef = get_resource_def(ld.engine, resource_id)
        if rdef is None:
            raise NotFoundError(f"resource '{resource_id}' not found", code="resource_not_found")
        previous = await repo.previous_state(self.db, ld.timeline.id, state.tick)
        recorded = await repo.recorded_states(self.db, ld.timeline.id)
        return build_resource_detail(ld.engine, state, rdef, previous, recorded)

    async def completion(self, session_id: str, timeline_id: str | None) -> MissionCompletionView:
        ld, state = await self._head(session_id, timeline_id)
        records = await repo.effective_records(self.db, session_id, ld.timeline)
        return build_completion(
            ld.engine,
            state,
            session_id=session_id,
            timeline_id=ld.timeline.id,
            state_version=ld.timeline.version,
            decisions_count=len(records),
        )

    async def history(
        self, session_id: str, timeline_id: str | None, limit: int
    ) -> MissionHistoryView:
        ld = await self._load(session_id, timeline_id)
        record, records, _ = await self._record(ld)
        return build_history(
            session_id=session_id,
            timeline_id=ld.timeline.id,
            state_version=ld.timeline.version,
            state=record.final_state,
            records=records,
            events=record.events,
            limit=limit,
        )

    # ================================================================== commands
    async def decision_command(
        self, session_id: str, cmd: DecisionCommand, idem: IdempotencyContext | None = None
    ) -> tuple[DecisionResultView, bool]:
        async def run(make_record: Any) -> DecisionResultView:
            engine = await self._engine_for(session_id)
            decision = command_to_decision(engine, cmd.option_id, cmd.decision_type, cmd.parameters)
            out = await self.decide(
                session_id,
                cmd.timeline_id,
                decision,
                participant_id=cmd.participant_id,
                metadata=dict(cmd.metadata),
                expected_state_version=cmd.expected_state_version,
            )
            await self._flush()
            tl = out.loaded.timeline
            events = list(out.result.events)
            shown = events[:MAX_EVENTS_IN_RESPONSE]
            response = DecisionResultView(
                session_id=session_id,
                timeline_id=tl.id,
                state_version=tl.version,
                prev_state_version=out.prev_version,
                tick=out.result.state.tick,
                decision=decision_entry(out.record, tl.id),
                hud=build_hud(out.loaded.engine, out.result.state),
                events=[event_view(e) for e in shown],
                events_truncated=len(events) > len(shown),
            )
            await self._commit_and_publish(record=make_record(response) if make_record else None)
            return response

        return await self._idempotent(
            idem, "decision_command", session_id, DecisionResultView, 201, run
        )

    async def advance_command(
        self, session_id: str, cmd: AdvanceCommand, idem: IdempotencyContext | None = None
    ) -> tuple[AdvanceResultView, bool]:
        async def run(make_record: Any) -> AdvanceResultView:
            out = await self.run_advance(
                session_id,
                cmd.timeline_id,
                cmd.ticks,
                participant_id=cmd.participant_id,
                expected_state_version=cmd.expected_state_version,
            )
            await self._flush()
            tl, final, engine = out.loaded.timeline, out.final, out.loaded.engine
            shown = out.events[:MAX_EVENTS_IN_RESPONSE]
            response = AdvanceResultView(
                session_id=session_id,
                timeline_id=tl.id,
                state_version=tl.version,
                prev_state_version=out.prev_version,
                from_tick=out.before.tick,
                to_tick=final.tick,
                ticks_run=out.ticks_run,
                concluded=final.status == MissionStatus.CONCLUDED,
                phase=final.phase,
                outcome=build_outcome(engine, final),
                hud=build_hud(engine, final),
                events=[event_view(e) for e in shown],
                events_truncated=len(out.events) > len(shown),
            )
            await self._commit_and_publish(record=make_record(response) if make_record else None)
            return response

        return await self._idempotent(
            idem, "advance_command", session_id, AdvanceResultView, 200, run
        )

    async def branch_command(
        self, session_id: str, cmd: BranchCommand, idem: IdempotencyContext | None = None
    ) -> tuple[TimelineChangeView, bool]:
        async def run(make_record: Any) -> TimelineChangeView:
            engine = await self._engine_for(session_id)
            alternative = (
                command_to_decision(
                    engine, cmd.alternative.option_id, None, cmd.alternative.parameters
                )
                if cmd.alternative is not None
                else None
            )
            out = await self.branch(
                session_id,
                decision_id=cmd.decision_id,
                alternative=alternative,
                timeline_id=cmd.timeline_id,
                continue_ticks=cmd.continue_ticks,
                activate=cmd.activate,
                label=cmd.label,
                participant_id=cmd.participant_id,
            )
            await self._flush()
            active = out.loaded.session.active_timeline_id
            response = TimelineChangeView(
                timeline=self.timeline_ref(out.child, active),
                parent_timeline_id=out.loaded.timeline.id,
                replaced_decision_id=out.replaced_decision_id,
                alternative_decision=decision_entry(out.alternative, out.child.id)
                if out.alternative
                else None,
                state_version=out.child.version,
                active=out.activated,
                hud=build_hud(out.loaded.engine, out.state),
            )
            await self._commit_and_publish(record=make_record(response) if make_record else None)
            return response

        return await self._idempotent(
            idem, "timeline_branch", session_id, TimelineChangeView, 201, run
        )

    # ================================================================== realtime resume
    async def events_after(
        self,
        session_id: str,
        *,
        last_event_id: str | None,
        timeline_id: str | None,
        last_state_version: int | None,
        last_seq: int | None,
    ) -> EventsPage:
        """Retained realtime events after a cursor, or why the client must re-fetch the
        snapshot (``resync_required`` with a reason)."""
        if last_event_id is None and last_state_version is None:
            raise InvalidRequestError(
                "last_event_id or last_state_version is required", code="cursor_required"
            )
        ld = await self._load(session_id, None)
        active = ld.timeline
        snapshot_path = f"/api/v1/mission-sessions/{session_id}/snapshot"

        def resync(reason: Any) -> EventsPage:
            return EventsPage(
                session_id=session_id,
                timeline_id=active.id,
                state_version=active.version,
                resync_required=True,
                reason=reason,
                snapshot_path=snapshot_path,
            )

        if last_event_id is not None:
            match = _EVENT_ID.match(last_event_id)
            if match is None:
                raise InvalidRequestError("malformed last_event_id", code="bad_event_id")
            cursor_tl, version = match.group(1), int(match.group(2))
            raw_seq = match.group(3)
            seq = _END_OF_GROUP if raw_seq.startswith("aux:") else int(raw_seq)
        else:
            assert last_state_version is not None
            cursor_tl = timeline_id or active.id
            version = last_state_version
            seq = _END_OF_GROUP if last_seq is None else last_seq
        timelines = {t.id for t in await repo.list_timelines(self.db, session_id)}
        if cursor_tl not in timelines:
            return resync("unknown_timeline")
        if cursor_tl != active.id:
            return resync("timeline_changed")
        if version > active.version:
            return resync("unknown_position")
        # The next position the client needs: the rest of the cursor's group, or the start of
        # the next group when the cursor ends its group (or names a whole state version).
        complete = seq >= _END_OF_GROUP
        if not complete:
            row = await repo.realtime_event(self.db, f"{active.id}:{version}:{seq}")
            if row is not None and seq >= int(row.envelope.get("seq_count", 0)) - 1:
                complete = True
        expected = (version + 1, 0) if complete else (version, seq + 1)
        empty = EventsPage(
            session_id=session_id,
            timeline_id=active.id,
            state_version=active.version,
            resync_required=False,
            snapshot_path=snapshot_path,
        )
        if expected[0] > active.version:
            return empty  # the client is up to date
        oldest = await repo.oldest_retained_version(self.db, active.id)
        if oldest is None or expected[0] < oldest:
            return resync("events_expired")
        rows = await repo.realtime_events_after(
            self.db, active.id, version, min(seq, _END_OF_GROUP), MAX_EVENTS_PAGE + 1
        )
        if len(rows) > MAX_EVENTS_PAGE:
            return resync("too_many_events")
        if not rows or (rows[0].state_version, rows[0].seq) != expected:
            return resync("events_unavailable")
        events = [RealtimeEvent.model_validate(r.envelope) for r in rows]
        return EventsPage(
            session_id=session_id,
            timeline_id=active.id,
            state_version=active.version,
            resync_required=False,
            snapshot_path=snapshot_path,
            events=events,
        )

    # ================================================================== analysis
    async def future_lens_projection(
        self, session_id: str, cmd: FutureLensCommand
    ) -> FutureLensView:
        engine = await self._engine_for(session_id)
        candidates = [
            CandidateBranch(
                label=c.label,
                decisions=[
                    command_to_decision(engine, d.option_id, None, d.parameters)
                    for d in c.decisions
                ],
            )
            for c in cmd.candidates
        ]
        lens_req = FutureLensRequest(
            candidates=candidates,
            include_baseline=cmd.include_baseline,
            horizon_ticks=cmd.horizon_ticks,
            samples=cmd.samples,
            knowledge_policy=cmd.prediction_mode,
        )
        result, ld, base_state = await self.run_future_lens(
            session_id, cmd.timeline_id, cmd.participant_id, lens_req
        )
        return build_future_lens_view(
            ld.engine,
            result,
            session_id=session_id,
            timeline_id=ld.timeline.id,
            state_version=ld.timeline.version,
            requested_ticks=cmd.horizon_ticks,
            entered=entered_phases(base_state),
        )

    async def black_box_summary(
        self, session_id: str, timeline_id: str | None, *, counterfactuals: bool
    ) -> BlackBoxView:
        report, ld = await self._black_box(session_id, timeline_id, counterfactuals=counterfactuals)
        return build_black_box_view(
            ld.engine,
            report,
            session_id=session_id,
            timeline_id=ld.timeline.id,
            state_version=ld.timeline.version,
            counterfactuals=counterfactuals,
        )

    async def engineering_profile(
        self, session_id: str, timeline_id: str | None
    ) -> EngineeringProfileView:
        prof, ld, record = await self._profile(session_id, timeline_id)
        return build_profile_view(
            prof,
            session_id=session_id,
            timeline_id=ld.timeline.id,
            state_version=ld.timeline.version,
            concluded=record.final_state.status == MissionStatus.CONCLUDED,
            lens_requests=ld.session.future_lens_requests,
        )

    async def mission_dna_share(self, session_id: str, timeline_id: str | None) -> MissionDNAView:
        dna, ld = await self._mission_dna(session_id, timeline_id)
        return build_dna_view(ld.engine, dna, concluded=ld.timeline.status == "concluded")

    # ================================================================== timelines / rewind
    async def timeline_tree(self, session_id: str) -> TimelineTreeView:
        sess = await repo.get_session_row(self.db, session_id, allow_game_managed=self.game_access)
        engine = await self._engine_for(session_id)
        timelines = await repo.list_timelines(self.db, session_id)
        branches = {b.child_timeline_id: b for b in await repo.branches(self.db, session_id)}
        outcomes = {o.timeline_id: o for o in await repo.outcomes(self.db, session_id)}
        children: dict[str, list[str]] = {}
        for t in timelines:
            if t.parent_timeline_id is not None:
                children.setdefault(t.parent_timeline_id, []).append(t.id)
        nodes = []
        for t in timelines:
            b = branches.get(t.id)
            o = outcomes.get(t.id)
            nodes.append(
                TimelineNodeView(
                    id=t.id,
                    label=t.label or "",
                    parent_timeline_id=t.parent_timeline_id,
                    children=children.get(t.id, []),
                    fork_tick=t.fork_tick,
                    fork_sequence=t.fork_sequence,
                    replaced_decision_id=b.replaced_decision_id if b else None,
                    alternative_option_id=decision_to_option_id(b.alternative_inputs)
                    if b and b.alternative_inputs
                    else None,
                    status=t.status,
                    is_active=t.id == sess.active_timeline_id,
                    head_tick=t.head_tick,
                    head_sequence=t.head_sequence,
                    state_version=t.version,
                    outcome_code=o.outcome_code if o else None,
                    outcome_tier=outcome_tier(engine, o.outcome_code, o.rule_id) if o else None,
                )
            )
        return TimelineTreeView(
            session_id=session_id, active_timeline_id=sess.active_timeline_id, timelines=nodes
        )

    async def rewind_points(self, session_id: str, timeline_id: str | None) -> RewindPointsView:
        ld = await self._load(session_id, timeline_id)
        records = await repo.effective_records(self.db, session_id, ld.timeline)
        return build_rewind_points(
            records,
            session_id=session_id,
            timeline_id=ld.timeline.id,
            state_version=ld.timeline.version,
        )

    async def rewind_preview(
        self, session_id: str, decision_id: str, timeline_id: str | None
    ) -> ForkPreviewView:
        ld = await self._load(session_id, timeline_id)
        records = await repo.effective_records(self.db, session_id, ld.timeline)
        try:
            plan = plan_fork(records, decision_id)
        except TimelineError as exc:
            raise NotFoundError(str(exc), code="decision_not_in_timeline") from exc
        initial = ld.engine.initial_state(ld.session.seed)
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
            from app.core.errors import IntegrityFailure

            raise IntegrityFailure("ledger replay diverged", code="replay_divergence") from exc
        replaced = next(r for r in records if r.decision_id == decision_id)
        return ForkPreviewView(
            session_id=session_id,
            timeline_id=ld.timeline.id,
            replaced_decision=decision_entry(replaced, ld.timeline.id),
            fork_tick=plan.fork_tick,
            inherited_decisions=len(plan.inherited),
            discarded_decisions=len(records) - len(plan.inherited),
            state_at_fork=build_hud(ld.engine, fork.state),
        )
