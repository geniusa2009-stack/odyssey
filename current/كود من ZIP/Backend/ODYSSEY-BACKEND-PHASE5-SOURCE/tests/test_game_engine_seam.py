"""The additive seams Phase 5 put into protected modules change nothing for existing callers:
``engine.advance(stop_when=…)`` is purely observational and chunked advancement equals one
uninterrupted advance; game-owned simulation sessions are invisible to API v1."""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from app.game.content.loader import default_content
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.events import MissionEvent
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario
from tests.conftest import make_settings
from tests.game_api import GamePlayer, game_client


@pytest.mark.parametrize("scenario_id", ["luna-01", "earth-command"])
@pytest.mark.parametrize("seed", [1, 42])
def test_chunked_advance_with_stop_when_equals_one_advance(scenario_id: str, seed: int) -> None:
    scenario = (
        get_scenario(scenario_id)
        if scenario_id == "luna-01"
        else default_content().scenarios[scenario_id]
    )
    engine = SimulationEngine(scenario)
    start = engine.initial_state(seed)
    whole = engine.advance(start, scenario.time.max_ticks)
    never = engine.advance(start, scenario.time.max_ticks, stop_when=lambda _s: False)
    assert never.state.state_hash() == whole.state.state_hash()
    assert [e.model_dump() for e in never.events] == [e.model_dump() for e in whole.events]

    rng = random.Random(seed)
    stops = set(rng.sample(range(1, scenario.time.max_ticks), 12))
    state = start
    events: list[MissionEvent] = []
    while state.tick < scenario.time.max_ticks and state.status != MissionStatus.CONCLUDED:
        r = engine.advance(state, scenario.time.max_ticks, stop_when=lambda s: s.tick in stops)
        state, events = r.state, events + r.events
        stops.discard(state.tick)
    assert state.state_hash() == whole.state.state_hash()
    assert [e.model_dump() for e in events] == [e.model_dump() for e in whole.events]


def test_game_simulation_sessions_are_invisible_to_api_v1(sqlite_url: str) -> None:
    import sqlite3

    with game_client(make_settings(sqlite_url)) as (client, rt):
        g = GamePlayer(client, rt)
        g.create()
        con = sqlite3.connect(sqlite_url.removeprefix("sqlite+aiosqlite:///"))
        (sim_id,) = con.execute(
            "select id from mission_sessions where managed_by = 'game'"
        ).fetchone()
        (v1_rows,) = con.execute("select count(*) from mission_realtime_events").fetchone()
        con.close()
        assert v1_rows == 0  # the game emits odyssey.game.v1 events only
        api: TestClient = client
        for path in ("", "/snapshot", "/bootstrap", "/history", "/verify"):
            r = api.get(f"/api/v1/mission-sessions/{sim_id}{path}")
            assert r.status_code == 404, path
            assert r.json()["error"]["code"] == "SESSION_NOT_FOUND"
