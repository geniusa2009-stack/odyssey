"""Query helpers. All SQL goes through SQLAlchemy expressions (parameterised)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import IntegrityFailure, NotFoundError
from app.db import models as m
from app.simulation.domain.state import MissionState
from app.simulation.replay.ledger import DecisionRecord
from app.simulation.replay.timeline import TimelineError, TimelineSpec, effective_ledger


async def get_session_row(
    db: AsyncSession, session_id: str, *, allow_game_managed: bool = False
) -> m.MissionSession:
    """``allow_game_managed``: simulation sessions owned by the game backend
    (``managed_by='game'``) are invisible to the v1 API; only the game service sees them."""
    row = await db.get(m.MissionSession, session_id)
    if row is None or (row.managed_by is not None and not allow_game_managed):
        raise NotFoundError(f"mission session '{session_id}' not found", code="session_not_found")
    return row


async def get_timeline_row(
    db: AsyncSession, session_id: str, timeline_id: str, *, lock: bool = False
) -> m.MissionTimeline:
    stmt = select(m.MissionTimeline).where(
        m.MissionTimeline.id == timeline_id, m.MissionTimeline.session_id == session_id
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"timeline '{timeline_id}' not found", code="timeline_not_found")
    return row


async def list_timelines(db: AsyncSession, session_id: str) -> Sequence[m.MissionTimeline]:
    stmt = (
        select(m.MissionTimeline)
        .where(m.MissionTimeline.session_id == session_id)
        .order_by(m.MissionTimeline.created_at, m.MissionTimeline.id)
    )
    return (await db.execute(stmt)).scalars().all()


async def latest_snapshot(db: AsyncSession, timeline_id: str) -> m.MissionSnapshot:
    stmt = (
        select(m.MissionSnapshot)
        .where(m.MissionSnapshot.timeline_id == timeline_id)
        .order_by(m.MissionSnapshot.tick.desc(), m.MissionSnapshot.decisions_applied.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise IntegrityFailure("timeline has no snapshot", code="snapshot_missing")
    return row


async def head_state(db: AsyncSession, timeline: m.MissionTimeline) -> MissionState:
    snap = await latest_snapshot(db, timeline.id)
    state = MissionState.model_validate(snap.state)
    if state.state_hash() != timeline.head_state_hash or snap.state_hash != state.state_hash():
        raise IntegrityFailure(
            "stored head state does not match its hash", code="state_hash_mismatch"
        )
    return state


def to_record(row: m.MissionDecision, *, include_states: bool = False) -> DecisionRecord:
    return DecisionRecord(
        decision_id=row.decision_id,
        session_id=row.session_id,
        timeline_id=row.timeline_id,
        sequence=row.sequence,
        tick=row.tick,
        decision_type=row.decision_type,
        inputs=row.inputs,
        phase=row.phase,
        affected_systems=tuple(row.affected_systems),
        state_before_hash=row.state_before_hash,
        state_after_hash=row.state_after_hash,
        prev_record_hash=row.prev_record_hash,
        record_hash=row.record_hash,
        metadata=row.meta,
        state_before=row.state_before if include_states else None,
        state_after=row.state_after if include_states else None,
    )


async def own_records(db: AsyncSession, timeline_id: str) -> list[DecisionRecord]:
    stmt = (
        select(m.MissionDecision)
        .where(m.MissionDecision.timeline_id == timeline_id)
        .order_by(m.MissionDecision.sequence)
    )
    return [to_record(r) for r in (await db.execute(stmt)).scalars().all()]


def to_spec(row: m.MissionTimeline) -> TimelineSpec:
    return TimelineSpec(
        timeline_id=row.id,
        parent_timeline_id=row.parent_timeline_id,
        fork_sequence=row.fork_sequence,
        fork_tick=row.fork_tick,
    )


async def effective_records(
    db: AsyncSession, session_id: str, timeline: m.MissionTimeline
) -> list[DecisionRecord]:
    """Effective ledger for a timeline (ancestors truncated at their fork points)."""
    specs = {t.id: to_spec(t) for t in await list_timelines(db, session_id)}
    chain_ids = [timeline.id]
    while specs[chain_ids[-1]].parent_timeline_id is not None:
        parent_id = specs[chain_ids[-1]].parent_timeline_id
        if parent_id not in specs or len(chain_ids) > 64:
            raise IntegrityFailure("broken timeline ancestry", code="timeline_ancestry")
        chain_ids.append(parent_id)
    own = {tid: await own_records(db, tid) for tid in chain_ids}
    try:
        return effective_ledger(specs[timeline.id], specs.__getitem__, own.__getitem__)
    except (TimelineError, KeyError) as exc:
        raise IntegrityFailure("broken timeline ancestry", code="timeline_ancestry") from exc


# ----------------------------------------------------------------------------- Phase 4
async def participants(db: AsyncSession, session_id: str) -> Sequence[m.MissionParticipant]:
    stmt = (
        select(m.MissionParticipant)
        .where(m.MissionParticipant.session_id == session_id)
        .order_by(m.MissionParticipant.joined_at, m.MissionParticipant.handle)
    )
    return (await db.execute(stmt)).scalars().all()


async def previous_state(db: AsyncSession, timeline_id: str, tick: int) -> MissionState | None:
    """The most recent *recorded* state of a timeline before ``tick`` (for trends)."""
    row = (
        await db.execute(
            select(m.MissionSnapshot)
            .where(m.MissionSnapshot.timeline_id == timeline_id, m.MissionSnapshot.tick < tick)
            .order_by(m.MissionSnapshot.tick.desc(), m.MissionSnapshot.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return MissionState.model_validate(row.state) if row is not None else None


async def recorded_states(db: AsyncSession, timeline_id: str) -> list[MissionState]:
    """Every persisted state of one timeline, oldest first (the known past)."""
    rows = (
        await db.execute(
            select(m.MissionSnapshot)
            .where(m.MissionSnapshot.timeline_id == timeline_id)
            .order_by(m.MissionSnapshot.tick, m.MissionSnapshot.id)
        )
    ).scalars()
    return [MissionState.model_validate(r.state) for r in rows]


async def branches(db: AsyncSession, session_id: str) -> Sequence[m.MissionTimelineBranch]:
    stmt = select(m.MissionTimelineBranch).where(m.MissionTimelineBranch.session_id == session_id)
    return (await db.execute(stmt)).scalars().all()


async def outcomes(db: AsyncSession, session_id: str) -> Sequence[m.MissionOutcome]:
    stmt = select(m.MissionOutcome).where(m.MissionOutcome.session_id == session_id)
    return (await db.execute(stmt)).scalars().all()


async def realtime_events_after(
    db: AsyncSession, timeline_id: str, state_version: int, seq: int, limit: int
) -> list[m.MissionRealtimeEvent]:
    """Retained realtime events of a timeline strictly after ``(state_version, seq)``."""
    stmt = (
        select(m.MissionRealtimeEvent)
        .where(
            m.MissionRealtimeEvent.timeline_id == timeline_id,
            (m.MissionRealtimeEvent.state_version > state_version)
            | (
                (m.MissionRealtimeEvent.state_version == state_version)
                & (m.MissionRealtimeEvent.seq > seq)
            ),
        )
        .order_by(m.MissionRealtimeEvent.state_version, m.MissionRealtimeEvent.seq)
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars())


async def realtime_event(db: AsyncSession, event_id: str) -> m.MissionRealtimeEvent | None:
    stmt = select(m.MissionRealtimeEvent).where(m.MissionRealtimeEvent.event_id == event_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def oldest_retained_version(db: AsyncSession, timeline_id: str) -> int | None:
    stmt = select(func.min(m.MissionRealtimeEvent.state_version)).where(
        m.MissionRealtimeEvent.timeline_id == timeline_id
    )
    value = (await db.execute(stmt)).scalar_one_or_none()
    return int(value) if value is not None else None
