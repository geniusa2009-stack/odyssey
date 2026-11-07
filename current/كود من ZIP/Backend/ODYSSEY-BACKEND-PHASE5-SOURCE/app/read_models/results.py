"""Results of commands (decision, advance) and the realtime resume page."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.read_models.analysis import DecisionEntryView
from app.read_models.common import View
from app.read_models.events import EventView
from app.read_models.mission import MissionHUD, OutcomeView
from app.realtime.contract import RealtimeEvent

ResyncReason = Literal[
    "events_expired",
    "timeline_changed",
    "unknown_timeline",
    "unknown_position",
    "too_many_events",
    "events_unavailable",
]


class DecisionResultView(View):
    accepted: bool = True
    session_id: str
    timeline_id: str
    state_version: int
    prev_state_version: int
    tick: int
    decision: DecisionEntryView
    hud: MissionHUD
    events: list[EventView]
    events_truncated: bool


class AdvanceResultView(View):
    session_id: str
    timeline_id: str
    state_version: int
    prev_state_version: int
    from_tick: int
    to_tick: int
    ticks_run: int
    concluded: bool
    phase: str
    outcome: OutcomeView | None
    hud: MissionHUD
    events: list[EventView]
    events_truncated: bool


class EventsPage(View):
    """Retained realtime events after a cursor, or the instruction to re-fetch the snapshot."""

    session_id: str
    timeline_id: str
    state_version: int
    resync_required: bool
    reason: ResyncReason | None = None
    snapshot_path: str
    events: list[RealtimeEvent] = Field(default_factory=list)
