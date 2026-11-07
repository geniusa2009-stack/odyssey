"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.container import Container, build_container
from app.api.errors import install_error_handlers
from app.api.security import BodySizeLimitMiddleware, RequestContextMiddleware
from app.api.v1 import routes, ws
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.models import Base
from app.game.api.app import GAME_API_PREFIX, build_game_runtime, create_game_app
from app.game.application.reference import sync_game_reference_data
from app.game.application.runtime import GameRuntime
from app.services.reference_data import sync_reference_data

log = logging.getLogger("odyssey")


def create_app(
    settings: Settings | None = None,
    container: Container | None = None,
    game_runtime: GameRuntime | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    # odyssey.game.v1 is a separately versioned sub-application (own OpenAPI document, own
    # snapshot); mounting it keeps the frozen API v1 schema byte-identical.
    game_app = create_game_app(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        c = container or build_container(settings)
        app.state.container = c
        if settings.auto_create_schema:
            async with c.db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        rt = game_runtime or build_game_runtime(c)
        game_app.state.container = c
        game_app.state.game_runtime = rt
        try:
            async with c.session_factory() as db:
                await sync_reference_data(db)
            async with c.session_factory() as db:
                await sync_game_reference_data(db, rt.content)
        except Exception:
            log.exception("reference_data_sync_failed", extra={"error_code": "reference_sync"})
            raise
        log.info("startup", extra={"event_type": "startup"})
        try:
            yield
        finally:
            await rt.bus.close()
            await c.close()

    app = FastAPI(
        title="ODYSSEY Backend",
        version=__version__,
        description="Deterministic lunar mission simulation API (LUNA-01 — The Last Light).",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    install_error_handlers(app)

    @app.middleware("http")
    async def _access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        log.info(
            "request",
            extra={
                "event_type": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return response

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key"],
            expose_headers=["X-Request-ID", "Idempotent-Replayed"],
            allow_credentials=False,
        )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(routes.router)
    app.include_router(ws.router)
    app.mount(GAME_API_PREFIX, game_app)
    return app


app = create_app()
