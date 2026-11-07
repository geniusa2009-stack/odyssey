"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.container import Container
from app.core.errors import NotFoundError, RateLimitedError
from app.services.contract_service import ContractService
from app.services.idempotency import ANONYMOUS
from app.services.mission_service import MissionService


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


async def get_db(container: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        yield session


def get_service(
    db: AsyncSession = Depends(get_db), container: Container = Depends(get_container)
) -> MissionService:
    return MissionService(
        db, container.settings, container.engines, container.bus, container.orion, container.policy
    )


def get_contract_service(
    db: AsyncSession = Depends(get_db), container: Container = Depends(get_container)
) -> ContractService:
    return ContractService(
        db, container.settings, container.engines, container.bus, container.orion, container.policy
    )


def get_principal() -> str:
    """Authentication seam: the caller's identity. Always "anonymous" until auth exists; an
    auth layer replaces this dependency without touching mission logic."""
    return ANONYMOUS


async def internal_endpoint(container: Container = Depends(get_container)) -> None:
    """Internal engineering endpoints are hidden (404) unless ``internals_exposed``."""
    if not container.settings.internals_exposed:
        raise NotFoundError("not found", code="not_found")


def rate_limit(bucket: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Per-client token bucket. ``bucket`` is 'default' or 'expensive'."""

    async def dependency(request: Request, container: Container = Depends(get_container)) -> None:
        settings = container.settings
        limit = (
            settings.rate_limit_expensive_per_minute
            if bucket == "expensive"
            else settings.rate_limit_per_minute
        )
        client = request.client.host if request.client else "unknown"
        if not container.rate_limiter.hit(f"{bucket}:{client}", limit):
            raise RateLimitedError("too many requests; slow down")

    return dependency
