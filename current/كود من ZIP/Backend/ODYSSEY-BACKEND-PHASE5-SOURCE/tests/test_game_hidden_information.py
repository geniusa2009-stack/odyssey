"""Hidden information never reaches the Unreal client (sections 7, 26, 28, 30, 51).

Collects every payload a client can obtain — bootstrap, snapshots, command results, realtime
events, restore, detail reads, progression reads, Future Lens and Black Box — and checks that
none contains: an incident or unforeseeable simulation event before it happened, the session
seed or a derived mission seed, simulation session/timeline ids, ledger decision ids or the
token hash.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.game.application.memory import mission_seed
from app.game.content.loader import default_content
from app.read_models.visibility import unforeseeable_event_ids
from tests.conftest import make_settings
from tests.game_api import (
    GAME,
    LUNA01,
    E,
    GamePlayer,
    charge_spacecraft,
    game_client,
    prepare_spacecraft,
    resolve_incident,
)

HIDDEN_EC = ("bus_b_breaker_fault", "power_incident", "breaker_fault")


def _db_path(sqlite_url: str) -> str:
    return sqlite_url.removeprefix("sqlite+aiosqlite:///")


def _secrets(sqlite_url: str) -> list[str]:
    con = sqlite3.connect(_db_path(sqlite_url))
    try:
        out: list[str] = []
        for seed, token_hash in con.execute("select seed, token_hash from game_sessions"):
            out += [str(seed), token_hash]
            for mission in ("earth_command.station_readiness", "luna_01.the_last_light"):
                for attempt in (1, 2, 3):
                    out.append(str(mission_seed(seed, mission, attempt)))
        for (sid,) in con.execute("select id from mission_sessions"):
            out.append(sid)
        for (tid,) in con.execute("select id from mission_timelines"):
            out.append(tid)
        for (did,) in con.execute("select decision_id from mission_decisions"):
            out.append(did)
        return out
    finally:
        con.close()


def _collect(g: GamePlayer) -> list[Any]:
    payloads: list[Any] = [
        g.get("/bootstrap"),
        g.get("/snapshot"),
        g.get("/events", after_seq=0, limit=500),
        g.get("/checkpoints"),
        g.get("/capabilities"),
        g.get("/expansion-map"),
        g.get("/readiness/mars_01_human_mission"),
        g.get("/rewind-points"),
        g.get("/black-box"),
        g.get("/engineering-profile"),
        g.get("/mission-dna"),
        g.post("/restore", {"last_seq": 0}),
        g.client.get(f"{GAME}/features").json(),
        g.client.get(f"{GAME}/catalog").json(),
        *g.responses,
    ]
    snap = g.snapshot()
    for obj in snap["world"]["objects"]:
        payloads.append(g.get(f"/objects/{obj['id']}"))
    return payloads


def _assert_absent(payloads: list[Any], needles: list[str] | tuple[str, ...]) -> None:
    text = json.dumps(payloads)
    for needle in needles:
        assert needle not in text, f"leaked {needle!r}"


def _lens(g: GamePlayer, horizon: int = 24) -> Any:
    return g.post(
        "/future-lens",
        {
            "candidates": [
                {
                    "id": "heat-eco",
                    "action": "system.set_mode",
                    "target": E + "engineering.thermal_plant",
                    "params": {"mode": "eco"},
                },
                {"id": "walk", "action": "world.zone_entered", "target": E + "hangar"},
            ],
            "horizon_ticks": horizon,
        },
    )


def test_nothing_hidden_leaks_before_the_incident(sqlite_url: str) -> None:
    with game_client(make_settings(sqlite_url)) as pair:
        g = GamePlayer(*pair)
        g.create()
        g.act("world.zone_entered", E + "engineering")
        g.wait(5)  # one tick: the scheduled fault (tick 4) has not happened yet
        assert g.snapshot()["world"]["incidents"] == []
        lens = _lens(g, horizon=24)  # the horizon crosses the hidden fault tick
        assert lens["knowledge_boundary"]["prediction_mode"] == "known_only"
        assert lens["knowledge_boundary"]["anticipates_unforeseeable_events"] is False
        payloads = [*_collect(g), lens]
        _assert_absent(payloads, HIDDEN_EC)
        _assert_absent(payloads, _secrets(sqlite_url))
        # the projection does not "see" the scheduled bus fault: no candidate shows damage
        for branch in lens["branches"]:
            for hint in branch["world_hints"]:
                assert hint["object"] != E + "engineering.power_bus_b"


def test_lens_and_black_box_shapes_carry_no_engine_internals(sqlite_url: str) -> None:
    with game_client(make_settings(sqlite_url)) as pair:
        g = GamePlayer(*pair)
        g.create()
        g.act("world.zone_entered", E + "engineering")
        lens = _lens(g, horizon=8)
        branch_keys = set().union(*(b.keys() for b in lens["branches"]))
        assert not branch_keys & {"decisions", "excluded_events", "seed", "label"}
        assert set(lens) == {
            "protocol",
            "session_id",
            "timeline_id",
            "mission_id",
            "state_version",
            "base_tick",
            "base_sim_hours",
            "horizon",
            "knowledge_boundary",
            "branches",
        }
        bb = g.get("/black-box")
        for node in bb["nodes"]:
            assert not node["id"].startswith("decision:") or node["decision"]["command_id"]
        # no presentation directives anywhere
        text = json.dumps([lens, bb]).lower()
        for word in ("color", "colour", "animation", "particle", "niagara", "material"):
            assert word not in text


def test_luna01_unforeseeable_events_stay_hidden(sqlite_url: str) -> None:
    hidden = sorted(unforeseeable_event_ids(default_content().scenarios.values()))
    with game_client(make_settings(sqlite_url)) as pair:
        g = GamePlayer(*pair)
        g.create()
        g.act("world.zone_entered", E + "engineering")
        g.wait(30)
        resolve_incident(g)
        prepare_spacecraft(g)
        charge_spacecraft(g)
        g.act("mission.authorize", LUNA01)
        snap = g.snapshot()
        assert snap["mission"]["id"] == "luna_01.the_last_light"
        g.act("world.zone_entered", "luna.asteria.habitat")
        lens = g.post(
            "/future-lens",
            {
                "candidates": [
                    {
                        "id": "heater-eco",
                        "action": "system.set_mode",
                        "target": "luna.asteria.habitat.core",
                        "params": {"mode": "eco"},
                    }
                ],
                "horizon_ticks": 48,
            },
        )
        payloads = [*_collect(g), lens]
        luna_hidden = [h for h in hidden if h != "bus_b_breaker_fault"]
        _assert_absent(payloads, luna_hidden)
        _assert_absent(payloads, _secrets(sqlite_url))
