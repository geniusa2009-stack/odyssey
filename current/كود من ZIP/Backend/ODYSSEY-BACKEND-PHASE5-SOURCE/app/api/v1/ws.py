"""WebSocket endpoint for live mission updates (server → client), contract odyssey.realtime.v1.

``/api/v1/ws/mission-sessions/{session_id}`` — optional resume query parameters:

* ``last_event_id`` — the last event the client applied, or
* ``last_state_version`` (+ optional ``timeline_id``, ``last_seq``).

Connection sequence:

1. The server subscribes to the session channel *before* reading anything, so no event committed
   during the handshake can be missed.
2. Without resume parameters it sends a ``CONNECTED`` control frame (current timeline, state
   version and tick); the client then loads ``GET .../snapshot``.
3. With resume parameters it either sends ``RESUMED`` (``replayed`` = number of retained events
   that follow) and then those events in order, or ``RESYNC_REQUIRED`` with a reason (events
   expired, timeline changed, unknown position) — the client then re-fetches the snapshot.
4. Live events follow. Events already sent from the backlog are skipped (dedupe by
   ``(timeline_id, state_version, seq)``).

The only client → server frame understood is ``{"type": "ping"}`` (answered with a ``PONG``
control frame); anything else, including oversized or malformed frames, is ignored. Commands go
through the REST API (single write path).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.container import Container
from app.core.errors import AppError
from app.realtime.bus import session_channel
from app.realtime.contract import RealtimeControl, RealtimeEvent
from app.services.contract_service import ContractService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")
MAX_CLIENT_FRAME = 1024
_SESSION_ID = re.compile(r"^[0-9a-fA-F\-]{1,36}$")
_EVENT_ID = re.compile(r"^[0-9a-fA-F\-]{1,36}:\d{1,9}:(\d{1,6}|aux:[0-9a-f]{16})$")
POLICY_VIOLATION = 1008


def is_ping(frame: str) -> bool:
    """True for a well-formed ``{"type": "ping"}`` frame (whitespace/key order irrelevant)."""
    if len(frame) > MAX_CLIENT_FRAME:
        return False
    try:
        data = json.loads(frame)
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("type") == "ping"


def _int_param(raw: str | None) -> int | None:
    if raw is None or not raw.lstrip("-").isdigit() or len(raw) > 10:
        return None
    return int(raw)


@router.websocket("/ws/mission-sessions/{session_id}")
async def mission_socket(websocket: WebSocket, session_id: str) -> None:
    container: Container = websocket.app.state.container
    if not _SESSION_ID.match(session_id):
        await websocket.close(code=POLICY_VIOLATION)
        return
    origin = websocket.headers.get("origin")
    allowed = container.settings.cors_origins
    if origin and allowed and origin not in allowed and "*" not in allowed:
        await websocket.close(code=POLICY_VIOLATION)
        return
    params = websocket.query_params
    last_event_id = params.get("last_event_id")
    if last_event_id is not None and not _EVENT_ID.match(last_event_id):
        await websocket.close(code=POLICY_VIOLATION)
        return
    last_version = _int_param(params.get("last_state_version"))
    last_seq = _int_param(params.get("last_seq"))
    resume_tl = params.get("timeline_id")
    if resume_tl is not None and not _SESSION_ID.match(resume_tl):
        await websocket.close(code=POLICY_VIOLATION)
        return
    resuming = last_event_id is not None or last_version is not None

    async with container.bus.subscribe(session_channel(session_id)) as messages:
        async with container.session_factory() as db:
            service = ContractService(
                db,
                container.settings,
                container.engines,
                container.bus,
                container.orion,
                container.policy,
            )
            try:
                ld = await service._load(session_id, None)
                page = (
                    await service.events_after(
                        session_id,
                        last_event_id=last_event_id,
                        timeline_id=resume_tl,
                        last_state_version=last_version,
                        last_seq=last_seq,
                    )
                    if resuming
                    else None
                )
            except AppError:
                await websocket.close(code=POLICY_VIOLATION)
                return
            timeline_id, version, tick = ld.timeline.id, ld.timeline.version, ld.timeline.head_tick
        await websocket.accept()
        snapshot_path = f"/api/v1/mission-sessions/{session_id}/snapshot"
        sent: dict[str, tuple[int, int]] = {}
        if page is None:
            control = RealtimeControl(
                type="CONNECTED",
                session_id=session_id,
                timeline_id=timeline_id,
                state_version=version,
                sim_tick=tick,
                snapshot_path=snapshot_path,
            )
            sent[timeline_id] = (version, 10**9)
            await websocket.send_text(control.model_dump_json())
        elif page.resync_required:
            await websocket.send_text(
                RealtimeControl(
                    type="RESYNC_REQUIRED",
                    session_id=session_id,
                    timeline_id=page.timeline_id,
                    state_version=page.state_version,
                    reason=page.reason,
                    snapshot_path=snapshot_path,
                ).model_dump_json()
            )
            sent[page.timeline_id] = (page.state_version, 10**9)
        else:
            await websocket.send_text(
                RealtimeControl(
                    type="RESUMED",
                    session_id=session_id,
                    timeline_id=page.timeline_id,
                    state_version=page.state_version,
                    replayed=len(page.events),
                    snapshot_path=snapshot_path,
                ).model_dump_json()
            )
            for ev in page.events:
                await websocket.send_text(ev.model_dump_json())
            last_sent = (
                (page.events[-1].state_version, page.events[-1].seq) if page.events else (0, 0)
            )
            # A transition may have committed between the version read and the backlog read.
            sent[page.timeline_id] = max((page.state_version, 10**9), last_sent)

        def duplicate(ev: RealtimeEvent) -> bool:
            if ev.seq < 0:  # auxiliary events are never replayed, so never duplicated
                return False
            last = sent.get(ev.timeline_id)
            return last is not None and (ev.state_version, ev.seq) <= last

        async def pump() -> None:
            async for message in messages:
                if duplicate(message):
                    continue
                await websocket.send_text(message.model_dump_json())

        async def listen() -> None:
            while True:
                frame = await websocket.receive_text()
                if is_ping(frame):
                    await websocket.send_text(
                        RealtimeControl(type="PONG", session_id=session_id).model_dump_json()
                    )

        tasks = [asyncio.create_task(pump()), asyncio.create_task(listen())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect):
                    log.warning("websocket_error", extra={"error_code": type(exc).__name__})
        finally:
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
