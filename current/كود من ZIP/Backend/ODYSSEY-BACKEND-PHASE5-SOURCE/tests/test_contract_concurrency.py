"""Phase 4: concurrent commands (optimistic concurrency and idempotency under contention).

Runs on SQLite always and on PostgreSQL when ``ODYSSEY_TEST_POSTGRES_URL`` is set (row locks
with ``SELECT ... FOR UPDATE``). Requests are sent from several threads through one
``TestClient``, so they interleave on the server's event loop like real concurrent clients.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.conftest import make_settings

API = "/api/v1"


def _reset_postgres(url: str) -> None:
    from app.db.session import create_engine
    from tests.test_database import _alembic

    async def reset() -> None:
        eng = create_engine(url)
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await eng.dispose()

    asyncio.run(reset())
    assert _alembic(url, "upgrade", "head").returncode == 0


@pytest.fixture(params=["sqlite", "postgres"])
def any_client(request: pytest.FixtureRequest, sqlite_url: str) -> Iterator[TestClient]:
    if request.param == "postgres":
        url = request.getfixturevalue("postgres_url")
        _reset_postgres(url)
        settings = make_settings(url, auto_create_schema=False)
    else:
        settings = make_settings(sqlite_url)
    with TestClient(create_app(settings)) as c:
        yield c


def _session(c: TestClient) -> tuple[str, int]:
    sid = c.post(f"{API}/mission-sessions", json={"seed": 3}).json()["id"]
    version = c.get(f"{API}/mission-sessions/{sid}/snapshot").json()["state_version"]
    return sid, version


def _parallel(fns: list[Any]) -> list[Any]:
    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        return list(pool.map(lambda f: f(), fns))


def test_racing_decisions_on_one_version(any_client: TestClient) -> None:
    """Several clients decide on the same state version: exactly one wins, the others get
    409 STALE_STATE, and the ledger holds one decision."""
    c = any_client
    sid, version = _session(c)
    url = f"{API}/mission-sessions/{sid}/decision-commands"

    def submit(level: float) -> Any:
        return lambda: c.post(
            url,
            json={
                "option_id": "set_ration_level",
                "parameters": {"level": level},
                "expected_state_version": version,
            },
        )

    responses = _parallel([submit(lv) for lv in (0.95, 0.9, 0.85, 0.8)])
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 409, 409, 409], [r.text for r in responses]
    for r in responses:
        if r.status_code == 409:
            assert r.json()["error"]["code"] == "STALE_STATE"
    history = c.get(f"{API}/mission-sessions/{sid}/history").json()["decisions"]
    assert len(history) == 1
    snap = c.get(f"{API}/mission-sessions/{sid}/snapshot").json()
    assert snap["state_version"] == version + 1
    assert c.get(f"{API}/mission-sessions/{sid}/verify").json()["replay_ok"]


def test_retry_racing_its_original(any_client: TestClient) -> None:
    """The same request sent twice at once with one Idempotency-Key is applied once and both
    callers receive the same successful response."""
    c = any_client
    sid, version = _session(c)
    url = f"{API}/mission-sessions/{sid}/decision-commands"
    body = {
        "option_id": "set_ration_level",
        "parameters": {"level": 0.9},
        "expected_state_version": version,
    }
    headers = {"Idempotency-Key": "race-key-000001"}
    responses = _parallel([lambda: c.post(url, json=body, headers=headers)] * 3)
    assert [r.status_code for r in responses] == [201, 201, 201], [r.text for r in responses]
    # Same content (PostgreSQL JSONB may store object keys of free-form dicts in another order)
    assert all(r.json() == responses[0].json() for r in responses)
    replayed = sorted(r.headers["Idempotent-Replayed"] for r in responses)
    assert replayed == ["false", "true", "true"]
    history = c.get(f"{API}/mission-sessions/{sid}/history").json()["decisions"]
    assert len(history) == 1


def test_racing_advances(any_client: TestClient) -> None:
    c = any_client
    sid, version = _session(c)
    url = f"{API}/mission-sessions/{sid}/advance-commands"
    responses = _parallel(
        [lambda: c.post(url, json={"ticks": 5, "expected_state_version": version})] * 3
    )
    assert sorted(r.status_code for r in responses) == [200, 409, 409]
    snap = c.get(f"{API}/mission-sessions/{sid}/snapshot").json()
    assert snap["clock"]["tick"] == 5 and snap["state_version"] == version + 1
    events = c.get(
        f"{API}/mission-sessions/{sid}/events", params={"last_state_version": version}
    ).json()["events"]
    assert {e["state_version"] for e in events} == {version + 1}
