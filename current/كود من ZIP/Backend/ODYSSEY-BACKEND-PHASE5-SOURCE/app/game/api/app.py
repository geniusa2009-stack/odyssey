"""The ``odyssey.game.v1`` sub-application.

Mounted by :func:`app.main.create_app` at :data:`GAME_API_PREFIX`. It is a separate FastAPI
application so that

* it has its **own OpenAPI document** (``/api/game/v1/openapi.json``) and its own frozen
  snapshot (``tests/fixtures/game/openapi-game-v1.json``), and
* the frozen API v1 OpenAPI document stays byte-identical (mounted apps are not part of it).

It shares the parent's container, middleware (request id, body size limit, access log, CORS)
and the exact same error envelope (``app/api/errors.py``). Its state (container and
:class:`~app.game.application.runtime.GameRuntime`) is set by the parent lifespan.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.container import Container
from app.api.errors import install_error_handlers
from app.core.config import Settings
from app.game import GAME_PROTOCOL
from app.game.api import routes, ws
from app.game.application.identity import AnonymousIdentityProvider
from app.game.application.runtime import GameRuntime
from app.game.content.loader import default_content
from app.game.realtime.bus import GameBus, InMemoryGameBus, RedisGameBus
from app.game.runtime.clock import SystemClock

GAME_API_PREFIX = "/api/game/v1"

DESCRIPTION = """\
Authoritative mission/campaign backend for the ODYSSEY Unreal Engine client
(protocol **odyssey.game.v1**). Unreal owns movement, physics, animation and presentation; the
client sends *semantic* actions and the backend decides results. See
docs/UNREAL_BACKEND_CONTRACT.md and docs/UNREAL_HANDOFF.md.
"""


def create_game_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="ODYSSEY Game API",
        version=GAME_PROTOCOL,
        description=DESCRIPTION,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    install_error_handlers(app)
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


def build_game_runtime(container: Container) -> GameRuntime:
    """Zero-cost defaults: in-process bus unless Redis is configured (then fan-out via Redis)."""
    bus: GameBus = (
        RedisGameBus(container.redis) if container.redis is not None else InMemoryGameBus()
    )
    return GameRuntime(
        content=default_content(),
        bus=bus,
        clock=SystemClock(),
        identity=AnonymousIdentityProvider(),
    )
