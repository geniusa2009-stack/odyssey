"""FastAPI dependencies of the game API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.container import Container
from app.api.deps import get_container, get_db
from app.game.application.runtime import GameRuntime
from app.game.application.service import GameService

# Documented in the game OpenAPI document as the "GameSessionToken" bearer scheme. auto_error is
# off so a missing/invalid token yields the standard PERMISSION_DENIED envelope from the service.
_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="GameSessionToken",
    description="The session token returned once by POST /sessions (gst_…).",
)


def get_game_runtime(request: Request) -> GameRuntime:
    runtime: GameRuntime = request.app.state.game_runtime
    return runtime


def get_game_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    container: Annotated[Container, Depends(get_container)],
    runtime: Annotated[GameRuntime, Depends(get_game_runtime)],
) -> GameService:
    return GameService(db, container, runtime)


def session_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str | None:
    return credentials.credentials if credentials is not None else None


def game_principal(
    request: Request, runtime: Annotated[GameRuntime, Depends(get_game_runtime)]
) -> str:
    """Identity seam: the caller's principal (always "anonymous" until accounts exist)."""
    return runtime.identity.principal(request.headers.get("authorization"))
