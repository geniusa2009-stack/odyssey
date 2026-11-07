"""odyssey.game.v1 under contention: optimistic concurrency, idempotency races, atomic
transfers and clock settlement. Runs on SQLite always and on PostgreSQL (row locks with
``SELECT ... FOR UPDATE``) when ``ODYSSEY_TEST_POSTGRES_URL`` is set. Requests come from several
threads through one TestClient, so they interleave on the server event loop like real clients.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.game.application.runtime import GameRuntime
from tests.conftest import make_settings
from tests.game_api import HANGAR_STORAGE, E, GamePlayer, game_client
from tests.test_contract_concurrency import _reset_postgres


@pytest.fixture(params=["sqlite", "postgres"])
def api(
    request: pytest.FixtureRequest, sqlite_url: str
) -> Iterator[tuple[TestClient, GameRuntime]]:
    if request.param == "postgres":
        url = request.getfixturevalue("postgres_url")
        _reset_postgres(url)
        settings = make_settings(url, auto_create_schema=False)
    else:
        settings = make_settings(sqlite_url)
    with game_client(settings) as pair:
        yield pair


def _parallel(fns: list[Any]) -> list[Any]:
    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        return list(pool.map(lambda f: f(), fns))


def _ready_in_hangar(api: tuple[TestClient, GameRuntime]) -> GamePlayer:
    g = GamePlayer(*api)
    g.create()
    g.act("world.zone_entered", E + "hangar")
    return g


def _items(snap: dict[str, Any], cid: str) -> dict[str, int]:
    c = next(c for c in snap["world"]["containers"] if c["id"] == cid)
    return {i["item"]: i["quantity"] for i in c["items"]}


def test_racing_commands_on_one_version(api: tuple[TestClient, GameRuntime]) -> None:
    """Different commands on the same expected version: exactly one mutates; the rest get
    409 STALE_STATE; the version advances by exactly one."""
    g = GamePlayer(*api)
    g.create()
    bodies = [
        g.command_body("world.zone_entered", E + loc)
        for loc in ("engineering", "laboratory", "training", "medical")
    ]
    responses = _parallel([lambda b=b: g.send(b) for b in bodies])
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409, 409, 409], [r.text for r in responses]
    for r in responses:
        if r.status_code == 409:
            assert r.json()["error"]["code"] == "STALE_STATE"
    snap = g.snapshot()
    assert snap["state_version"] == 2
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert snap["world"]["player_location"] == winner["target"]


def test_retry_racing_its_original_is_applied_once(api: tuple[TestClient, GameRuntime]) -> None:
    g = _ready_in_hangar(api)
    body = g.command_body(
        "cargo.transfer",
        HANGAR_STORAGE,
        item="tool.diagnostic_scanner",
        quantity=1,
        **{"from": "earth.command.player_kit"},
    )
    responses = _parallel([lambda: g.send(body)] * 4)
    assert [r.status_code for r in responses] == [200] * 4, [r.text for r in responses]
    assert all(r.json() == responses[0].json() for r in responses)
    assert sorted(r.headers["Idempotent-Replayed"] for r in responses) == [
        "false",
        "true",
        "true",
        "true",
    ]
    snap = g.snapshot()
    assert _items(snap, HANGAR_STORAGE)["tool.diagnostic_scanner"] == 1
    assert snap["state_version"] == responses[0].json()["state_version"]


def test_racing_transfers_conserve_mass(api: tuple[TestClient, GameRuntime]) -> None:
    """Two different transfers of the last unit from one container on the same version: one
    wins, no duplication, no negative quantity, total mass unchanged."""
    g = _ready_in_hangar(api)
    before = g.snapshot()
    total_before = sum(c["mass_kg"] for c in before["world"]["containers"])
    bodies = [
        g.command_body(
            "cargo.transfer",
            HANGAR_STORAGE,
            item="tool.diagnostic_scanner",
            quantity=1,
            **{"from": "earth.command.player_kit"},
        )
        for _ in range(3)
    ]
    responses = _parallel([lambda b=b: g.send(b) for b in bodies])
    assert sorted(r.status_code for r in responses) == [200, 409, 409]
    after = g.snapshot()
    total_after = sum(c["mass_kg"] for c in after["world"]["containers"])
    assert abs(total_after - total_before) < 1e-6
    assert _items(after, HANGAR_STORAGE)["tool.diagnostic_scanner"] == 1
    assert all(
        q >= 0 for c in after["world"]["containers"] for q in _items(after, c["id"]).values()
    )


def test_racing_syncs_never_double_advance(api: tuple[TestClient, GameRuntime]) -> None:
    """Clock settlement is idempotent at an instant: N concurrent syncs advance the simulation
    by the due ticks once."""
    g = GamePlayer(*api)
    g.create()
    g.act("world.zone_entered", E + "engineering")
    tick0 = g.snapshot()["clock"]["sim_tick"]
    g.clock.advance(10)  # 2 ticks at the Earth Command realtime rate (0.2 ticks/s)
    responses = _parallel([lambda: g.client.post(g.url("/sync"), json={}, headers=g.headers)] * 4)
    ok = [r for r in responses if r.status_code == 200]
    assert ok, [r.text for r in responses]
    assert all(r.status_code in {200, 409} for r in responses)
    snap = g.snapshot()
    assert snap["clock"]["sim_tick"] == tick0 + 2
    assert sum(r.json()["ticks_advanced"] for r in ok) == 2
