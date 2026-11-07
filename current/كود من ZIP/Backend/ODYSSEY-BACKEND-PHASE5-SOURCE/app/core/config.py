"""Typed, environment-based settings (prefix ``ODYSSEY_``). No secrets have defaults."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ODYSSEY_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    # Persistence: defaults to a local SQLite file so the API boots with zero infrastructure.
    database_url: str = "sqlite+aiosqlite:///./odyssey-dev.db"
    database_echo: bool = False
    auto_create_schema: bool = Field(
        False, description="Create tables on startup (dev/test only; production uses Alembic)"
    )

    # Optional Redis (pub/sub fan-out + cache). Empty → in-memory implementations.
    redis_url: str | None = None

    # HTTP / security
    cors_origins: list[str] = Field(default_factory=list)
    max_request_bytes: int = Field(64 * 1024, ge=1024)
    rate_limit_per_minute: int = Field(120, ge=1)
    rate_limit_expensive_per_minute: int = Field(20, ge=1)
    max_advance_ticks: int = Field(240, ge=1)
    snapshot_interval_ticks: int = Field(24, ge=1)

    # Application contract (Phase 4)
    realtime_retained_versions: int = Field(
        64, ge=1, description="State versions per timeline kept for realtime resume"
    )
    future_lens_omniscient_enabled: bool = Field(
        False,
        description="Allow omniscient Future Lens projections on every Future Lens endpoint. "
        "Omniscient projections reveal hidden future events (teacher/debug tool); the role "
        "policy (D6) still applies on top of this switch.",
    )
    internal_endpoints_enabled: bool | None = Field(
        None,
        description="Serve the internal engineering endpoints (raw state, raw timeline, raw "
        "Future Lens/Black Box/trace, legacy commands) and include session seeds in session "
        "views. They expose engine internals and the random seed, which would let a client "
        "compute hidden future events. Default: enabled except in production.",
    )

    @property
    def internals_exposed(self) -> bool:
        if self.internal_endpoints_enabled is not None:
            return self.internal_endpoints_enabled
        return self.environment != "production"

    # AI (ORION). "mock" needs no key and is the default.
    ai_provider: Literal["mock", "openai_compatible"] = "mock"
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: SecretStr | None = None
    ai_timeout_seconds: float = Field(20.0, gt=0)

    # NASA data
    nasa_api_key: SecretStr | None = None
    nasa_remote_enabled: bool = False
    nasa_base_url: str = "https://api.nasa.gov"
    nasa_timeout_seconds: float = Field(10.0, gt=0)
    nasa_cache_ttl_seconds: int = Field(24 * 3600, ge=0)
    nasa_cache_dir: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [o.strip() for o in stripped.split(",") if o.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
