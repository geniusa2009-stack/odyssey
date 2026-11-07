"""Game persistence (``odyssey.game.v1``): additive tables, no change to existing ones.

* ``game_profiles``        — the player identity seam (no account platform yet).
* ``game_sessions``        — one campaign: content version/hash, campaign meta document,
  authoritative ``state_version`` (optimistic concurrency), realtime ``event_seq``, the hash of
  the session token, and the secret seed (never exposed).
* ``game_timelines``       — one play-through of one mission; points at its simulation session
  and timeline (``mission_sessions``/``mission_timelines``) and holds the head timeline document.
* ``game_state_snapshots`` — timeline documents captured right before simulation decisions
  (rewind anchors) and at transitions.
* ``game_checkpoints``     — saves: automatic, mission transition, critical decision, incident
  resolution and manual; each holds the timeline document *and* campaign meta at that version.
* ``game_commands``        — accepted commands (id, action, target, server time, decision ids):
  the recorded timing that makes the clock deterministic, and a duplicate-command guard.
* ``game_events``          — retained realtime envelopes for resume (bounded per session).

Public ids are opaque prefixed strings (``gs_``, ``gt_``, ``ck_``, ``gp_``); no autoincrement
database id ever leaves the backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, JSONType

_BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GameProfile(Base):
    __tablename__ = "game_profiles"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    principal: Mapped[str] = mapped_column(String(64), default="anonymous")
    created_at: Mapped[datetime] = _now()


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("game_profiles.id"), index=True)
    content_id: Mapped[str] = mapped_column(String(64))
    content_version: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(BigInteger)
    token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONType)
    active_timeline_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    event_seq: Mapped[int] = mapped_column(Integer, default=0)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Application-managed optimistic version: the service sets state_version = prev + 1 exactly
    # once per authoritative mutation; every UPDATE is guarded by WHERE state_version = <read>,
    # so a concurrent writer that read the same version fails (StaleDataError → STALE_STATE).
    __mapper_args__ = {"version_id_col": state_version, "version_id_generator": False}


class GameTimeline(Base):
    __tablename__ = "game_timelines"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    mission_id: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    sim_session_id: Mapped[str] = mapped_column(ForeignKey("mission_sessions.id"))
    sim_timeline_id: Mapped[str] = mapped_column(ForeignKey("mission_timelines.id"))
    parent_timeline_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fork_command_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    doc: Mapped[dict[str, Any]] = mapped_column(JSONType)
    doc_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GameStateSnapshot(Base):
    __tablename__ = "game_state_snapshots"
    __table_args__ = (
        Index("ix_game_state_snapshots_timeline_command", "timeline_id", "command_id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"))
    timeline_id: Mapped[str] = mapped_column(ForeignKey("game_timelines.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    command_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sim_tick: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class GameCheckpoint(Base):
    __tablename__ = "game_checkpoints"
    __table_args__ = (Index("ix_game_checkpoints_session_created", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"))
    timeline_id: Mapped[str] = mapped_column(ForeignKey("game_timelines.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    label: Mapped[str] = mapped_column(String(64))
    mission_id: Mapped[str] = mapped_column(String(64))
    state_version: Mapped[int] = mapped_column(Integer)
    sim_tick: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(128))
    doc: Mapped[dict[str, Any]] = mapped_column(JSONType)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class GameCommand(Base):
    __tablename__ = "game_commands"
    __table_args__ = (UniqueConstraint("session_id", "command_id"),)

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"))
    timeline_id: Mapped[str] = mapped_column(String(40))
    command_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(48))
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str] = mapped_column(String(16))
    server_time_ms: Mapped[int] = mapped_column(BigInteger)
    state_version: Mapped[int] = mapped_column(Integer)
    decision_ids: Mapped[list[str]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()


class GameEvent(Base):
    __tablename__ = "game_events"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String(80), unique=True)
    timeline_id: Mapped[str] = mapped_column(String(40))
    state_version: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(48))
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now()
