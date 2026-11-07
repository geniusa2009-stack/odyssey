"""Test fixtures.

Infrastructure-backed tests are opt-in through environment variables and skipped otherwise:
* ``ODYSSEY_TEST_POSTGRES_URL`` (e.g. postgresql+asyncpg://user:pw@localhost:5432/odyssey_test)
* ``ODYSSEY_TEST_REDIS_URL``    (e.g. redis://localhost:6379/15)
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, settings

from app.core.config import Settings
from app.main import create_app
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario
from app.simulation.scenarios.schema import ScenarioDefinition
from app.telemetry import runtime_stats

settings.register_profile(
    "odyssey", deadline=None, max_examples=25, suppress_health_check=[HealthCheck.too_slow]
)
# Long fuzzing run: HYPOTHESIS_PROFILE=fuzz uv run pytest tests/test_invariants_and_fuzz.py
settings.register_profile(
    "fuzz", deadline=None, max_examples=500, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "odyssey"))

POSTGRES_URL = os.environ.get("ODYSSEY_TEST_POSTGRES_URL")
REDIS_URL = os.environ.get("ODYSSEY_TEST_REDIS_URL")


@pytest.fixture(scope="session")
def scenario() -> ScenarioDefinition:
    return get_scenario("luna-01")


@pytest.fixture(scope="session")
def engine(scenario: ScenarioDefinition) -> SimulationEngine:
    return SimulationEngine(scenario)


@pytest.fixture
def initial(engine: SimulationEngine) -> MissionState:
    return engine.initial_state(42)


def make_settings(db_url: str, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "database_url": db_url,
        "auto_create_schema": True,
        "log_json": False,
        "log_level": "WARNING",
        "rate_limit_per_minute": 100_000,
        "rate_limit_expensive_per_minute": 100_000,
        "redis_url": None,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'odyssey-test.db'}"


@pytest.fixture
def client(sqlite_url: str) -> Iterator[TestClient]:
    runtime_stats.reset()
    with TestClient(create_app(make_settings(sqlite_url))) as test_client:
        yield test_client


@pytest.fixture
def postgres_url() -> str:
    if not POSTGRES_URL:
        pytest.skip("ODYSSEY_TEST_POSTGRES_URL not set")
    return POSTGRES_URL


@pytest.fixture
def redis_url() -> str:
    if not REDIS_URL:
        pytest.skip("ODYSSEY_TEST_REDIS_URL not set")
    return REDIS_URL
