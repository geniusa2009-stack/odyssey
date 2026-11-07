"""odyssey.game.v1 over HTTP: the Earth Command end-to-end flow (production API paths only),
error contract, auth seam, idempotency, optimistic concurrency, campaign gates and the
on-demand read endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.game.application.runtime import GameRuntime
from tests.conftest import make_settings
from tests.game_api import (
    GAME,
    HANGAR_STORAGE,
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

EC = "earth_command.station_readiness"
L1 = "luna_01.the_last_light"


@pytest.fixture
def api(sqlite_url: str) -> Iterator[tuple[TestClient, GameRuntime]]:
    with game_client(make_settings(sqlite_url)) as pair:
        yield pair


@pytest.fixture
def player(api: tuple[TestClient, GameRuntime]) -> GamePlayer:
    g = GamePlayer(*api)
    g.create()
    return g


def _obj(snap: dict[str, Any], oid: str) -> dict[str, Any]:
    return next(o for o in snap["world"]["objects"] if o["id"] == oid)


def _container(snap: dict[str, Any], cid: str) -> dict[str, int]:
    c = next(c for c in snap["world"]["containers"] if c["id"] == cid)
    return {i["item"]: i["quantity"] for i in c["items"]}


def _error(r: Any) -> dict[str, Any]:
    body: dict[str, Any] = r.json()["error"]
    return body


# =================================================================== Phase 1 end-to-end
def test_earth_command_end_to_end_through_the_api(sqlite_url: str) -> None:
    """Section 53: create → bootstrap → engineering → inspect fault → system action →
    consequence → resolve → inspect LUNA-01 → requirements → authorize → campaign transition →
    save → disconnect → restore (fresh server process on the same database) → exact state."""
    settings = make_settings(sqlite_url)
    runtime = game_runtime()
    with game_client(settings, runtime) as (client, rt):
        g = GamePlayer(client, rt)
        created = g.create()
        boot = created["bootstrap"]
        assert boot["protocol"] == "odyssey.game.v1"
        assert boot["snapshot"]["mission"]["id"] == EC
        assert boot["snapshot"]["campaign"]["active_mission"] == EC
        assert boot["snapshot"]["clock"]["mode"] == "PAUSED"
        assert boot["snapshot"]["world"]["player_location"] == E + "observation_deck"
        assert "mission.authorize" in {a["type"] for a in boot["features"]["actions"]}
        assert g.get("/bootstrap")["snapshot"]["state_version"] == g.state_version

        # enter engineering: the mission clock starts; trusted time passes; the fault happens
        out = g.act("world.zone_entered", E + "engineering")
        assert out["result"] == "applied"
        to_incident_snapshot = g.wait(30)
        snap = g.snapshot()
        assert snap["clock"]["mode"] == "DECISION_PAUSED"
        incident = next(i for i in snap["world"]["incidents"] if i["id"] == E + "power_incident")
        assert incident["stage"] == "active"
        assert "incident.started" in {e["type"] for e in to_incident_snapshot["events"]}

        # investigate, then act on the physical system and observe the consequence
        inspect = g.act("system.inspect", E + "engineering.power_bus_b")
        assert any(e["type"] == "incident.updated" for e in inspect["events"])
        g.act("world.zone_entered", E + "training")
        shed = g.act("system.set_mode", E + "training.simulator", mode="off")
        assert any(e["type"] in {"system.state_changed", "mission.updated"} for e in shed["events"])
        assert _obj(g.snapshot(), E + "training.simulator")["power"] == "off"
        g.act("world.zone_entered", E + "engineering")
        before_spares = _container(g.snapshot(), E + "engineering.spares_locker")
        g.act("repair.perform", E + "engineering.power_bus_b")
        after_spares = _container(g.snapshot(), E + "engineering.spares_locker")
        assert after_spares["spare.breaker_module"] == before_spares["spare.breaker_module"] - 1
        g.act("mission.clock_set", mode="ACCELERATED")
        for _ in range(4):
            g.wait(5)
        snap = g.snapshot()
        incident = next(i for i in snap["world"]["incidents"] if i["id"] == E + "power_incident")
        assert incident["stage"] == "resolved"
        assert _obj(snap, LUNA01)["access"] == "inspection_ready"

        # LUNA-01 inspection, loadout, charging, then authorization
        auth = snap["mission"]["authorization"]
        assert auth["available"] is False
        prepare_spacecraft(g)
        charge_spacecraft(g)
        snap = g.snapshot()
        assert all(r["met"] for r in snap["mission"]["authorization"]["requirements"])
        g.act("world.zone_entered", E + "hangar")
        result = g.act("mission.authorize", LUNA01)
        transition = result["mission_transition"]
        assert transition["from_mission"] == EC
        assert transition["result"] == "completed"
        assert transition["next_mission"] == L1
        assert "cert.earth_command.station_operations" in transition["certifications_granted"]
        types = [e["type"] for e in result["events"]]
        assert "mission.transitioned" in types
        assert "black_box.ready" in types

        snap = g.snapshot()
        assert snap["mission"]["id"] == L1
        assert snap["timeline"]["mission_id"] == L1
        phases = {p["id"]: p["status"] for p in snap["campaign"]["phases"]}
        assert phases["EARTH_COMMAND"] == "completed"
        assert phases["LUNA_01"] == "active"
        assert _container(snap, "luna.asteria.lander.cargo_hold") == {
            "cargo.water_tank": 2,
            "spare.habitat_spares_kit": 1,
        }

        # save, then "disconnect" (the client simply goes away)
        saved = g.act("checkpoint.save", label="before_launch")
        assert any(e["type"] == "checkpoint.saved" for e in saved["events"])
        kinds = {c["kind"] for c in g.get("/checkpoints")["checkpoints"]}
        assert {"manual", "mission_transition", "critical_decision", "incident_resolved"} <= kinds
        expected = g.snapshot()
        seq_seen = g.last_seq - 3
        token, sid = g.token, g.session_id

    # a new server process on the same database (restart), same trusted time
    with game_client(settings, game_runtime(clock=runtime.clock)) as (client2, rt2):  # type: ignore[arg-type]
        g2 = GamePlayer(client2, rt2, session_id=sid, token=token)
        restored = g2.post("/restore", {"last_seq": seq_seen})
        assert restored["resync_required"] is False
        assert [e["seq"] for e in restored["events"]] == list(
            range(seq_seen + 1, expected["session"]["last_seq"] + 1)
        )
        assert restored["while_disconnected"]["ticks_advanced"] == 0
        assert restored["snapshot"] == expected
        assert g2.get("/snapshot") == expected


def test_strategies_have_different_costs_through_the_api(sqlite_url: str) -> None:
    """No correct answer: repairing at once (bus offline during maintenance) costs station
    stability; shedding training and lab loads first protects it at the price of the work they
    were doing. Both are accepted; the backend computes the consequence."""

    def run(shed: bool) -> str:
        with game_client(make_settings(sqlite_url.replace(".db", f"-{shed}.db"))) as (c, rt):
            g = GamePlayer(c, rt)
            g.create()
            to_incident(g)
            g.act("system.inspect", E + "engineering.power_bus_b")
            if shed:
                g.act("world.zone_entered", E + "training")
                g.act("system.set_mode", E + "training.simulator", mode="off")
                g.act("world.zone_entered", E + "laboratory")
                g.act("system.set_mode", E + "laboratory.sample_analyzer", mode="off")
                g.act("world.zone_entered", E + "engineering")
            g.act("repair.perform", E + "engineering.power_bus_b")
            g.act("mission.clock_set", mode="ACCELERATED")
            for _ in range(4):
                g.wait(5)
            objectives = {o["id"]: o["status"] for o in g.snapshot()["mission"]["objectives"]}
            return str(objectives["station_stability"])

    assert run(shed=False) == "failed"
    assert run(shed=True) != "failed"


# =================================================================== error contract / auth
def test_session_token_is_required(api: tuple[TestClient, GameRuntime], player: GamePlayer) -> None:
    client, _ = api
    url = f"{GAME}/sessions/{player.session_id}/snapshot"
    missing = client.get(url)
    assert missing.status_code == 403
    assert _error(missing)["code"] == "PERMISSION_DENIED"
    wrong = client.get(url, headers={"Authorization": "Bearer gst_not-the-token"})
    assert wrong.status_code == 403
    other = GamePlayer(*api)
    other.create()
    cross = client.get(url, headers=other.headers)
    assert cross.status_code == 403  # a token authorizes only its own session
    unknown = client.get(
        f"{GAME}/sessions/gs_aaaaaaaaaaaaaaaaaaaaaaaaaa/snapshot", headers=player.headers
    )
    assert unknown.status_code == 404
    assert _error(unknown)["code"] == "SESSION_NOT_FOUND"
    bad_id = client.get(f"{GAME}/sessions/not-a-session/snapshot", headers=player.headers)
    assert bad_id.status_code == 422
    assert _error(bad_id)["code"] == "VALIDATION_ERROR"


def test_errors_use_the_frozen_envelope_and_never_leak(player: GamePlayer) -> None:
    r = player.send(player.command_body("repair.perform", E + "engineering.power_bus_b"))
    assert r.status_code == 409
    err = _error(r)
    assert err["code"] == "DECISION_UNAVAILABLE"
    assert err["reason"] == "not_at_location"
    assert err["recoverable"] is True
    assert set(err) == {
        "code",
        "reason",
        "message",
        "details",
        "request_id",
        "recoverable",
        "state_version",
    }
    assert "Traceback" not in r.text
    unknown = player.send(player.command_body("system.inspect", "earth.command.nowhere"))
    assert unknown.status_code == 404
    assert _error(unknown)["code"] == "NOT_FOUND"
    bad_param = player.send(player.command_body("world.zone_entered", E + "engineering", speed=3))
    assert bad_param.status_code == 422
    unknown_action = player.send(player.command_body("player.jump", E + "engineering"))
    assert unknown_action.status_code == 422
    assert _error(unknown_action)["code"] in {"INVALID_REQUEST", "INVALID_DECISION"}


def test_client_cannot_set_authoritative_values(player: GamePlayer) -> None:
    """Section 43: no field accepts resource values, completion, certification, quantities,
    repairs or unlocks — unknown fields are rejected by the schema."""
    for extra in (
        {"resources": {"power.battery_soc": 1.0}},
        {"mission_complete": True},
        {"certifications": ["cert.earth_command.station_operations"]},
        {"state_version": 99},
    ):
        body = player.command_body("world.zone_entered", E + "engineering") | extra
        r = player.send(body)
        assert r.status_code == 422, extra
        assert _error(r)["code"] == "VALIDATION_ERROR"
    huge = player.command_body(
        "cargo.transfer",
        E + "hangar.luna01.cargo_hold",
        item="cargo.water_tank",
        quantity=10_000,
        **{"from": HANGAR_STORAGE},
    )
    assert player.send(huge).status_code in {404, 409, 422}
    assert player.snapshot()["state_version"] == 1


# =================================================================== state versions
def test_stale_state_is_rejected_and_recoverable(player: GamePlayer) -> None:
    body = player.command_body("world.zone_entered", E + "engineering")
    first = player.send(body)
    assert first.status_code == 200
    stale = player.command_body("world.zone_entered", E + "laboratory")
    stale["expected_state_version"] = 1
    r = player.send(stale)
    assert r.status_code == 409
    err = _error(r)
    assert err["code"] == "STALE_STATE"
    assert err["state_version"] == 2
    # recovery: refresh the authoritative snapshot and re-issue
    player.snapshot()
    assert player.act("world.zone_entered", E + "laboratory")["state_version"] == 3


def test_state_version_and_seq_are_monotonic(player: GamePlayer) -> None:
    versions, seqs = [player.state_version], [player.last_seq]
    for loc in ("engineering", "laboratory", "training", "hangar"):
        out = player.act("world.zone_entered", E + loc)
        versions.append(out["state_version"])
        seqs += [e["seq"] for e in out["events"]]
    assert versions == sorted(versions) and len(set(versions)) == len(versions)
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    page = player.get("/events", after_seq=0, limit=500)
    all_seqs = [e["seq"] for e in page["events"]]
    assert all_seqs == list(range(1, page["last_seq"] + 1))  # gap-free


def test_read_only_action_does_not_bump_the_version(player: GamePlayer) -> None:
    out = player.act("npc.context_request", "maya")
    assert out["result"] == "no_change"
    assert out["state_version"] == 1
    assert out["context"] is not None


# =================================================================== idempotency
def test_idempotent_retry_returns_the_same_response_once(player: GamePlayer) -> None:
    player.act("world.zone_entered", E + "hangar")
    body = player.command_body(
        "cargo.transfer",
        E + "hangar.storage",
        item="tool.diagnostic_scanner",
        quantity=1,
        **{"from": "earth.command.player_kit"},
    )
    first = player.send(body)
    assert first.status_code == 200, first.text
    assert first.headers["Idempotent-Replayed"] == "false"
    again = player.send(body)
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    snap = player.snapshot()
    assert snap["state_version"] == first.json()["state_version"]
    assert _container(snap, HANGAR_STORAGE)["tool.diagnostic_scanner"] == 1
    assert "tool.diagnostic_scanner" not in _container(snap, "earth.command.player_kit")
    reused = dict(body, command_id="other-command-id", target=E + "hangar.luna01.cargo_hold")
    r = player.send(reused)
    assert r.status_code == 422
    assert _error(r)["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_command_id_cannot_be_reused_with_a_new_key(player: GamePlayer) -> None:
    body = player.command_body("world.zone_entered", E + "engineering")
    assert player.send(body).status_code == 200
    player.snapshot()
    again = player.command_body("world.zone_entered", E + "laboratory")
    again["command_id"] = body["command_id"]
    r = player.send(again)
    assert r.status_code == 422
    assert _error(r)["reason"] == "duplicate_command_id"


def test_idempotency_header_must_match_the_body(player: GamePlayer) -> None:
    body = player.command_body("world.zone_entered", E + "engineering")
    r = player.client.post(
        player.url("/commands"),
        json=body,
        headers=player.headers | {"Idempotency-Key": "a-different-key"},
    )
    assert r.status_code == 422
    assert _error(r)["reason"] == "idempotency_mismatch"


def test_repeated_discovery_and_insight_do_not_duplicate(player: GamePlayer) -> None:
    out = player.act("world.poi_discovered", E + "observation_deck.lunar_telescope")
    assert any(e["type"] == "discovery.recorded" for e in out["events"])
    again = player.send(
        player.command_body("world.poi_discovered", E + "observation_deck.lunar_telescope")
    )
    assert again.status_code in {200, 409}
    snap = player.snapshot()
    ids = [d["id"] for d in snap["discoveries"]]
    assert ids.count("discovery.earth.shackleton_rim_illumination") == 1
    assert len(snap["insights"]) == len({i["id"] for i in snap["insights"]})


# =================================================================== campaign gates
def test_locked_and_unauthored_missions_cannot_start(player: GamePlayer) -> None:
    body = {"expected_state_version": player.state_version}
    busy = player.client.post(
        player.url(f"/missions/{L1}/start"), json=body, headers=player.headers
    )
    assert busy.status_code == 409
    assert _error(busy)["reason"] == "mission_already_active"
    unknown = player.client.post(
        player.url("/missions/no.such.mission/start"), json=body, headers=player.headers
    )
    assert unknown.status_code == 404
    skip = player.client.post(
        player.url("/phases/LUNAR_SURVIVAL/start"), json=body, headers=player.headers
    )
    assert skip.status_code == 409
    assert _error(skip)["reason"] == "phase_locked"
    mars = player.client.post(
        player.url("/phases/MARS_01/start"), json=body, headers=player.headers
    )
    assert mars.status_code == 409
    err = _error(mars)
    assert err["code"] == "DECISION_UNAVAILABLE"
    assert err["reason"] == "mars_mission_locked"
    assert err["details"]["lock_code"] == "MARS_MISSION_LOCKED"
    assert "transportation.planetary_return" in err["details"]["missing_capabilities"]
    assert player.snapshot()["state_version"] == body["expected_state_version"]
    readiness = player.get("/readiness/mars_01_human_mission")
    assert readiness["locked"] is True
    assert readiness["lock"]["code"] == "MARS_MISSION_LOCKED"
    assert readiness["lock"]["missing_capabilities"]
    assert all(
        g["critical"] for g in readiness["gates"] if g["id"] in readiness["critical_missing"]
    )


def test_progression_reads(player: GamePlayer) -> None:
    caps = player.get("/capabilities")
    assert {c["status"] for c in caps["capabilities"]} <= {
        "locked",
        "not_started",
        "qualified",
        "max",
    }
    assert caps["certifications"]
    emap = player.get("/expansion-map")
    node_ids = {n["id"] for n in emap["nodes"]}
    assert {e["source"] for e in emap["edges"]} <= node_ids
    assert {e["target"] for e in emap["edges"]} <= node_ids
    assert any(n["type"] == "mission" for n in emap["nodes"])
    assert "xp" not in str(emap).lower().split()
    catalog = player.client.get(f"{GAME}/catalog").json()
    assert catalog["items"] and catalog["infrastructure_types"]
    features = player.client.get(f"{GAME}/features").json()
    assert features["protocol"] == "odyssey.game.v1"
    assert set(features["clock_modes"]) == {"PAUSED", "REALTIME", "ACCELERATED", "DECISION_PAUSED"}


def test_why_requires_an_unlocked_insight(player: GamePlayer) -> None:
    r = player.client.get(player.url("/insights/power.load_shedding/why"), headers=player.headers)
    assert r.status_code == 404
    assert _error(r)["reason"] == "insight_not_unlocked"
    to_incident(player)
    snap = player.snapshot()
    unlocked = [i["id"] for i in snap["insights"]]
    assert "power.generation_vs_demand" in unlocked
    why = player.get("/insights/power.generation_vs_demand/why")
    assert why["insight"] == "power.generation_vs_demand"
    assert why["provenance"]["classification"]


def test_object_and_vehicle_detail(player: GamePlayer) -> None:
    obj = player.get(f"/objects/{E}engineering.power_bus_b")
    assert obj["id"] == E + "engineering.power_bus_b"
    vehicle = player.get(f"/vehicles/{LUNA01}")
    assert vehicle["vehicle_class"] == "vehicle.asteria_crew_lander"
    assert vehicle["ready"] is False and vehicle["blockers"]
    r = player.client.get(
        player.url(f"/vehicles/{E}engineering.power_bus_b"), headers=player.headers
    )
    assert r.status_code == 404


def test_snapshot_payload_is_bounded(player: GamePlayer) -> None:
    """Payload discipline: a snapshot is a compact semantic document (no history, no assets)."""
    r = player.client.get(player.url("/snapshot"), headers=player.headers)
    assert len(r.content) < 64_000
    to_incident(player)
    resolve_incident(player)
    r = player.client.get(player.url("/snapshot"), headers=player.headers)
    assert len(r.content) < 64_000
    page = player.get("/events", after_seq=0, limit=5)
    assert len(page["events"]) == 5 and page["has_more"] is True


def test_v1_api_does_not_see_game_sessions(
    api: tuple[TestClient, GameRuntime], player: GamePlayer
) -> None:
    client, _ = api
    missions = client.get("/api/v1/missions").json()
    assert [m["id"] for m in missions] == ["luna-01"]
    assert (
        client.post("/api/v1/mission-sessions", json={"mission_id": "earth-command"}).status_code
        == 404
    )
    assert client.get("/api/game/v1/openapi.json").json()["info"]["version"] == "odyssey.game.v1"
    assert "/api/game/v1/sessions" not in client.get("/openapi.json").json()["paths"]


def test_unknown_routes_use_the_error_envelope(api: tuple[TestClient, GameRuntime]) -> None:
    client, _ = api
    r = client.get(f"{GAME}/nope")
    assert r.status_code == 404
    assert _error(r)["code"] == "NOT_FOUND"


def test_db_file_isolated(tmp_path: Path) -> None:
    """Sessions persist in the configured database only (the local SQLite path works)."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'g.db'}"
    with game_client(make_settings(url)) as pair:
        GamePlayer(*pair).create()
    assert (tmp_path / "g.db").exists()


def test_one_action_recording_several_decisions(player: GamePlayer) -> None:
    """Regression (found by the API fuzzer, seed 13): an action that records two simulation
    decisions in one turn (``power.reroute`` stop = stow + unstow), right after a clock
    catch-up, keeps the ledger head consistent for every following turn."""
    player.act("world.zone_entered", E + "hangar")
    player.wait(5)
    out = player.act("power.reroute", E + "hangar.ground_support", direction="stop")
    assert out["result"] == "applied"
    player.wait(5)
    again = player.act("power.reroute", E + "hangar.ground_support", direction="to_station")
    assert again["state_version"] == out["state_version"] + 2
    assert player.post("/restore", {"last_seq": 0})["snapshot"] == player.snapshot()
