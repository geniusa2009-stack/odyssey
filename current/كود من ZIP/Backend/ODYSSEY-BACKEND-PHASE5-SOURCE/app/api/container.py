"""Process-wide dependencies, created once in the app lifespan."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.mock import MockAIProvider
from app.ai.orion import ORIONService
from app.ai.provider import AIProvider, OpenAICompatibleProvider
from app.api.security import InMemoryRateLimiter, RateLimiter
from app.core.config import Settings
from app.db.session import create_engine, create_session_factory
from app.nasa.cache import CacheBackend, FileCache, InMemoryCache, RedisCache
from app.nasa.providers import (
    DonkiSolarEnvironmentProvider,
    FallbackSolarEnvironmentProvider,
    FixtureSolarEnvironmentProvider,
    SolarEnvironmentProvider,
)
from app.realtime.bus import EventBus, InMemoryEventBus, RedisEventBus
from app.services.engine_registry import EngineRegistry
from app.services.permissions import AllowAllPolicy, PermissionPolicy

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    db_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    engines: EngineRegistry
    bus: EventBus
    orion: ORIONService
    http: httpx.AsyncClient
    rate_limiter: RateLimiter
    solar_provider: SolarEnvironmentProvider
    policy: PermissionPolicy
    redis: Any | None = None

    async def close(self) -> None:
        await self.bus.close()
        await self.http.aclose()
        await self.db_engine.dispose()


def _ai_provider(settings: Settings, http: httpx.AsyncClient) -> AIProvider:
    if settings.ai_provider == "openai_compatible":
        if not settings.ai_base_url or not settings.ai_model:
            log.warning("ai_provider_misconfigured", extra={"error_code": "ai_config"})
            return MockAIProvider()
        key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else None
        return OpenAICompatibleProvider(
            http, settings.ai_base_url, settings.ai_model, key, settings.ai_timeout_seconds
        )
    return MockAIProvider()


def build_container(settings: Settings) -> Container:
    db_engine = create_engine(settings.database_url, echo=settings.database_echo)
    http = httpx.AsyncClient(follow_redirects=False)
    redis_client = None
    bus: EventBus
    cache: CacheBackend
    if settings.redis_url:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
        bus = RedisEventBus(redis_client)
        cache = RedisCache(redis_client)
    else:
        bus = InMemoryEventBus()
        cache = (
            FileCache(Path(settings.nasa_cache_dir)) if settings.nasa_cache_dir else InMemoryCache()
        )
    primary = None
    if settings.nasa_remote_enabled and settings.nasa_api_key is not None:
        primary = DonkiSolarEnvironmentProvider(
            http,
            settings.nasa_base_url,
            settings.nasa_api_key.get_secret_value(),
            settings.nasa_timeout_seconds,
        )
    solar = FallbackSolarEnvironmentProvider(
        primary, FixtureSolarEnvironmentProvider(), cache, settings.nasa_cache_ttl_seconds
    )
    return Container(
        settings=settings,
        db_engine=db_engine,
        session_factory=create_session_factory(db_engine),
        engines=EngineRegistry(),
        bus=bus,
        orion=ORIONService(_ai_provider(settings, http)),
        http=http,
        rate_limiter=InMemoryRateLimiter(),
        solar_provider=solar,
        policy=AllowAllPolicy(),
        redis=redis_client,
    )
