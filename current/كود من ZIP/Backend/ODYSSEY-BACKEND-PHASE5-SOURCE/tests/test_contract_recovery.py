"""Recovery-fidelity regression tests for the reconstructed API v1 (docs/RECOVERY_PROVENANCE.md).

The Phase 4 repository was reconstructed after the original workspace was lost. These tests pin
the points where the reconstruction was aligned with the recorded original contract:

* F1  snapshot / bootstrap alerts expose ``id`` (``alert_id`` stays where it is confirmed:
      Future Lens warnings and resource alert rules)
* F2  decision entries carry ``participant_id`` (null when no participant was given)
* F3  the recorded Future Lens explanation names ``crew.projected_dose_msv``; the engine's own
      trace (target ``crew.projected_dose_margin_msv``) is unchanged
* F4  Black Box key moments exclude randomly sampled wear faults, which stay in the report
* F13 the frozen resume semantics of ``GET .../events`` (REST equivalent of WebSocket resume)
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.errors import PUBLIC_CODES
from app.main import create_app
from tests.conftest import make_settings

API = "/api/v1"


# ----------------------------------------------------------------------------- helpers
class Session:
    def __init__(self, client: TestClient, seed: int = 42, **create: Any) -> None:
        self.c = client
        r = client.post(f"{API}/mission-sessions", json={"seed": seed, **create})
        assert r.status_code == 201, r.text
        self.body: dict[str, Any] = r.json()
        self.sid: str = self.body["id"]
        self.base = f"{API}/mission-sessions/{self.sid}"
        self.version: int = self.get("/snapshot")["state_version"]

    def get(self, path: str, **params: Any) -> Any:
        r = self.c.get(f"{self.base}{path}", params=params)
        assert r.status_code == 200, r.text
        return r.json()

    def advance(self, ticks: int) -> Any:
        r = self.c.post(
            f"{self.base}/advance-commands",
            json={"ticks": ticks, "expected_state_version": self.version},
        )
        assert r.status_code == 200, r.text
        self.version = r.json()["state_version"]
        return r.json()

    def decide(self, option_id: str, **body: Any) -> Any:
        r = self.c.post(
            f"{self.base}/decision-commands",
            json={"option_id": option_id, "expected_state_version": self.version, **body},
        )
        assert r.status_code == 201, r.text
        self.version = r.json()["state_version"]
        return r.json()

    def run_to_end(self) -> None:
        while self.get("/snapshot")["status"] != "concluded":
            self.advance(240)


def error(r: Any) -> dict[str, Any]:
    err: dict[str, Any] = r.json()["error"]
    assert r.status_code == PUBLIC_CODES[err["code"]].status
    return err


def recorded_scenario_to_tick_123(client: TestClient) -> Session:
    """The scripted contract-fixture session up to its emergency snapshot (tick 123, v6)."""
    s = Session(client, seed=42)
    s.advance(15)
    s.decide("start_science_activity:regolith_survey")
    s.advance(85)
    s.decide("start_science_activity:ice_core_sampling")
    s.advance(23)
    assert s.get("/snapshot")["clock"]["tick"] == 123 and s.version == 6
    return s


LENS = {
    "candidates": [{"label": "shelter", "decisions": [{"option_id": "set_crew_location:shelter"}]}],
    "include_baseline": True,
    "horizon_ticks": 24,
    "samples": 4,
    "prediction_mode": "known_only",
}


@pytest.fixture(scope="module")
def recorded_client() -> Iterator[TestClient]:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite+aiosqlite:///{Path(tmp) / 'recovery.db'}"
        with TestClient(create_app(make_settings(url))) as c:
            yield c


# ----------------------------------------------------------------------------- F1
def test_f1_snapshot_and_bootstrap_alerts_expose_id(client: TestClient) -> None:
    s = Session(client)
    s.advance(130)  # dose-budget alerts are active after the tick-122 solar particle event
    snap = s.get("/snapshot")
    boot = s.get("/bootstrap")
    assert snap["alerts"], "the scenario raises alerts by tick 130"
    for alerts in (snap["alerts"], boot["snapshot"]["alerts"]):
        for a in alerts:
            assert "id" in a and "alert_id" not in a
            assert a["message_key"] == f"alert.{a['id']}"
    assert boot["snapshot"]["alerts"] == snap["alerts"]
    # alert_id is preserved where it is confirmed correct
    rules = s.get("/resources/radiation")["alert_rules"]
    assert rules and all("alert_id" in r and "id" not in r for r in rules)
    at_123 = recorded_scenario_to_tick_123(client)  # dose warnings are projected from here
    lens = client.post(f"{at_123.base}/future-lens/projections", json=LENS).json()
    warnings = [w for b in lens["branches"] for w in b["warnings"]]
    assert warnings and all("alert_id" in w and "id" not in w for w in warnings)


# ----------------------------------------------------------------------------- F2
def test_f2_participant_id_is_null_without_participant(client: TestClient) -> None:
    s = Session(client)
    result = s.decide("set_ration_level", parameters={"level": 0.9})
    assert result["decision"]["participant_id"] is None
    assert s.get("/history")["decisions"][0]["participant_id"] is None


def test_f2_participant_id_propagates_through_every_decision_view(client: TestClient) -> None:
    s = Session(client, participants=[{"handle": "cdr", "role": "commander"}])
    pid = s.body["participants"][0]["id"]
    before = s.version
    result = s.decide("set_ration_level", parameters={"level": 0.9}, participant_id=pid)
    decision = result["decision"]
    assert decision["participant_id"] == pid
    # history
    assert s.get("/history")["decisions"][0]["participant_id"] == pid
    # DECISION_ACCEPTED realtime event
    events = s.get("/events", last_state_version=before)["events"]
    accepted = [e for e in events if e["type"] == "DECISION_ACCEPTED"]
    assert accepted and accepted[0]["payload"]["decision"]["participant_id"] == pid
    # rewind views
    preview = s.get(f"/rewind-points/{decision['decision_id']}/preview")
    assert preview["replaced_decision"]["participant_id"] == pid
    r = client.post(
        f"{s.base}/timeline-branches",
        json={
            "decision_id": decision["decision_id"],
            "alternative": {"option_id": "set_ration_level", "parameters": {"level": 0.8}},
            "participant_id": pid,
            "activate": False,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["alternative_decision"]["participant_id"] == pid


# ----------------------------------------------------------------------------- F3
def test_f3_recorded_future_lens_explanation_names_projected_dose(
    recorded_client: TestClient,
) -> None:
    s = recorded_scenario_to_tick_123(recorded_client)
    view = recorded_client.post(f"{s.base}/future-lens/projections", json=LENS).json()
    baseline = view["branches"][0]
    assert baseline["is_baseline"] and baseline["explanations"]
    assert {e["target_metric"] for e in baseline["explanations"]} == {"crew.projected_dose_msv"}
    # the engine is unchanged: its raw trace targets the margin metric, explained by the
    # projected dose directly upstream on the same chain
    raw = recorded_client.post(
        f"{s.base}/future-lens",
        json={
            "candidates": [
                {
                    "label": "shelter",
                    "decisions": [{"type": "set_crew_location", "location": "shelter"}],
                }
            ],
            "horizon_ticks": 24,
            "samples": 4,
        },
    ).json()
    traces = raw["predictions"][0]["causal_explanation"]
    assert traces
    for t in traces:
        assert t["target_metric"] == "crew.projected_dose_margin_msv"
        assert t["chains"][0][-2:] == [
            "metric:crew.projected_dose_msv",
            "metric:crew.projected_dose_margin_msv",
        ]
    assert view["request_hash"] == raw["request_hash"]


# ----------------------------------------------------------------------------- F4
def test_f4_key_moments_exclude_random_wear_faults(recorded_client: TestClient) -> None:
    s = recorded_scenario_to_tick_123(recorded_client)
    s.advance(1)
    s.decide("set_crew_location:shelter")
    s.advance(12)
    s.decide("set_crew_location:habitat")
    s.run_to_end()
    bb = s.get("/black-box/summary")
    late = [(m["tick"], m["key"]) for m in bb["key_moments"] if m["tick"] >= 120]
    assert late[:2] == [(139, "communication_loss"), (159, "resource_cascade")]
    ticks = [m["tick"] for m in bb["key_moments"]]
    assert ticks == sorted(ticks)  # chronological
    keys = {m["key"] for m in bb["key_moments"]}
    assert "water_processor_pump_fault" in keys  # designed incident stays a key moment
    assert not any(k.startswith("fault:") for k in keys)
    # the wear fault is still in the underlying report
    raw = s.get("/black-box", counterfactuals="false")
    assert (146, "fault:oxygen_generator") in {(f["tick"], f["key"]) for f in raw["failures"]}


# ----------------------------------------------------------------------------- F13
def test_f13_resume_semantics(client: TestClient) -> None:
    s = Session(client)
    other = Session(client, seed=7)
    s.advance(2)  # versions 1 (created) and 2 (advance) are retained
    all_events = s.get("/events", last_state_version=0)
    assert all_events["resync_required"] is False
    events = all_events["events"]
    assert {e["state_version"] for e in events} == {1, 2}
    tl = events[0]["timeline_id"]

    # latest event cursor → empty page
    latest = s.get("/events", last_event_id=events[-1]["event_id"])
    assert latest["resync_required"] is False and latest["events"] == []

    # mid-group cursor → the rest of that group, then later groups
    mid = s.get("/events", last_state_version=1, last_seq=0)["events"]
    assert [(e["state_version"], e["seq"]) for e in mid] == [
        (e["state_version"], e["seq"]) for e in events if (e["state_version"], e["seq"]) > (1, 0)
    ]

    # auxiliary event id → end of that version
    aux = s.get("/events", last_event_id=f"{tl}:1:aux:0123456789abcdef")["events"]
    assert aux and {e["state_version"] for e in aux} == {2} and aux[0]["seq"] == 0

    # sequence beyond the group → events_unavailable
    beyond = s.get("/events", last_event_id=f"{tl}:1:99")
    assert beyond["resync_required"] is True and beyond["reason"] == "events_unavailable"

    # a timeline of another session → unknown_timeline
    other_tl = other.get("/snapshot")["timeline"]["id"]
    foreign = s.get("/events", last_event_id=f"{other_tl}:1:0")
    assert foreign["resync_required"] is True and foreign["reason"] == "unknown_timeline"

    # negative state version → 422 VALIDATION_ERROR
    r = client.get(f"{s.base}/events", params={"last_state_version": -1})
    assert r.status_code == 422 and error(r)["code"] == "VALIDATION_ERROR"

    # no cursor → 422 cursor_required
    r = client.get(f"{s.base}/events")
    err = error(r)
    assert r.status_code == 422 and err["code"] == "INVALID_REQUEST"
    assert err["reason"] == "cursor_required"


def test_f13_real_auxiliary_event_id_resumes_after_its_version(client: TestClient) -> None:
    """An auxiliary event id published on the WebSocket is a valid resume cursor."""
    s = Session(client)
    with client.websocket_connect(f"{API}/ws/mission-sessions/{s.sid}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        r = client.post(f"{s.base}/future-lens/projections", json={**LENS, "samples": 1})
        assert r.status_code == 200, r.text
        ready = ws.receive_json()
    assert ready["type"] == "FUTURE_LENS_READY" and ready["seq"] == -1
    assert ":aux:" in ready["event_id"]
    version = ready["state_version"]
    s.advance(1)
    after = s.get("/events", last_event_id=ready["event_id"])
    assert after["resync_required"] is False
    assert {e["state_version"] for e in after["events"]} == {version + 1}
