"""Frozen realtime contract ``odyssey.realtime.v1`` (docs/API_CONTRACT.md#realtime).

Every committed state transition becomes one ordered *group* of events sharing a
``state_version``:

1. ``TIMELINE_CHANGED`` (a new timeline was created) — optional
2. ``DECISION_ACCEPTED`` (the transition applied a decision) — optional
3. the engine events of the transition, in emission order, as ``SYSTEM_ALERT``,
   ``PHASE_CHANGED``, ``OBJECTIVE_UPDATED`` or ``MISSION_EVENT`` (at most
   :data:`MAX_ENGINE_EVENTS`; the ``decision_applied`` engine event is represented by
   ``DECISION_ACCEPTED``)
4. ``RESOURCE_CHANGED`` (the HUD after the transition)
5. ``MISSION_STATE_CHANGED`` (the transition summary)
6. ``MISSION_COMPLETED`` — when the transition concluded the mission

``seq`` numbers the events of a group from 0; ``event_id`` is
``{timeline_id}:{state_version}:{seq}`` (deterministic and unique). Auxiliary events
(``FUTURE_LENS_READY``, ``ORION_MESSAGE``) change no state: ``seq`` −1, ``seq_count`` 0, a random
id, never retained.

Control frames (``CONNECTED``, ``RESUMED``, ``RESYNC_REQUIRED``, ``PONG``) describe the connection,
not the mission, and carry no ``event_id``.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.read_models.events import event_view
from app.simulation.domain.enums import EventKind
from app.simulation.domain.events import MissionEvent

REALTIME_CONTRACT: Literal["odyssey.realtime.v1"] = "odyssey.realtime.v1"
MAX_ENGINE_EVENTS = 200

RealtimeEventType = Literal[
    "TIMELINE_CHANGED",
    "DECISION_ACCEPTED",
    "SYSTEM_ALERT",
    "PHASE_CHANGED",
    "OBJECTIVE_UPDATED",
    "MISSION_EVENT",
    "RESOURCE_CHANGED",
    "MISSION_STATE_CHANGED",
    "MISSION_COMPLETED",
    "FUTURE_LENS_READY",
    "ORION_MESSAGE",
]
AuxEventType = Literal["FUTURE_LENS_READY", "ORION_MESSAGE"]
ControlType = Literal["CONNECTED", "RESUMED", "RESYNC_REQUIRED", "PONG"]
Cause = Literal["session_created", "decision", "advance", "timeline_created"]

_ALERT_ACTIONS: dict[EventKind, str] = {
    EventKind.ALERT_RAISED: "raised",
    EventKind.ALERT_CLEARED: "cleared",
    EventKind.RESOURCE_WARNING: "warning",
    EventKind.CASCADE_WARNING: "cascade",
}


def server_now() -> str:
    return datetime.now(UTC).isoformat()


class RealtimeEvent(BaseModel):
    """One mission event of the realtime stream (frozen envelope)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["odyssey.realtime.v1"] = REALTIME_CONTRACT
    event_id: str
    type: RealtimeEventType
    session_id: str
    timeline_id: str
    state_version: int
    prev_state_version: int | None = Field(
        description="State version the group was applied to (null for a new timeline)"
    )
    seq: int = Field(description="Position in the group (0…seq_count−1); −1 for auxiliary events")
    seq_count: int
    sim_tick: int
    sim_time_hours: float
    server_time: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RealtimeControl(BaseModel):
    """A connection control frame (no ``event_id``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: Literal["odyssey.realtime.v1"] = REALTIME_CONTRACT
    type: ControlType
    session_id: str
    timeline_id: str | None = None
    state_version: int | None = None
    sim_tick: int | None = None
    replayed: int | None = None
    reason: str | None = None
    snapshot_path: str | None = None


def _engine_event(e: MissionEvent) -> tuple[RealtimeEventType, dict[str, Any]] | None:
    if e.kind == EventKind.DECISION_APPLIED:
        return None
    view = event_view(e).model_dump(mode="json")
    if e.kind in _ALERT_ACTIONS:
        return "SYSTEM_ALERT", {"action": _ALERT_ACTIONS[e.kind], "event": view}
    if e.kind == EventKind.PHASE_CHANGE:
        return "PHASE_CHANGED", {"from": e.data.get("from"), "to": e.data.get("to"), "event": view}
    if e.kind == EventKind.OBJECTIVE:
        return "OBJECTIVE_UPDATED", {
            "objective": e.data.get("objective", e.key),
            "status": e.data.get("status"),
            "category": e.data.get("category"),
            "event": view,
        }
    return "MISSION_EVENT", {"event": view}


def build_transition(
    *,
    session_id: str,
    timeline_id: str,
    state_version: int,
    prev_state_version: int | None,
    tick: int,
    tick_hours: float,
    cause: Cause,
    from_tick: int,
    phase: str,
    status: str,
    state_hash: str,
    engine_events: Sequence[MissionEvent],
    hud: dict[str, Any],
    decision: dict[str, Any] | None = None,
    timeline_change: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
) -> list[RealtimeEvent]:
    """The ordered event group of one committed transition (see module docstring)."""
    items: list[tuple[RealtimeEventType, dict[str, Any]]] = []
    if timeline_change is not None:
        items.append(("TIMELINE_CHANGED", timeline_change))
    if decision is not None:
        items.append(("DECISION_ACCEPTED", {"decision": decision}))
    mapped = [x for x in (_engine_event(e) for e in engine_events) if x is not None]
    truncated = len(mapped) > MAX_ENGINE_EVENTS
    items.extend(mapped[:MAX_ENGINE_EVENTS])
    items.append(("RESOURCE_CHANGED", {"hud": hud}))
    items.append(
        (
            "MISSION_STATE_CHANGED",
            {
                "cause": cause,
                "from_tick": from_tick,
                "tick": tick,
                "phase": phase,
                "status": status,
                "state_hash": state_hash,
                "engine_events": len(mapped),
                "events_truncated": truncated,
            },
        )
    )
    if outcome is not None:
        items.append(("MISSION_COMPLETED", {"outcome": outcome}))
    now = server_now()
    return [
        RealtimeEvent(
            event_id=f"{timeline_id}:{state_version}:{seq}",
            type=etype,
            session_id=session_id,
            timeline_id=timeline_id,
            state_version=state_version,
            prev_state_version=prev_state_version,
            seq=seq,
            seq_count=len(items),
            sim_tick=tick,
            sim_time_hours=round(tick * tick_hours, 3),
            server_time=now,
            payload=payload,
        )
        for seq, (etype, payload) in enumerate(items)
    ]


def aux_event(
    *,
    etype: AuxEventType,
    session_id: str,
    timeline_id: str,
    state_version: int,
    tick: int,
    tick_hours: float,
    payload: dict[str, Any],
) -> RealtimeEvent:
    """An auxiliary event: informational, changes nothing, not retained."""
    return RealtimeEvent(
        event_id=f"{timeline_id}:{state_version}:aux:{secrets.token_hex(8)}",
        type=etype,
        session_id=session_id,
        timeline_id=timeline_id,
        state_version=state_version,
        prev_state_version=state_version,
        seq=-1,
        seq_count=0,
        sim_tick=tick,
        sim_time_hours=round(tick * tick_hours, 3),
        server_time=server_now(),
        payload=payload,
    )
