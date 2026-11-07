"""SQLAlchemy ORM models (persistence only — no simulation logic here).

Persistence strategy:
* The **decision ledger** (``mission_decisions``) is the durable source of truth, append-only
  and hash-chained. Updates/deletes are blocked by an ORM guard *and* by database triggers
  (:mod:`app.db.ledger_guard`).
* **Snapshots** store full states at decision points, advance boundaries and every N ticks so
  reads never need replay. Every tick is *not* persisted; any tick can be reconstructed.
* **Events** are an append-only log for timelines/realtime; they are derivable by replay.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db import ledger_guard

JSONType = JSON().with_variant(JSONB(), "postgresql")

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType, list[str]: JSONType}


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # NULL = a v1 mission; "game" = a scenario owned by the game backend (hidden from v1).
    managed_by: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    created_at: Mapped[datetime] = _now()


class MissionScenario(Base):
    """A pinned scenario version (content-hashed) so old sessions stay replayable."""

    __tablename__ = "mission_scenarios"
    __table_args__ = (UniqueConstraint("scenario_key", "version", "content_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    scenario_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class MissionSession(Base):
    __tablename__ = "mission_sessions"
    __table_args__ = (Index("ix_mission_sessions_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("mission_scenarios.id"), index=True)
    seed: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="active")
    active_timeline_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    future_lens_requests: Mapped[int] = mapped_column(Integer, default=0)
    # NULL = a v1 session; "game" = owned by the game backend (invisible to the v1 API).
    managed_by: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MissionParticipant(Base):
    __tablename__ = "mission_participants"
    __table_args__ = (UniqueConstraint("session_id", "handle"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mission_sessions.id", ondelete="CASCADE"), index=True
    )
    handle: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    joined_at: Mapped[datetime] = _now()


class MissionTimeline(Base):
    __tablename__ = "mission_timelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mission_sessions.id", ondelete="CASCADE"), index=True
    )
    parent_timeline_id: Mapped[str | None] = mapped_column(
        ForeignKey("mission_timelines.id"), nullable=True, index=True
    )
    fork_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fork_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    head_tick: Mapped[int] = mapped_column(Integer, default=0)
    head_sequence: Mapped[int] = mapped_column(Integer, default=0)
    head_state_hash: Mapped[str] = mapped_column(String(64))
    head_record_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": version}


class MissionTimelineBranch(Base):
    """Fork record: which decision was replaced, and by what, to create a child timeline."""

    __tablename__ = "mission_timeline_branches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mission_sessions.id", ondelete="CASCADE"), index=True
    )
    parent_timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"), index=True)
    child_timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"), unique=True)
    replaced_decision_id: Mapped[str] = mapped_column(String(40))
    alternative_inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    participant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = _now()


class MissionDecision(Base):
    """Append-only ledger entry. Never updated or deleted."""

    __tablename__ = "mission_decisions"
    __table_args__ = (
        UniqueConstraint("timeline_id", "sequence"),
        Index("ix_mission_decisions_timeline_tick", "timeline_id", "tick"),
    )

    decision_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mission_sessions.id", ondelete="CASCADE"), index=True
    )
    # Indexed through the (timeline_id, sequence) unique constraint.
    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    tick: Mapped[int] = mapped_column(Integer)
    decision_type: Mapped[str] = mapped_column(String(48))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONType)
    phase: Mapped[str] = mapped_column(String(64))
    affected_systems: Mapped[list[str]] = mapped_column(JSONType)
    state_before: Mapped[dict[str, Any]] = mapped_column(JSONType)
    state_after: Mapped[dict[str, Any]] = mapped_column(JSONType)
    state_before_hash: Mapped[str] = mapped_column(String(64))
    state_after_hash: Mapped[str] = mapped_column(String(64))
    prev_record_hash: Mapped[str] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64), unique=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    participant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = _now()


class MissionEvent(Base):
    __tablename__ = "mission_events"
    __table_args__ = (
        UniqueConstraint("timeline_id", "event_id"),
        Index("ix_mission_events_timeline_tick", "timeline_id", "tick"),
        Index("ix_mission_events_timeline_kind", "timeline_id", "kind"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mission_sessions.id", ondelete="CASCADE"), index=True
    )
    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    event_id: Mapped[str] = mapped_column(String(160))
    tick: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class MissionSnapshot(Base):
    __tablename__ = "mission_snapshots"
    __table_args__ = (
        # Also serves "latest snapshot of a timeline" (ORDER BY tick DESC, decisions_applied DESC).
        UniqueConstraint("timeline_id", "tick", "decisions_applied"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    tick: Mapped[int] = mapped_column(Integer)
    decisions_applied: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict[str, Any]] = mapped_column(JSONType)
    state_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _now()


class MissionOutcome(Base):
    __tablename__ = "mission_outcomes"

    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("mission_sessions.id", ondelete="CASCADE"), index=True
    )
    outcome_code: Mapped[str] = mapped_column(String(48), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(64))
    objectives_achieved: Mapped[list[str]] = mapped_column(JSONType)
    objectives_failed: Mapped[list[str]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class MissionProfile(Base):
    __tablename__ = "mission_profiles"
    __table_args__ = (UniqueConstraint("timeline_id", "weights_version", "head_state_hash"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    # Indexed through the unique constraint (timeline_id is its leading column).
    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    weights_version: Mapped[str] = mapped_column(String(32))
    head_state_hash: Mapped[str] = mapped_column(String(64))
    profile: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class MissionDNARecord(Base):
    __tablename__ = "mission_dna"
    __table_args__ = (UniqueConstraint("timeline_id", "head_state_hash"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    # Indexed through the unique constraint (timeline_id is its leading column).
    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    head_state_hash: Mapped[str] = mapped_column(String(64))
    dna_code: Mapped[str] = mapped_column(String(48), index=True)
    dna_version: Mapped[int] = mapped_column(Integer)
    genes: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class ScienceEvidenceRecord(Base):
    __tablename__ = "science_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    concept: Mapped[str] = mapped_column(String(200))
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_name: Mapped[str] = mapped_column(Text)
    source_citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_date: Mapped[str] = mapped_column(String(10))
    verification_status: Mapped[str] = mapped_column(String(24), index=True)
    simulation_usage: Mapped[list[str]] = mapped_column(JSONType)
    simplification: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(8))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class NASASourceRecord(Base):
    __tablename__ = "nasa_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_name: Mapped[str] = mapped_column(Text)
    dataset: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    license_notes: Mapped[str] = mapped_column(Text)
    variables_used: Mapped[list[str]] = mapped_column(JSONType)
    transformation_notes: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16))
    is_real_data: Mapped[bool] = mapped_column(Boolean)


class SimulationRun(Base):
    """Audit/telemetry row for every engine invocation that served a request."""

    __tablename__ = "simulation_runs"
    __table_args__ = (Index("ix_simulation_runs_session_created", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("mission_sessions.id", ondelete="CASCADE"))
    timeline_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    from_tick: Mapped[int] = mapped_column(Integer)
    to_tick: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[float] = mapped_column(Float)
    state_hash_out: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _now()


class MissionRealtimeEvent(Base):
    """Retained realtime envelopes (``odyssey.realtime.v1``) for reconnect/resume.

    Written in the same transaction as the state change they describe, published after
    commit. Only the most recent ``realtime_retained_versions`` state versions per timeline are
    kept; older positions answer "resync required". Derivable state, not a source of truth.
    """

    __tablename__ = "mission_realtime_events"
    __table_args__ = (
        UniqueConstraint("timeline_id", "state_version", "seq"),
        Index("ix_mission_realtime_events_session_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("mission_sessions.id", ondelete="CASCADE"))
    timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    state_version: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String(80), unique=True)
    type: Mapped[str] = mapped_column(String(32))
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class IdempotencyRecord(Base):
    """Stored response of an idempotent mutation (``Idempotency-Key`` header).

    Inserted in the same transaction as the mutation, so a retry either finds the committed
    response or finds nothing (the mutation did not happen). ``principal`` is the auth seam:
    "anonymous" until authentication exists, then the caller's identity.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("principal", "scope", "session_key", "idempotency_key"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    principal: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(32))
    session_key: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class LedgerImmutableError(RuntimeError):
    pass


@event.listens_for(MissionDecision, "before_update")
def _block_decision_update(*_: object) -> None:
    raise LedgerImmutableError("mission_decisions is append-only")


@event.listens_for(MissionDecision, "before_delete")
def _block_decision_delete(*_: object) -> None:
    raise LedgerImmutableError("mission_decisions is append-only")


ledger_guard.install(MissionDecision.__table__)  # type: ignore[arg-type]

# Game backend tables (odyssey.game.v1) share this metadata so Alembic and create_all see them.
from app.game.persistence import models as _game_models  # noqa: E402, F401
