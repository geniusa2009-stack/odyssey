"""Rewind integration, timeline-local vs campaign-global ownership (sections 31-32), saves,
checkpoints, content-version handling and the authoritative clock across disconnects."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.game.application.runtime import GameRuntime
from app.game.application.service import content_compatible
from app.game.content.loader import default_content
from tests.conftest import make_settings
from tests.game_api import (
    LUNA01,
    E,
    GamePlayer,
    charge_spacecraft,
    game_client,
    game_runtime,
    prepare_spacecraft,
    resolve_incident,
    to_incident,
)

TELESCOPE = E + "observation_deck.lunar_telescope"
DISCOVERY = "discovery.earth.shackleton_rim_illumination"
CERT = "cert.earth_command.station_operations"


@pytest.fixture
def api(sqlite_url: str) -> Iterator[tuple[TestClient, GameRuntime]]:
    with game_client(make_settings(sqlite_url)) as pair:
        yield pair


def _items(snap: dict[str, Any], cid: str) -> dict[str, int]:
    c = next(c for c in snap["world"]["containers"] if c["id"] == cid)
    return {i["item"]: i["quantity"] for i in c["items"]}


def _incident(snap: dict[str, Any]) -> dict[str, Any]:
    return next(i for i in snap["world"]["incidents"] if i["id"] == E + "power_incident")


def _rewind(g: GamePlayer, command_id: str) -> dict[str, Any]:
    out: dict[str, Any] = g.post(
        "/rewind", {"command_id": command_id, "expected_state_version": g.state_version}
    )
    g.state_version = out["state_version"]
    g.timeline_id = out["timeline"]["id"]
    return out


# =================================================================== rewind
def test_rewind_forks_timeline_local_state_and_keeps_campaign_state(
    api: tuple[TestClient, GameRuntime],
) -> None:
    g = GamePlayer(*api)
    g.create()
    to_incident(g)
    g.act("system.inspect", E + "engineering.power_bus_b")
    repair = g.act("repair.perform", E + "engineering.power_bus_b")
    after = g.snapshot()
    assert _items(after, E + "engineering.spares_locker")["spare.breaker_module"] == 1
    campaign_before = after["campaign"]

    points = g.get("/rewind-points")
    assert points["timeline_id"] == g.timeline_id
    assert repair["command_id"] in [p["command_id"] for p in points["points"]]
    old_timeline = g.timeline_id
    out = _rewind(g, repair["command_id"])
    assert out["previous_timeline_id"] == old_timeline
    assert out["timeline"]["parent_timeline_id"] == old_timeline
    assert [e["type"] for e in out["events"]] == ["timeline.changed"]
    assert out["state_version"] == after["state_version"] + 1

    snap = g.snapshot()
    assert snap["timeline"]["id"] == out["timeline"]["id"] != old_timeline
    # timeline-local state is back to just before the repair ...
    assert _items(snap, E + "engineering.spares_locker")["spare.breaker_module"] == 2
    assert _incident(snap)["stage"] == "investigating"
    assert snap["clock"]["mode"] == "PAUSED" and snap["clock"]["pause_reason"] == "rewound"
    # ... campaign-global state is untouched (nothing committed can be undone or duplicated)
    assert snap["campaign"] == campaign_before
    # the new timeline plays on normally; the spare is consumed once again, not twice
    g.act("repair.perform", E + "engineering.power_bus_b")
    assert _items(g.snapshot(), E + "engineering.spares_locker")["spare.breaker_module"] == 1
    # the rewound timeline stays inspectable
    assert g.get("/black-box", timeline_id=old_timeline)["timeline_id"] == old_timeline


def test_rewind_errors(api: tuple[TestClient, GameRuntime]) -> None:
    g = GamePlayer(*api)
    g.create()
    g.act("world.zone_entered", E + "training")
    shed = g.act("system.set_mode", E + "training.simulator", mode="off")
    stale = g.client.post(
        g.url("/rewind"),
        json={"command_id": shed["command_id"], "expected_state_version": 1},
        headers=g.headers,
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_STATE"
    zone = g.responses[0]["command_id"]  # zone entries record no simulation decision
    no_point = g.client.post(
        g.url("/rewind"),
        json={"command_id": zone, "expected_state_version": g.state_version},
        headers=g.headers,
    )
    assert no_point.status_code == 404
    assert no_point.json()["error"]["reason"] == "command_not_rewindable"


def test_rewind_cannot_duplicate_or_farm_meta_progression(
    api: tuple[TestClient, GameRuntime],
) -> None:
    """Discoveries/evidence are pending on the timeline and commit once at completion;
    rewinding drops pending items, and a completed mission cannot be rewound at all."""
    g = GamePlayer(*api)
    g.create()
    g.act("world.zone_entered", E + "training")
    anchor = g.act("system.set_mode", E + "training.simulator", mode="off")
    g.act("world.zone_entered", E + "observation_deck")
    g.act("world.poi_discovered", TELESCOPE)
    assert [d["id"] for d in g.snapshot()["discoveries"]] == [DISCOVERY]
    insights_after_discovery = g.snapshot()["campaign"]["insights"]

    _rewind(g, anchor["command_id"])
    snap = g.snapshot()
    assert snap["discoveries"] == []  # pending discovery belonged to the abandoned timeline
    assert snap["campaign"]["discoveries"] == []
    # knowledge carries no gameplay power and is kept campaign-wide (documented rule)
    assert snap["campaign"]["insights"] == insights_after_discovery

    g.act("world.zone_entered", E + "observation_deck")
    g.act("world.poi_discovered", TELESCOPE)
    g.act("mission.clock_set", mode="REALTIME")  # a rewind leaves the clock paused
    to_incident(g)
    resolve_incident(g)
    prepare_spacecraft(g)
    charge_spacecraft(g)
    done = g.act("mission.authorize", LUNA01)
    assert done["mission_transition"]["result"] == "completed"
    campaign = g.snapshot()["campaign"]
    assert campaign["discoveries"] == [DISCOVERY]
    assert campaign["certifications"].count(CERT) == 1

    # the completed Earth Command timeline is no longer active: its commands cannot be rewound
    r = g.client.post(
        g.url("/rewind"),
        json={"command_id": anchor["command_id"], "expected_state_version": g.state_version},
        headers=g.headers,
    )
    assert r.status_code == 404
    # and a completed, non-replayable mission cannot be started again to farm its rewards
    again = g.client.post(
        g.url("/missions/earth_command.station_readiness/start"),
        json={"expected_state_version": g.state_version},
        headers=g.headers,
    )
    assert again.status_code == 409
    caps = g.get("/capabilities")
    assert [c["id"] for c in caps["certifications"] if c["granted"]].count(CERT) == 1


# =================================================================== saves / checkpoints
def test_automatic_checkpoints_are_kept_bounded(sqlite_url: str) -> None:
    rt = game_runtime()
    rt.auto_checkpoint_every = 2
    rt.auto_checkpoints_kept = 3
    with game_client(make_settings(sqlite_url), rt) as pair:
        g = GamePlayer(*pair)
        g.create()
        for loc in ["engineering", "laboratory", "training", "hangar"] * 3:
            g.act("world.zone_entered", E + loc)
        cps = g.get("/checkpoints", limit=200)["checkpoints"]
        kinds = [c["kind"] for c in cps]
        assert kinds.count("auto") == 3
        assert "mission_transition" in kinds  # session start is a transition checkpoint
        for c in cps:
            assert c["location"].startswith("earth.command.")
            assert set(c) == {
                "id",
                "kind",
                "label",
                "mission_id",
                "timeline_id",
                "state_version",
                "sim_tick",
                "location",
                "created_at",
            }


def test_content_version_is_checked_on_load(sqlite_url: str) -> None:
    content = default_content()
    assert content_compatible(content.version, content)
    assert not content_compatible("0.0.1", content)
    assert not content_compatible("99.0.0", content)
    with game_client(make_settings(sqlite_url)) as pair:
        g = GamePlayer(*pair)
        g.create()
        con = sqlite3.connect(sqlite_url.removeprefix("sqlite+aiosqlite:///"))
        con.execute("update game_sessions set content_version = '0.0.1'")
        con.commit()
        con.close()
        r = g.client.get(g.url("/snapshot"), headers=g.headers)
        assert r.status_code == 422
        err = r.json()["error"]
        assert err["reason"] == "content_version_mismatch"
        assert err["recoverable"] is False
        assert err["details"]["save"] == "0.0.1"


# =================================================================== clock across disconnects
def test_restore_reports_what_happened_while_disconnected(
    api: tuple[TestClient, GameRuntime],
) -> None:
    g = GamePlayer(*api)
    g.create()
    to_incident(g)
    resolve_incident(g)
    g.act("mission.clock_set", mode="REALTIME")
    tick = g.snapshot()["clock"]["sim_tick"]
    seen = g.last_seq
    g.clock.advance(20)  # 4 ticks at 0.2 ticks/s while the client is away
    restored = g.post("/restore", {"last_seq": seen})
    away = restored["while_disconnected"]
    assert away["from_tick"] == tick and away["to_tick"] == tick + 4
    assert away["ticks_advanced"] == 4
    assert away["event_types"].get("time.advanced") == 1
    assert restored["snapshot"]["clock"]["sim_tick"] == tick + 4
    # restoring again at the same instant advances nothing (no double advancement)
    again = g.post("/restore", {"last_seq": restored["snapshot"]["session"]["last_seq"]})
    assert again["while_disconnected"]["ticks_advanced"] == 0
    assert again["events"] == []


def test_unattended_play_is_capped_and_paused(api: tuple[TestClient, GameRuntime]) -> None:
    g = GamePlayer(*api)
    g.create()
    to_incident(g)
    resolve_incident(g)
    g.act("mission.clock_set", mode="REALTIME")
    tick = g.snapshot()["clock"]["sim_tick"]
    g.clock.advance(3600)  # an hour away: far more than max_catchup_ticks are owed
    out = g.sync()
    assert out["ticks_advanced"] == 24
    assert out["clock"]["mode"] == "PAUSED"
    assert out["clock"]["pause_reason"] == "unattended_limit"
    assert out["sim_tick"] == tick + 24
