"""Phase 4 API contract tests: the frozen frontend-safe endpoints (docs/API_FREEZE_V1.md).

Covers bootstrap, snapshot recovery, decision commands (valid, invalid, unavailable, stale),
idempotent retries, realtime event ordering, WebSocket resume, objective outlook, radiation
budget, Future Lens, Black Box, rewind, Engineering Profile, Mission DNA, science claims,
v0.1.0 compatibility, v0.2.0 determinism and the production hardening of internal endpoints.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.errors import PUBLIC_CODES
from app.db import models as m
from app.main import create_app
from app.read_models.bootstrap import MissionBootstrap
from app.read_models.decisions import decision_parameters, decision_to_option_id
from app.read_models.mission import MissionSnapshotView
from app.simulation.scenarios.loader import load_scenario_file, scenario_content_hash
from tests.conftest import make_settings

API = "/api/v1"
COMPAT = Path(__file__).parent / "fixtures" / "compat"
GOLDEN: list[dict[str, Any]] = json.loads(
    (COMPAT / "luna-01-v0.1.0-golden.json").read_text(encoding="utf-8")
)["cases"]
FORBIDDEN_KEYS = {"seed", "rng", "modifiers", "trigger", "effects", "random"}
EXPECTED_RESOURCES = {
    "power",
    "battery",
    "oxygen",
    "co2",
    "water",
    "food",
    "thermal",
    "communications",
    "science",
    "radiation",
    "rover",
}


# ----------------------------------------------------------------------------- helpers
class Mission:
    """A client of the frozen contract that tracks the state version like a frontend would."""

    def __init__(self, client: TestClient, seed: int = 42, **create: Any) -> None:
        self.c = client
        r = client.post(f"{API}/mission-sessions", json={"seed": seed, **create})
        assert r.status_code == 201, r.text
        self.sid: str = r.json()["id"]
        self.base = f"{API}/mission-sessions/{self.sid}"
        self.version: int = self.get("/bootstrap")["snapshot"]["state_version"]

    def get(self, path: str, **params: Any) -> Any:
        r = self.c.get(f"{self.base}{path}", params=params)
        assert r.status_code == 200, r.text
        return r.json()

    def decide_raw(self, option_id: str, version: int | None = None, **body: Any) -> Any:
        payload = {
            "option_id": option_id,
            "expected_state_version": self.version if version is None else version,
            **body,
        }
        return self.c.post(f"{self.base}/decision-commands", json=payload)

    def decide(self, option_id: str, **params: float) -> Any:
        r = self.decide_raw(option_id, parameters=params)
        assert r.status_code == 201, r.text
        self.version = r.json()["state_version"]
        return r.json()

    def advance_raw(
        self, ticks: int, version: int | None = None, headers: dict[str, str] | None = None
    ) -> Any:
        return self.c.post(
            f"{self.base}/advance-commands",
            json={"ticks": ticks, "expected_state_version": version or self.version},
            headers=headers or {},
        )

    def advance(self, ticks: int) -> Any:
        r = self.advance_raw(ticks)
        assert r.status_code == 200, r.text
        self.version = r.json()["state_version"]
        return r.json()

    def run_to_end(self) -> None:
        while self.get("/snapshot")["status"] != "concluded":
            self.advance(240)


def error(r: Any) -> dict[str, Any]:
    body = r.json()
    assert set(body) == {"error"}, body
    err: dict[str, Any] = body["error"]
    assert err["code"] in PUBLIC_CODES
    assert r.status_code == PUBLIC_CODES[err["code"]].status
    assert err["recoverable"] is PUBLIC_CODES[err["code"]].recoverable
    assert "Traceback" not in r.text
    return err


def all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        out = set(value)
        for v in value.values():
            out |= all_keys(v)
        return out
    if isinstance(value, list):
        out = set()
        for v in value:
            out |= all_keys(v)
        return out
    return set()


@pytest.fixture
def small_retention_client(sqlite_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(sqlite_url, realtime_retained_versions=2))) as c:
        yield c


# ----------------------------------------------------------------------------- bootstrap
class TestBootstrap:
    def test_schema_and_content(self, client: TestClient) -> None:
        ms = Mission(client)
        body = ms.get("/bootstrap")
        boot = MissionBootstrap.model_validate(body)  # the documented shape, nothing extra
        assert boot.api.api_version == "v1"
        assert boot.api.realtime_contract == "odyssey.realtime.v1"
        assert boot.scenario.scenario_version == "0.2.0"  # scenario and API versions differ
        assert boot.api.error_codes == sorted(PUBLIC_CODES)
        assert boot.capabilities.future_lens and boot.capabilities.radiation_budget
        assert boot.capabilities.idempotency and boot.capabilities.optimistic_concurrency
        assert boot.capabilities.multiplayer_ready is False
        assert boot.capabilities.future_lens_omniscient is False
        snap = boot.snapshot
        assert snap.state_version == ms.version and snap.clock.tick == 0
        assert {r.id for r in snap.resources} == EXPECTED_RESOURCES
        assert {s.id for s in snap.systems.systems} >= {"power", "life_support", "thermal"}
        assert len(snap.crew.members) == len(boot.scenario.crew)
        assert {o.id for o in snap.objectives.objectives} == {
            o.id for o in boot.scenario.objectives
        }
        assert snap.decisions.available_count > 0
        assert {t.option_id for t in snap.decisions.tools} == {"tool:future_lens", "tool:orion"}
        assert all(t.impact == "informational" for t in snap.decisions.tools)
        assert snap.radiation.dose_limit_msv == 15.0
        assert boot.realtime.path.endswith(f"/ws/mission-sessions/{ms.sid}")
        # frontend-safe: no seed, no raw engine state, no scheduling internals, no history
        assert not all_keys(body) & FORBIDDEN_KEYS
        assert "state" not in body["snapshot"]
        assert len(json.dumps(body)) < 120_000

    def test_unknown_session(self, client: TestClient) -> None:
        r = client.get(f"{API}/mission-sessions/00000000-0000-0000-0000-00000000abcd/bootstrap")
        assert r.status_code == 404 and error(r)["code"] == "SESSION_NOT_FOUND"

    def test_capabilities_endpoint(self, client: TestClient) -> None:
        caps = client.get(f"{API}/capabilities").json()
        assert caps["api"]["api_version"] == "v1"
        assert caps["capabilities"]["internal_endpoints"] is True  # test environment


# ----------------------------------------------------------------------------- snapshot
class TestSnapshot:
    def test_snapshot_is_the_authoritative_state(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.advance(20)
        result = ms.decide("start_science_activity:regolith_survey")
        snap = ms.get("/snapshot")
        MissionSnapshotView.model_validate(snap)
        assert snap["state_version"] == result["state_version"] == ms.version
        assert snap["hud"] == result["hud"]
        assert snap["science"]["active_opportunity"] == "regolith_survey"
        # the same truth as the internal raw view and the bootstrap
        raw = client.get(f"{ms.base}/state").json()
        assert raw["state_hash"] == snap["state_hash"]
        assert raw["state_version"] == snap["state_version"]
        assert ms.get("/bootstrap")["snapshot"] == snap

    def test_recovery_after_lost_events(self, client: TestClient) -> None:
        """A client that missed every realtime event recovers fully from one snapshot."""
        ms = Mission(client)
        stale = ms.get("/snapshot")
        ms.advance(30)
        ms.decide("set_ration_level", level=0.9)
        fresh = ms.get("/snapshot")
        assert fresh["state_version"] > stale["state_version"]
        assert fresh["clock"]["tick"] == 30
        assert (
            ms.decide("set_ration_level", level=0.85)["prev_state_version"]
            == (fresh["state_version"])
        )

    def test_trend_only_from_recorded_states(self, client: TestClient) -> None:
        ms = Mission(client)
        first = {r["id"]: r for r in ms.get("/snapshot")["resources"]}
        assert all(r["trend"]["basis"] == "insufficient_data" for r in first.values())
        assert all(r["trend"]["direction"] == "unknown" for r in first.values())
        ms.advance(10)
        later = {r["id"]: r for r in ms.get("/snapshot")["resources"]}
        assert later["battery"]["trend"]["basis"] == "recorded_snapshot"
        detail = ms.get("/resources/battery")
        assert detail["history_basis"] == "recorded_snapshots"
        assert [p["tick"] for p in detail["history"]] == sorted(
            {p["tick"] for p in detail["history"]}
        )
        r = client.get(f"{ms.base}/resources/warp_core")
        assert r.status_code == 404


# ----------------------------------------------------------------------------- decisions
class TestDecisions:
    def test_options_are_backend_authoritative(self, client: TestClient) -> None:
        ms = Mission(client)
        opts = {o["option_id"]: o for o in ms.get("/decision-options")["options"]}
        stop = opts["stop_science_activity"]
        assert stop["available"] is False and stop["unavailable"]["reason"] == "no_active_science"
        assert opts["set_crew_location:shelter"]["impact"] == "major"
        assert opts["schedule_maintenance:battery"]["impact"] == "local"  # D24
        setpoint = opts["set_thermal_setpoint"]
        assert setpoint["parameters"][0]["name"] == "target_c"
        assert setpoint["parameters"][0]["min"] < setpoint["parameters"][0]["max"]
        for o in opts.values():
            assert o["impact"] in ("major", "local")
            assert o["affected_systems"]
            assert (o["unavailable"] is None) == o["available"]

    def test_submit_by_option_id(self, client: TestClient) -> None:
        ms = Mission(client)
        before = ms.version
        r = ms.decide_raw("set_subsystem_mode:comms:eco")
        assert r.status_code == 201
        body = r.json()
        assert body["accepted"] is True
        assert body["prev_state_version"] == before and body["state_version"] == before + 1
        assert body["decision"]["option_id"] == "set_subsystem_mode:comms:eco"
        assert body["decision"]["decision_type"] == "set_subsystem_mode"
        assert r.headers["Idempotent-Replayed"] == "false"
        history = ms.get("/history")["decisions"]
        assert [d["option_id"] for d in history] == ["set_subsystem_mode:comms:eco"]

    @pytest.mark.parametrize(
        ("option_id", "params", "reason"),
        [
            ("set_subsystem_mode:warp_core:boost", {}, "unknown_option"),
            ("set_thermal_setpoint", {"target_c": 99.0}, "bad_parameters"),
            ("set_thermal_setpoint", {}, "bad_parameters"),
            ("set_ration_level", {"level": 0.9, "extra": 1.0}, "bad_parameters"),
        ],
    )
    def test_invalid_decision(
        self, client: TestClient, option_id: str, params: dict[str, float], reason: str
    ) -> None:
        ms = Mission(client)
        r = ms.decide_raw(option_id, parameters=params)
        err = error(r)
        assert err["code"] == "INVALID_DECISION" and err["reason"] == reason
        assert ms.get("/snapshot")["state_version"] == ms.version  # nothing applied

    def test_type_mismatch_and_malformed(self, client: TestClient) -> None:
        ms = Mission(client)
        r = ms.decide_raw("stop_science_activity", decision_type="set_ration_level")
        assert error(r)["reason"] == "option_type_mismatch"
        r = ms.decide_raw("NOT AN OPTION")
        assert error(r)["code"] == "VALIDATION_ERROR"
        r = client.post(f"{ms.base}/decision-commands", json={"option_id": "stop_science_activity"})
        assert error(r)["code"] == "VALIDATION_ERROR"  # expected_state_version is required

    def test_unavailable_decision(self, client: TestClient) -> None:
        ms = Mission(client)
        r = ms.decide_raw("stop_science_activity")
        err = error(r)
        assert err["code"] == "DECISION_UNAVAILABLE" and err["reason"] == "no_active_science"
        assert err["recoverable"] is True and err["state_version"] == ms.version
        # a science window that has not opened yet looks exactly like a closed one
        r = ms.decide_raw("start_science_activity:ice_core_sampling")
        err = error(r)
        assert err["code"] == "DECISION_UNAVAILABLE"
        assert err["reason"] == "opportunity_unavailable"
        assert ms.get("/history")["decisions"] == []

    def test_mission_complete(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.run_to_end()
        err = error(ms.decide_raw("set_ration_level", parameters={"level": 0.9}))
        assert err["code"] == "MISSION_COMPLETE"
        err = error(ms.advance_raw(1))
        assert err["code"] == "MISSION_COMPLETE"


# ----------------------------------------------------------------------------- concurrency
class TestStaleState:
    def test_stale_decision_is_never_applied(self, client: TestClient) -> None:
        ms = Mission(client)
        seen = ms.version
        ms.decide("set_ration_level", level=0.9)  # someone else moved the state
        r = ms.decide_raw("set_ration_level", version=seen, parameters={"level": 0.8})
        err = error(r)
        assert r.status_code == 409 and err["code"] == "STALE_STATE"
        assert err["reason"] == "stale_state" and err["recoverable"] is True
        assert err["state_version"] == ms.version
        assert err["details"]["expected_state_version"] == seen
        assert {"timeline_id", "head_tick", "head_sequence"} <= set(err["details"])
        levels = [d["parameters"]["level"] for d in ms.get("/history")["decisions"]]
        assert levels == [0.9]

    def test_stale_advance(self, client: TestClient) -> None:
        ms = Mission(client)
        seen = ms.version
        ms.advance(1)
        r = ms.advance_raw(5, version=seen)
        assert error(r)["code"] == "STALE_STATE"
        assert ms.get("/snapshot")["clock"]["tick"] == 1

    def test_versions_are_monotonic(self, client: TestClient) -> None:
        ms = Mission(client)
        versions = [ms.version]
        for _ in range(3):
            versions.append(ms.advance(2)["state_version"])
            versions.append(ms.decide("set_ration_level", level=0.9)["state_version"])
        assert versions == sorted(set(versions))
        assert all(b == a + 1 for a, b in itertools.pairwise(versions))


# ----------------------------------------------------------------------------- idempotency
class TestIdempotency:
    def test_retried_decision_is_applied_once(self, client: TestClient) -> None:
        ms = Mission(client)
        body = {"option_id": "set_ration_level", "parameters": {"level": 0.9}}
        payload = {**body, "expected_state_version": ms.version}
        headers = {"Idempotency-Key": "retry-key-0001"}
        first = client.post(f"{ms.base}/decision-commands", json=payload, headers=headers)
        again = client.post(f"{ms.base}/decision-commands", json=payload, headers=headers)
        assert first.status_code == again.status_code == 201
        assert again.json() == first.json()
        assert first.headers["Idempotent-Replayed"] == "false"
        assert again.headers["Idempotent-Replayed"] == "true"
        assert len(ms.get("/history")["decisions"]) == 1
        assert ms.get("/snapshot")["state_version"] == first.json()["state_version"]

    def test_key_reused_for_another_request(self, client: TestClient) -> None:
        ms = Mission(client)
        headers = {"Idempotency-Key": "retry-key-0002"}
        payload = {"option_id": "set_ration_level", "parameters": {"level": 0.9}}
        ok = client.post(
            f"{ms.base}/decision-commands",
            json={**payload, "expected_state_version": ms.version},
            headers=headers,
        )
        assert ok.status_code == 201
        other = client.post(
            f"{ms.base}/decision-commands",
            json={**payload, "parameters": {"level": 0.8}, "expected_state_version": ms.version},
            headers=headers,
        )
        assert error(other)["code"] == "IDEMPOTENCY_KEY_REUSED"

    def test_failed_requests_are_not_stored(self, client: TestClient) -> None:
        ms = Mission(client)
        headers = {"Idempotency-Key": "retry-key-0003"}
        stale = client.post(
            f"{ms.base}/decision-commands",
            json={"option_id": "stop_science_activity", "expected_state_version": ms.version},
            headers=headers,
        )
        assert stale.status_code == 409
        retry = client.post(
            f"{ms.base}/decision-commands",
            json={"option_id": "stop_science_activity", "expected_state_version": ms.version},
            headers=headers,
        )
        assert retry.status_code == 409  # re-executed, not replayed
        assert retry.headers.get("Idempotent-Replayed") is None

    def test_create_advance_and_branch(self, client: TestClient) -> None:
        h = {"Idempotency-Key": "create-key-0001"}
        a = client.post(f"{API}/mission-sessions", json={"seed": 5}, headers=h)
        b = client.post(f"{API}/mission-sessions", json={"seed": 5}, headers=h)
        assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
        assert b.headers["Idempotent-Replayed"] == "true"
        ms = Mission(client)
        h = {"Idempotency-Key": "advance-key-0001"}
        first = ms.advance_raw(3, headers=h)
        second = ms.advance_raw(3, version=ms.version, headers=h)
        assert first.json() == second.json()
        assert ms.get("/snapshot")["clock"]["tick"] == 3
        ms.version = first.json()["state_version"]
        decision = ms.decide("set_ration_level", level=0.9)["decision"]["decision_id"]
        body = {
            "decision_id": decision,
            "alternative": {"option_id": "set_ration_level", "parameters": {"level": 0.8}},
        }
        h = {"Idempotency-Key": "branch-key-0001"}
        x = client.post(f"{ms.base}/timeline-branches", json=body, headers=h)
        y = client.post(f"{ms.base}/timeline-branches", json=body, headers=h)
        assert x.status_code == y.status_code == 201
        assert x.json()["timeline"]["id"] == y.json()["timeline"]["id"]
        assert len(ms.get("/timelines")["timelines"]) == 2

    def test_bad_key(self, client: TestClient) -> None:
        r = client.post(
            f"{API}/mission-sessions", json={"seed": 1}, headers={"Idempotency-Key": "bad key!"}
        )
        assert error(r)["code"] == "INVALID_REQUEST"


# ----------------------------------------------------------------------------- realtime
def check_order(events: list[dict[str, Any]]) -> None:
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids)), "duplicate event ids"
    positions = [(e["state_version"], e["seq"]) for e in events]
    assert positions == sorted(positions) and len(set(positions)) == len(positions)
    groups: dict[int, list[dict[str, Any]]] = {}
    for e in events:
        assert e["contract"] == "odyssey.realtime.v1"
        assert e["event_id"] == f"{e['timeline_id']}:{e['state_version']}:{e['seq']}"
        groups.setdefault(e["state_version"], []).append(e)
    previous: int | None = None
    for version, group in sorted(groups.items()):
        assert [e["seq"] for e in group] == list(range(group[0]["seq_count"]))
        assert group[-1]["type"] in ("MISSION_STATE_CHANGED", "MISSION_COMPLETED")
        if previous is not None:
            assert group[0]["prev_state_version"] == previous
        previous = version


class TestRealtime:
    def test_event_ordering(self, client: TestClient) -> None:
        ms = Mission(client)
        start = ms.version
        ms.advance(20)
        ms.decide("start_science_activity:regolith_survey")
        ms.advance(110)  # crosses the dusk phase change and the 122 storm
        page = ms.get("/events", last_state_version=start)
        assert page["resync_required"] is False
        events = page["events"]
        check_order(events)
        types = [e["type"] for e in events]
        assert {"PHASE_CHANGED", "SYSTEM_ALERT", "DECISION_ACCEPTED"} <= set(types)
        decision_group = [e for e in events if e["state_version"] == start + 2]
        assert decision_group[0]["type"] == "DECISION_ACCEPTED"
        for e in events:
            assert not all_keys(e["payload"]) & {"trigger", "effects", "random", "seed"}

    def test_ordering_is_deterministic(self, sqlite_url: str, tmp_path: Path) -> None:
        from app.tools.contract_fixtures import deterministic_uuids

        def run(db: Path) -> list[dict[str, Any]]:
            settings = make_settings(f"sqlite+aiosqlite:///{db}")
            with deterministic_uuids(), TestClient(create_app(settings)) as c:
                ms = Mission(c, seed=9)
                ms.advance(20)
                ms.decide("start_science_activity:regolith_survey")
                ms.advance(150)
                events: list[dict[str, Any]] = ms.get("/events", last_state_version=1)["events"]
            return [{k: v for k, v in e.items() if k != "server_time"} for e in events]

        assert run(tmp_path / "a.db") == run(tmp_path / "b.db")

    def test_mission_completed_event(self, client: TestClient) -> None:
        ms = Mission(client)
        before = ms.version
        ms.run_to_end()
        events = ms.get("/events", last_state_version=before)["events"]
        assert events[-1]["type"] == "MISSION_COMPLETED"
        assert events[-1]["payload"]["outcome"]["tier"] in ("partial", "mission_failed")

    def test_resume_cursors(self, client: TestClient) -> None:
        ms = Mission(client)
        start = ms.version
        ms.decide("set_ration_level", level=0.9)
        page = ms.get("/events", last_state_version=start)["events"]
        last = page[-1]["event_id"]
        ms.advance(3)
        after = ms.get("/events", last_event_id=last)
        assert after["resync_required"] is False
        assert {e["state_version"] for e in after["events"]} == {ms.version}
        assert ms.get("/events", last_event_id=after["events"][-1]["event_id"])["events"] == []
        future = ms.get("/events", last_state_version=ms.version + 5)
        assert future["resync_required"] and future["reason"] == "unknown_position"
        r = client.get(f"{ms.base}/events", params={"last_event_id": "garbage"})
        assert error(r)["code"] == "INVALID_REQUEST"

    def test_expired_events_require_resync(self, small_retention_client: TestClient) -> None:
        ms = Mission(small_retention_client)
        start = ms.version
        for _ in range(4):
            ms.advance(1)
        page = ms.get("/events", last_state_version=start)
        assert page["resync_required"] and page["reason"] == "events_expired"
        assert page["state_version"] == ms.version


class TestWebSocket:
    def test_connect_and_live_events(self, client: TestClient) -> None:
        ms = Mission(client)
        with client.websocket_connect(f"{API}/ws/mission-sessions/{ms.sid}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "CONNECTED" and hello["state_version"] == ms.version
            assert hello["snapshot_path"].endswith("/snapshot")
            ms.decide("set_ration_level", level=0.9)
            frames = [ws.receive_json() for _ in range(3)]
        check_order(frames)
        assert frames[0]["type"] == "DECISION_ACCEPTED"

    def test_reconnect_replays_missed_events(self, client: TestClient) -> None:
        ms = Mission(client)
        with client.websocket_connect(f"{API}/ws/mission-sessions/{ms.sid}") as ws:
            last_version = ws.receive_json()["state_version"]
        ms.decide("set_ration_level", level=0.9)  # missed while disconnected
        ms.advance(2)
        expected = ms.get("/events", last_state_version=last_version)["events"]
        url = f"{API}/ws/mission-sessions/{ms.sid}?last_state_version={last_version}"
        with client.websocket_connect(url) as ws:
            control = ws.receive_json()
            assert control["type"] == "RESUMED" and control["replayed"] == len(expected)
            replayed = [ws.receive_json() for _ in range(len(expected))]
        assert replayed == expected
        check_order(replayed)
        url = f"{API}/ws/mission-sessions/{ms.sid}?last_event_id={expected[-1]['event_id']}"
        with client.websocket_connect(url) as ws:
            control = ws.receive_json()
            assert control["type"] == "RESUMED" and control["replayed"] == 0

    def test_resync_after_timeline_change(self, client: TestClient) -> None:
        ms = Mission(client)
        decision = ms.decide("set_ration_level", level=0.9)
        old_last = ms.get("/events", last_state_version=1)["events"][-1]["event_id"]
        r = client.post(
            f"{ms.base}/timeline-branches",
            json={"decision_id": decision["decision"]["decision_id"], "activate": True},
        )
        assert r.status_code == 201
        url = f"{API}/ws/mission-sessions/{ms.sid}?last_event_id={old_last}"
        with client.websocket_connect(url) as ws:
            control = ws.receive_json()
        assert control["type"] == "RESYNC_REQUIRED" and control["reason"] == "timeline_changed"
        assert control["timeline_id"] == r.json()["timeline"]["id"]

    def test_resync_when_expired(self, small_retention_client: TestClient) -> None:
        ms = Mission(small_retention_client)
        for _ in range(4):
            ms.advance(1)
        url = f"{API}/ws/mission-sessions/{ms.sid}?last_state_version=1"
        with small_retention_client.websocket_connect(url) as ws:
            control = ws.receive_json()
        assert control["type"] == "RESYNC_REQUIRED" and control["reason"] == "events_expired"

    @pytest.mark.parametrize("query", ["last_event_id=bad", "timeline_id=../x"])
    def test_malformed_resume_is_rejected(self, client: TestClient, query: str) -> None:
        ms = Mission(client)
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            client.websocket_connect(f"{API}/ws/mission-sessions/{ms.sid}?{query}") as ws,
        ):
            ws.receive_json()
        assert exc.value.code == 1008

    def test_oversized_client_frames_are_ignored(self, client: TestClient) -> None:
        ms = Mission(client)
        with client.websocket_connect(f"{API}/ws/mission-sessions/{ms.sid}") as ws:
            ws.receive_json()
            ws.send_text("x" * 5000)
            ws.send_text('{"type": "advance", "ticks": 240}')  # commands are REST-only
            ws.send_text('{"type":"ping"}')
            assert ws.receive_json()["type"] == "PONG"
        assert ms.get("/snapshot")["clock"]["tick"] == 0


# ----------------------------------------------------------------------------- outlook
class TestObjectivesAndRadiation:
    def test_objective_outlook(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.advance(20)
        out = ms.get("/objectives")
        cats = {o["category"] for o in out["objectives"]}
        assert cats == {"primary", "safety", "stability", "efficiency", "science", "discovery"}
        for o in out["objectives"]:
            assert o["status"] in ("pending", "achieved", "failed")
            assert o["rule"] and o["message_key"] == f"objective.{o['id']}"
            if o["completion_fraction"] is not None:
                assert 0.0 <= o["completion_fraction"] <= 1.0
        science = next(o for o in out["objectives"] if o["id"] == "science_return")
        assert science["required"] is True and science["completion_fraction"] == 0.0
        assert science["rule"]["target"] == 2.0
        assert "not a probability" in out["tier_statement"]
        assert not all_keys(out) & {"probability", "chance"}
        assert {t["tier"] for t in out["tiers"]} == {"exceptional", "success", "partial"}

    def test_outlook_after_passive_mission(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.run_to_end()
        tiers = {t["tier"]: t for t in ms.get("/objectives")["tiers"]}
        assert tiers["success"]["still_possible"] is False
        assert "science_return" in tiers["partial"]["blocked_by"]
        completion = ms.get("/completion")
        assert completion["concluded"] is True
        assert completion["outcome"]["tier"] == "mission_failed"
        assert {b["tier"] for b in completion["better_tiers_blocked"]} >= {"success", "partial"}

    def test_radiation_budget(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.advance(30)
        rad = ms.get("/radiation-budget")
        assert rad == ms.get("/snapshot")["radiation"]
        assert rad["dose_limit_msv"] == 15.0
        assert rad["projection_basis"] == "baseline_rate_current_locations"
        assert "does not anticipate space-weather events" in rad["projection_statement"]
        assert rad["budget_state"] in ("within_budget", "budget_low", "budget_exceeded")
        assert rad["dose_margin_msv"] == pytest.approx(15.0 - rad["max_dose_msv"], abs=0.02)
        assert len(rad["crew"]) == len(ms.get("/snapshot")["crew"]["members"])
        ms.decide("set_crew_location:shelter")
        sheltered = ms.get("/radiation-budget")
        assert sheltered["crew_in_shelter"] == len(sheltered["crew"]) - len(
            sheltered["crew_on_eva"]
        )


# ----------------------------------------------------------------------------- analysis
class TestFutureLens:
    def lens(self, ms: Mission, **body: Any) -> Any:
        payload = {
            "candidates": [
                {"label": "shelter", "decisions": [{"option_id": "set_crew_location:shelter"}]}
            ],
            "horizon_ticks": 24,
            "samples": 2,
            **body,
        }
        return ms.c.post(f"{ms.base}/future-lens/projections", json=payload)

    def test_contract(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.advance(100)
        before = ms.get("/snapshot")
        r = self.lens(ms)
        assert r.status_code == 200, r.text
        view = r.json()
        kb = view["knowledge_boundary"]
        assert kb["prediction_mode"] == "known_only"
        assert kb["anticipates_unforeseeable_events"] is False
        assert [b["label"] for b in view["branches"]] == ["baseline", "shelter"]
        branch = view["branches"][1]
        assert branch["valid"] and branch["resources"] and branch["objectives"]
        assert (
            branch["confidence"]["knowledge_factor"]
            == view["branches"][0]["confidence"]["knowledge_factor"]
        )
        assert any("Unforeseeable events" in a for a in branch["assumptions"])
        assert view["horizon"]["requested_ticks"] == 24
        after = ms.get("/snapshot")
        assert after == before  # never changes mission state
        assert ms.get("/events", last_state_version=before["state_version"])["events"] == []

    def test_omniscient_is_disabled_by_default(self, client: TestClient) -> None:
        ms = Mission(client)
        err = error(self.lens(ms, prediction_mode="omniscient"))
        assert err["code"] == "PERMISSION_DENIED" and err["reason"] == "omniscient_disabled"
        raw = client.post(
            f"{ms.base}/future-lens",
            json={
                "candidates": [{"label": "x", "decisions": []}],
                "knowledge_policy": "omniscient",
            },
        )
        assert error(raw)["reason"] == "omniscient_disabled"  # internal endpoint too

    def test_omniscient_when_enabled(self, sqlite_url: str) -> None:
        settings = make_settings(sqlite_url, future_lens_omniscient_enabled=True)
        with TestClient(create_app(settings)) as c:
            ms = Mission(c)
            view = self.lens(ms, prediction_mode="omniscient").json()
            assert view["knowledge_boundary"]["anticipates_unforeseeable_events"] is True

    @pytest.mark.parametrize(
        "body",
        [
            {"horizon_ticks": 10_000},
            {"samples": 99},
            {"candidates": [{"label": f"c{i}", "decisions": []} for i in range(5)]},
            {"candidates": [{"label": "x", "decisions": [{"option_id": "nope"}] * 9}]},
        ],
    )
    def test_limits(self, client: TestClient, body: dict[str, Any]) -> None:
        ms = Mission(client)
        assert error(self.lens(ms, **body))["code"] == "VALIDATION_ERROR"

    def test_invalid_candidate_option(self, client: TestClient) -> None:
        ms = Mission(client)
        r = self.lens(ms, candidates=[{"label": "x", "decisions": [{"option_id": "nope"}]}])
        assert error(r)["code"] == "INVALID_DECISION"


class TestBlackBoxAndCompletion:
    def test_black_box_contract(self, client: TestClient) -> None:
        ms = Mission(client, seed=7)
        ms.advance(20)
        ms.decide("start_science_activity:regolith_survey")
        ms.decide("set_subsystem_mode:science_payload:boost")
        ms.run_to_end()
        bb = ms.get("/black-box/summary")
        assert bb["outcome"]["tier"] in ("partial", "mission_failed", "critical_failure")
        assert bb["counterfactuals_evaluated"] is True
        assert bb["shortfalls"], "a non-success mission has shortfalls"
        for s in bb["shortfalls"]:
            assert s["objective"] and s["category"] and s["consequence"]
            assert s["kind"] in ("traced", "omission", "untraced")
            for d in s["root_decisions"]:
                assert d["verdict"] == "decision_worsened_target"  # never blamed without proof
            for d in s["decisions_on_path_without_effect"]:
                assert d["verdict"] != "decision_worsened_target"
        assert "counterfactual" in bb["statement"]
        for moment in bb["key_moments"]:
            assert not all_keys(moment["data"]) & {"trigger", "effects", "random"}
        assert not all_keys(bb) & {"seed", "nodes", "edges"}

    def test_completion_before_end(self, client: TestClient) -> None:
        ms = Mission(client)
        c = ms.get("/completion")
        assert c["concluded"] is False and c["outcome"] is None
        assert c["better_tiers_blocked"] == []


class TestRewind:
    def test_rewind_contract(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.advance(20)
        science = ms.decide("start_science_activity:regolith_survey")
        ms.advance(10)
        ms.decide("set_ration_level", level=0.9)
        parent = ms.get("/snapshot")
        parent_history = ms.get("/history")
        points = ms.get("/rewind-points")["points"]
        assert [p["option_id"] for p in points] == [
            "start_science_activity:regolith_survey",
            "set_ration_level",
        ]
        assert [p["decisions_discarded_if_replaced"] for p in points] == [2, 1]
        did = science["decision"]["decision_id"]
        preview = ms.get(f"/rewind-points/{did}/preview")
        assert preview["fork_tick"] == 20 and preview["discarded_decisions"] == 2
        assert preview["state_at_fork"]["tick"] == 20
        r = client.post(
            f"{ms.base}/timeline-branches",
            json={
                "decision_id": did,
                "alternative": {"option_id": "set_subsystem_mode:comms:eco"},
                "activate": False,
                "label": "comms-first",
            },
        )
        assert r.status_code == 201, r.text
        change = r.json()
        child = change["timeline"]["id"]
        assert change["parent_timeline_id"] == parent["timeline"]["id"]
        assert change["alternative_decision"]["option_id"] == "set_subsystem_mode:comms:eco"
        assert change["active"] is False
        # the original timeline is immutable
        assert ms.get("/snapshot") == parent
        assert ms.get("/history") == parent_history
        tree = {t["id"]: t for t in ms.get("/timelines")["timelines"]}
        assert tree[child]["parent_timeline_id"] == parent["timeline"]["id"]
        assert tree[parent["timeline"]["id"]]["children"] == [child]
        assert tree[child]["replaced_decision_id"] == did
        child_snap = ms.get("/snapshot", timeline_id=child)
        assert child_snap["clock"]["tick"] == 20
        assert child_snap["timeline"]["is_active"] is False

    def test_unknown_decision(self, client: TestClient) -> None:
        ms = Mission(client)
        r = client.get(f"{ms.base}/rewind-points/nope/preview")
        assert error(r)["code"] == "INVALID_TIMELINE"
        r = client.post(f"{ms.base}/timeline-branches", json={"decision_id": "nope"})
        assert error(r)["code"] == "INVALID_TIMELINE"


class TestProfileDnaEvidence:
    def test_profile(self, client: TestClient) -> None:
        ms = Mission(client)
        ms.advance(20)
        ms.decide("start_science_activity:regolith_survey")
        p = ms.get("/engineering-profile")
        assert len(p["dimensions"]) == 7
        assert all(0.0 <= d["value"] <= 1.0 for d in p["dimensions"])
        assert p["archetype"] is None and p["provisional"] is True
        assert p["coverage"]["decisions_analysed"] == 1
        assert p["coverage"]["mission_concluded"] is False

    def test_dna_is_share_safe_and_comparable(self, client: TestClient) -> None:
        codes = []
        for _ in range(2):
            ms = Mission(client, seed=31)
            ms.advance(20)
            ms.decide("start_science_activity:regolith_survey")
            ms.run_to_end()
            dna = ms.get("/mission-dna/share")
            text = json.dumps(dna)
            assert ms.sid not in text
            assert not all_keys(dna) & {"seed", "session_id", "timeline_id", "participant_id"}
            assert dna["share_safe"] is True and dna["scenario_version"] == "0.2.0"
            assert dna["concluded"] is True and dna["outcome_tier"] is not None
            codes.append(dna["code"])
        assert codes[0] == codes[1]  # same play → same code, on any session

    def test_science_claims(self, client: TestClient) -> None:
        claims = client.get(f"{API}/science/claims").json()
        assert claims
        for c in claims:
            assert {"concept", "claim", "source", "provenance", "simplification"} <= set(c)
            assert c["verified"] == c["verification_status"].startswith("verified")
            if c["verification_status"] == "unverified":
                assert c["provenance"] == "unverified" and not c["verified"]
                assert "Unverified" in c["status_label"]
        assert any(c["verified"] for c in claims)
        assert any(not c["verified"] for c in claims)
        one = client.get(f"{API}/science/claims/{claims[0]['id']}").json()
        assert one == claims[0]
        assert client.get(f"{API}/science/claims/nope").status_code == 404


# ----------------------------------------------------------------------------- compatibility
def add_v010_scenario(sqlite_url: str) -> None:
    """Simulate a database created before Phase 3: the v0.1.0 scenario row is present."""
    scenario = load_scenario_file(COMPAT / "luna-01-v0.1.0.yaml")
    engine = create_engine(sqlite_url.replace("+aiosqlite", ""))
    with Session(engine) as db:
        db.add(
            m.MissionScenario(
                id="00000000-0000-0000-0000-0000000001a0",
                mission_id=scenario.mission_id,
                scenario_key=scenario.id,
                version=scenario.version,
                content_hash=scenario_content_hash(scenario),
                provisional=scenario.provisional,
                definition=scenario.model_dump(mode="json", by_alias=True),
            )
        )
        db.commit()
    engine.dispose()


@pytest.mark.parametrize("case", GOLDEN, ids=[c["label"] for c in GOLDEN])
def test_v010_sessions_through_the_contract(sqlite_url: str, case: dict[str, Any]) -> None:
    with TestClient(create_app(make_settings(sqlite_url))) as c:
        add_v010_scenario(sqlite_url)
        ms = Mission(c, seed=case["seed"], scenario_version="0.1.0")
        boot = ms.get("/bootstrap")
        assert boot["scenario"]["scenario_version"] == "0.1.0"
        assert boot["capabilities"]["radiation_budget"] is False
        assert boot["snapshot"]["radiation"]["budget_state"] == "no_limit"
        for d in case["decisions"]:
            tick = ms.get("/snapshot")["clock"]["tick"]
            if d["tick"] > tick:
                ms.advance(d["tick"] - tick)
            ms.decide(decision_to_option_id(d["decision"]), **decision_parameters(d["decision"]))
        ms.run_to_end()
        completion = ms.get("/completion")
        assert completion["outcome"]["code"] == case["outcome"]
        statuses = {o["id"]: o["status"] for o in completion["objectives"]}
        assert statuses == case["objectives"]
        verify = c.get(f"{ms.base}/verify").json()
        assert verify["ledger_ok"] and verify["replay_ok"]


def test_v020_contract_is_deterministic() -> None:
    """The scripted fixture session produces byte-identical contract responses every run and
    matches the committed examples (tests/fixtures/contract/examples)."""
    from app.tools import contract_fixtures

    first = contract_fixtures.generate()
    second = contract_fixtures.generate()
    assert first == second
    for name, value in first.items():
        path = contract_fixtures.EXAMPLES / f"{name}.json"
        assert path.read_text(encoding="utf-8") == contract_fixtures.render(value), name


def test_openapi_schema_is_unchanged() -> None:
    """Any API change, breaking or not, needs a reviewed snapshot update:
    ``python -m app.tools.openapi_snapshot --write`` (docs/API_FREEZE_V1.md)."""
    from app.tools import openapi_snapshot

    old = json.loads(openapi_snapshot.FIXTURE.read_text(encoding="utf-8"))
    diff = openapi_snapshot.differences(old, openapi_snapshot.current_schema())
    assert diff == [], "OpenAPI changed:\n" + "\n".join(diff)


# ----------------------------------------------------------------------------- production
def test_production_hides_internals(sqlite_url: str) -> None:
    settings = make_settings(sqlite_url, environment="production")
    with TestClient(create_app(settings)) as c:
        created = c.post(f"{API}/mission-sessions", json={})
        assert created.status_code == 201 and created.json()["seed"] is None
        sid = created.json()["id"]
        base = f"{API}/mission-sessions/{sid}"
        assert c.get(base).json()["seed"] is None
        for method, path, body in [
            ("get", "/state", None),
            ("get", "/timeline", None),
            ("get", "/verify", None),
            ("get", "/black-box", None),
            ("get", "/trace?metric=power.battery_soc", None),
            ("get", "/profile", None),
            ("get", "/mission-dna", None),
            ("post", "/future-lens", {"candidates": [{"label": "x", "decisions": []}]}),
            ("post", "/decisions", {"decision": {"type": "stop_science_activity"}}),
            ("post", "/advance", {"ticks": 1}),
            ("post", "/rewind", {"decision_id": "x"}),
        ]:
            r = c.request(method, f"{base}{path}", json=body)
            assert r.status_code == 404 and error(r)["code"] == "NOT_FOUND", path
        boot = c.get(f"{base}/bootstrap").json()
        assert boot["capabilities"]["internal_endpoints"] is False
        assert not all_keys(boot) & FORBIDDEN_KEYS
        ms_version = boot["snapshot"]["state_version"]
        r = c.post(
            f"{base}/advance-commands", json={"ticks": 2, "expected_state_version": ms_version}
        )
        assert r.status_code == 200


# ----------------------------------------------------------------------------- query counts
def test_bootstrap_query_count_does_not_grow_with_timelines(client: TestClient) -> None:
    """No N+1: the bootstrap's SQL statement count is the same with 1 or 4 timelines."""
    from sqlalchemy import event

    ms = Mission(client, participants=[{"handle": "a", "role": "commander"}])
    engine = client.app.state.container.db_engine.sync_engine  # type: ignore[attr-defined]
    counted: list[int] = []

    def count(*_: Any, **__: Any) -> None:
        counted.append(1)

    def queries() -> int:
        counted.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            ms.get("/bootstrap")
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(counted)

    decision = ms.decide("set_ration_level", level=0.9)["decision"]["decision_id"]
    one = queries()
    for i in range(3):
        r = client.post(
            f"{ms.base}/timeline-branches",
            json={"decision_id": decision, "activate": False, "label": f"b{i}"},
        )
        assert r.status_code == 201
    assert len(ms.get("/timelines")["timelines"]) == 4
    assert queries() == one <= 10
