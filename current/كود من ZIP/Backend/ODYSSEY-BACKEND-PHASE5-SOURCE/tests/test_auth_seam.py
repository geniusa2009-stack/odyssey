"""Without authentication, no caller can corrupt simulation state (Phase 2 audit).

What an unauthenticated caller CAN do with a session id: make *valid* moves (decide, advance,
rewind) like a player — vandalism, not corruption. What they CANNOT do, verified here:

* reach another session's timeline, participants or decisions;
* impersonate a participant of another session, or claim a role that a policy denies;
* write anything the engine has not validated, rewrite the ledger, or desynchronise the stored
  head from its replay;
* use Future Lens or ORION to change the mission.

The integration point for real authentication is ``MissionService._authorize`` (see
docs/ARCHITECTURE.md, "Authentication seam").
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.container import build_container
from app.main import create_app
from app.services.permissions import MissionAction, MissionRole, RoleTablePolicy
from tests.conftest import make_settings

API = "/api/v1"


def _session(c: TestClient, **extra: Any) -> dict[str, Any]:
    r = c.post(f"{API}/mission-sessions", json={"seed": 5, **extra})
    assert r.status_code == 201
    body: dict[str, Any] = r.json()
    return body


def test_sessions_are_isolated(client: TestClient) -> None:
    a = _session(client, participants=[{"handle": "ana", "role": "commander"}])
    b = _session(client)
    a_participant = a["participants"][0]["id"]
    # a's timeline cannot be addressed through b
    r = client.get(
        f"{API}/mission-sessions/{b['id']}/state", params={"timeline_id": a["active_timeline_id"]}
    )
    assert r.status_code == 404
    r = client.post(
        f"{API}/mission-sessions/{b['id']}/advance",
        json={"ticks": 1, "timeline_id": a["active_timeline_id"]},
    )
    assert r.status_code == 404
    # a's participant cannot act in b
    r = client.post(
        f"{API}/mission-sessions/{b['id']}/decisions",
        json={
            "decision": {"type": "set_ration_level", "level": 0.9},
            "participant_id": a_participant,
        },
    )
    # Phase 4: the specific cause is in `reason` (`code` is the public code INVALID_REQUEST)
    assert r.status_code == 422 and r.json()["error"]["reason"] == "unknown_participant"
    # a is untouched by everything above
    state = client.get(f"{API}/mission-sessions/{a['id']}/state").json()
    assert state["tick"] == 0 and state["state"]["decisions_applied"] == 0


def test_rewind_cannot_target_another_sessions_decision(client: TestClient) -> None:
    a, b = _session(client), _session(client)
    d = client.post(
        f"{API}/mission-sessions/{a['id']}/decisions",
        json={"decision": {"type": "set_ration_level", "level": 0.9}},
    ).json()["decision"]
    r = client.post(
        f"{API}/mission-sessions/{b['id']}/rewind", json={"decision_id": d["decision_id"]}
    )
    assert r.status_code == 404


def test_vandalism_is_still_valid_play_and_verifiable(client: TestClient) -> None:
    s = _session(client)
    sid = s["id"]
    for body in (
        {"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "off"},
        {"type": "set_thermal_setpoint", "target_c": 10},
        {"type": "schedule_maintenance", "component": "warp_core"},
        {"type": "set_thermal_setpoint", "target_c": 99},
    ):
        client.post(f"{API}/mission-sessions/{sid}/decisions", json={"decision": body})
    client.post(f"{API}/mission-sessions/{sid}/advance", json={"ticks": 50})
    verify = client.get(f"{API}/mission-sessions/{sid}/verify").json()
    assert verify["ledger_ok"] and verify["replay_ok"] and verify["decisions_verified"] == 2


def test_future_lens_and_orion_respect_the_policy(sqlite_url: str) -> None:
    # Phase 4: omniscient projections also need the server switch (off by default); the role
    # policy then decides who may use them.
    settings = make_settings(sqlite_url, future_lens_omniscient_enabled=True)
    container = build_container(settings)
    container.policy = RoleTablePolicy(
        {
            MissionRole.COMMANDER: {MissionAction.FUTURE_LENS: ["*"], MissionAction.ORION: ["*"]},
            MissionRole.SCIENCE_OFFICER: {
                MissionAction.FUTURE_LENS: ["known_only"],
                MissionAction.ORION: ["state_summary"],
            },
        }
    )
    with TestClient(create_app(settings, container)) as c:
        s = _session(
            c,
            participants=[
                {"handle": "teacher", "role": "commander"},
                {"handle": "student", "role": "science_officer"},
            ],
        )
        ids = {p["role"]: p["id"] for p in s["participants"]}
        sid = s["id"]
        lens = {"candidates": [{"label": "x", "decisions": []}], "samples": 1}
        ok = c.post(
            f"{API}/mission-sessions/{sid}/future-lens",
            json={**lens, "participant_id": ids["science_officer"]},
        )
        assert ok.status_code == 200
        denied = c.post(
            f"{API}/mission-sessions/{sid}/future-lens",
            json={
                **lens,
                "knowledge_policy": "omniscient",
                "participant_id": ids["science_officer"],
            },
        )
        assert denied.status_code == 403
        teacher = c.post(
            f"{API}/mission-sessions/{sid}/future-lens",
            json={**lens, "knowledge_policy": "omniscient", "participant_id": ids["commander"]},
        )
        assert teacher.status_code == 200
        why = c.post(
            f"{API}/mission-sessions/{sid}/orion/explain",
            json={
                "topic": "why",
                "metric": "power.battery_soc",
                "participant_id": ids["science_officer"],
            },
        )
        assert why.status_code == 403
        assert (
            c.post(
                f"{API}/mission-sessions/{sid}/orion/explain",
                json={"participant_id": ids["science_officer"]},
            ).status_code
            == 200
        )
        state = c.get(f"{API}/mission-sessions/{sid}/state").json()
        assert state["state"]["decisions_applied"] == 0 and state["tick"] == 0
