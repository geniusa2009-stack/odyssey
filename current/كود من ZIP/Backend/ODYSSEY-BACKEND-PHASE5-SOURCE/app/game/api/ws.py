"""Game realtime WebSocket (``odyssey.game.v1``): ``/api/game/v1/ws/sessions/{session_id}``.

Query parameters: ``token`` (the session token; an ``Authorization: Bearer`` header also works)
and optionally ``last_seq`` (the last event seq the client applied).

Connection sequence (docs/GAME_REALTIME_PROTOCOL.md):

1. Validate the session id, origin and token, then subscribe to the session channel *before*
   reading the backlog, so nothing committed during the handshake can be missed.
2. No ``last_seq``: send ``CONNECTED`` (current ``state_version``/``last_seq``); the client loads
   the snapshot (or calls /restore).
3. With ``last_seq``: send ``RESUMED`` and the retained events after it, in order, or
   ``RESYNC_REQUIRED`` (events expired / unknown position) with the restore path.
4. Live events follow, strictly in ``seq`` order without gaps: duplicates are dropped and a gap
   (a message lost by the bus) is back-filled from the database; if the gap has expired the
   server sends ``RESYNC_REQUIRED``.

The only client frame understood is ``{"type": "ping"}`` (answered with ``PONG``). Commands go
through REST (single write path). The server never expects per-frame data.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.container import Container
from app.api.v1.ws import POLICY_VIOLATION, is_ping
from app.core.errors import AppError
from app.game.application.identity import bearer
from app.game.application.runtime import GameRuntime
from app.game.application.service import GameService
from app.game.contracts.protocol import GameControlFrame, GameEventEnvelope
from app.game.realtime.bus import game_channel

log = logging.getLogger(__name__)
router = APIRouter()
_SESSION_ID = re.compile(r"^gs_[a-z2-7]{20,32}$")


def _int(raw: str | None) -> int | None:
    if raw is None or not raw.isdigit() or len(raw) > 10:
        return None
    return int(raw)


@router.websocket("/ws/sessions/{session_id}")
async def game_socket(websocket: WebSocket, session_id: str) -> None:
    container: Container = websocket.app.state.container
    runtime: GameRuntime = websocket.app.state.game_runtime
    if not _SESSION_ID.match(session_id):
        await websocket.close(code=POLICY_VIOLATION)
        return
    origin = websocket.headers.get("origin")
    allowed = container.settings.cors_origins
    if origin and allowed and origin not in allowed and "*" not in allowed:
        await websocket.close(code=POLICY_VIOLATION)
        return
    params = websocket.query_params
    token = params.get("token") or bearer(websocket.headers.get("authorization"))
    raw_seq = params.get("last_seq")
    last_seq = _int(raw_seq)
    if raw_seq is not None and last_seq is None:
        await websocket.close(code=POLICY_VIOLATION)
        return
    restore_path = f"/api/game/v1/sessions/{session_id}/restore"

    async with runtime.bus.subscribe(game_channel(session_id)) as messages:
        async with container.session_factory() as db:
            service = GameService(db, container, runtime)
            try:
                sess = await service._session(session_id, token)
                version, current_seq = sess.state_version, sess.event_seq
                page = (
                    await service.events(session_id, token, after_seq=last_seq, limit=500)
                    if last_seq is not None
                    else None
                )
            except AppError:
                await websocket.close(code=POLICY_VIOLATION)
                return
        await websocket.accept()
        if page is None:
            sent = current_seq
            frame = GameControlFrame(
                type="CONNECTED",
                session_id=session_id,
                state_version=version,
                last_seq=current_seq,
                restore_path=restore_path,
            )
            await websocket.send_text(frame.model_dump_json())
        elif page.resync_required or page.has_more:
            sent = page.last_seq
            await websocket.send_text(
                GameControlFrame(
                    type="RESYNC_REQUIRED",
                    session_id=session_id,
                    state_version=version,
                    last_seq=page.last_seq,
                    reason="events_expired" if page.resync_required else "backlog_too_large",
                    restore_path=restore_path,
                ).model_dump_json()
            )
        else:
            await websocket.send_text(
                GameControlFrame(
                    type="RESUMED",
                    session_id=session_id,
                    state_version=version,
                    last_seq=page.last_seq,
                    replayed=len(page.events),
                    restore_path=restore_path,
                ).model_dump_json()
            )
            for ev in page.events:
                await websocket.send_text(ev.model_dump_json())
            sent = page.events[-1].seq if page.events else page.after_seq

        async def backfill(after: int, upto: int) -> int:
            """Send retained events (after, upto) from the database; returns the new position,
            or -1 when they expired (the client must restore)."""
            async with container.session_factory() as db:
                svc = GameService(db, container, runtime)
                pg = await svc.events(session_id, token, after_seq=after, limit=500)
            if pg.resync_required:
                return -1
            pos = after
            for ev in pg.events:
                if ev.seq >= upto:
                    break
                await websocket.send_text(ev.model_dump_json())
                pos = ev.seq
            return pos

        async def pump() -> None:
            nonlocal sent
            async for message in messages:
                env: GameEventEnvelope = message
                if env.seq <= sent:
                    continue  # already delivered (backlog or back-fill)
                if env.seq > sent + 1:
                    pos = await backfill(sent, env.seq)
                    if pos < 0 or pos != env.seq - 1:
                        await websocket.send_text(
                            GameControlFrame(
                                type="RESYNC_REQUIRED",
                                session_id=session_id,
                                last_seq=env.seq,
                                reason="events_expired",
                                restore_path=restore_path,
                            ).model_dump_json()
                        )
                        sent = env.seq
                        continue
                await websocket.send_text(env.model_dump_json())
                sent = env.seq

        async def listen() -> None:
            while True:
                frame = await websocket.receive_text()
                if is_ping(frame):
                    await websocket.send_text(
                        GameControlFrame(type="PONG", session_id=session_id).model_dump_json()
                    )

        tasks = [asyncio.create_task(pump()), asyncio.create_task(listen())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect):
                    log.warning("game_websocket_error", extra={"error_code": type(exc).__name__})
        finally:
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
