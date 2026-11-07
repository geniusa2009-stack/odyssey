"""D25: future phase names and unforeseeable event names never reach a client early.

The phase visibility rule (app/read_models/visibility.py) is derived from the scenario's phase
schedule and event foreseeability, never from names. These tests check the rule itself, that
withholding does not depend on whether hidden events exist (so ``null`` reveals nothing), that it
is applied in every frontend-safe channel (REST, WebSocket, Future Lens), and that the
simulation and the scenario are unchanged.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.read_models.analysis import build_future_lens_view
from app.read_models.mission import build_phase
from app.read_models.visibility import (
    WITHHELD_EVENT_USAGE,
    compute_phase_visibility,
    entered_phases,
)
from app.simulation.analysis.future_lens import CandidateBranch, FutureLens, FutureLensRequest
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario, scenario_content_hash
from app.simulation.scenarios.schema import ScenarioDefinition
from tests.conftest import make_settings
from tests.test_contract_api import Mission
from tests.test_contract_hidden_information import without_future_hidden_events

API = "/api/v1"
SC = get_scenario("luna-01")
V020_HASH = "ced64e641c46c061aa9ae1d467e90b88b2555ca5c358ca87bd33c078a5ce0e2d"
UNFORESEEABLE = sorted(e.id for e in SC.events if not e.foreseeable)


def variant(mutate: Any) -> ScenarioDefinition:
    data = SC.model_dump(mode="json", by_alias=True)
    mutate(data)
    return ScenarioDefinition.model_validate(data)


def withheld(sc: ScenarioDefinition) -> list[int]:
    """Positions (not names) of the phases withheld until entered."""
    hidden = compute_phase_visibility(sc).withheld_until_entered
    return [i for i, p in enumerate(sc.phases) if p.id in hidden]


def play(engine: SimulationEngine, ticks: int, seed: int = 4) -> MissionState:
    return engine.advance(engine.initial_state(seed), ticks).state


# ----------------------------------------------------------------------------- the rule
def test_rule_on_luna01() -> None:
    v = compute_phase_visibility(SC)
    assert v.bound_events == {
        "environmental_emergency": ("solar_particle_event",),
        "communication_loss": ("relay_outage",),
        "resource_cascade": ("water_processor_pump_fault",),
    }
    # announced = a planned (foreseeable, scheduled) milestone lies in the window
    assert v.announced == {
        "base_setup",
        "initial_resource_management",
        "reduced_solar_availability",
        "scientific_opportunity",
        "rover_decision",
        "final_low_power",
    }
    assert v.withheld_until_entered == {
        "power_management",  # no planned milestone: withheld although nothing hidden happens
        "environmental_emergency",
        "communication_loss",
        "resource_cascade",
    }


@pytest.mark.parametrize("t", [0, 60, 100, 121, 139, 159, 179])
def test_withholding_does_not_depend_on_hidden_events(t: int) -> None:
    """``null`` must not signal a secret: the same phases are withheld whether or not the
    unforeseeable events exist (after t, or at all)."""
    assert withheld(without_future_hidden_events(SC, t)) == withheld(SC)
    assert withheld(
        variant(lambda d: d.update(events=[e for e in d["events"] if e["foreseeable"]]))
    ) == withheld(SC)


def test_rule_does_not_depend_on_names() -> None:
    def rename(d: dict[str, Any]) -> None:
        mapping = {p["id"]: f"chapter_{i}" for i, p in enumerate(d["phases"])}
        for p in d["phases"]:
            p["id"] = mapping[p["id"]]
        for e in d["events"]:
            e["id"] = "e_" + str(abs(hash(e["id"])) % 10_000)

    assert withheld(variant(rename)) == withheld(SC)


def _event(d: dict[str, Any], event_id: str) -> dict[str, Any]:
    return next(e for e in d["events"] if e["id"] == event_id)


def test_a_planned_milestone_does_not_unmask_a_hidden_event_phase() -> None:
    """Safety net: a chapter with a planned milestone *and* a bound unforeseeable event stays
    withheld."""

    def add_milestone(d: dict[str, Any]) -> None:
        extra = dict(_event(d, "landing_complete"))
        extra["id"] = "planned_check_in"
        extra["trigger"] = {"type": "scheduled", "at_tick": 125}
        d["events"].append(extra)

    sc = variant(add_milestone)
    assert "environmental_emergency" in compute_phase_visibility(sc).withheld_until_entered


def test_an_announced_known_chapter_is_shown() -> None:
    """A chapter announced by the plan with nothing hidden in it is shown in advance."""

    def make_storm_foreseeable_and_announce(d: dict[str, Any]) -> None:
        _event(d, "solar_particle_event")["foreseeable"] = True

    sc = variant(make_storm_foreseeable_and_announce)
    v = compute_phase_visibility(sc)
    assert "environmental_emergency" in v.announced  # the (now foreseeable) storm announces it
    assert "environmental_emergency" not in v.withheld_until_entered


def test_unscheduled_transitions_withhold_every_later_phase() -> None:
    def state_triggered(d: dict[str, Any]) -> None:
        p = next(p for p in d["phases"] if p["id"] == "power_management")
        p["advance_when"] = {"metric": "power.battery_soc", "op": "<", "value": 0.5}

    sc = variant(state_triggered)
    hidden = compute_phase_visibility(sc).withheld_until_entered
    ids = [p.id for p in sc.phases]
    after = ids[ids.index("power_management") + 1 :]
    assert {p for p in after if sc.phases[ids.index(p)].kind == "simulated"} <= hidden
    assert "mission_conclusion" not in hidden  # structural phases are always known


# ----------------------------------------------------------------------------- next_phase
@pytest.mark.parametrize(
    ("tick", "current", "expected_next", "withheld_next"),
    [
        (30, "initial_resource_management", "reduced_solar_availability", False),
        (60, "reduced_solar_availability", None, True),  # power_management: no planned milestone
        (80, "power_management", "scientific_opportunity", False),
        (100, "scientific_opportunity", None, True),  # the hidden emergency is not revealed
        (119, "scientific_opportunity", None, True),
        (125, "environmental_emergency", None, True),  # current is visible; next is not
        (165, "resource_cascade", "rover_decision", False),
        (205, "final_low_power", "mission_conclusion", False),
    ],
)
def test_next_phase(
    engine: SimulationEngine,
    tick: int,
    current: str,
    expected_next: str | None,
    withheld_next: bool,
) -> None:
    view = build_phase(engine, play(engine, tick))
    assert view.id == current
    assert view.next_phase == expected_next
    assert view.next_phase_withheld is withheld_next


# ----------------------------------------------------------------------------- every channel
def secret_tokens(ms: Mission) -> set[str]:
    """Names a client must not see yet: withheld phases not entered, unforeseeable events that
    have not happened."""
    hist = ms.get("/history")
    entered = {p["phase"] for p in hist["phases"]}
    happened = {e["key"] for e in hist["events"]}
    hidden_phases = compute_phase_visibility(SC).withheld_until_entered - entered
    return set(hidden_phases) | (set(UNFORESEEABLE) - happened)


def frontend_responses(c: TestClient, ms: Mission) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in (
        "/bootstrap",
        "/snapshot",
        "/objectives",
        "/decision-options",
        "/radiation-budget",
        "/completion",
        "/history",
        "/timelines",
        "/rewind-points",
        "/black-box/summary",
        "/engineering-profile",
        "/mission-dna/share",
    ):
        out[path] = ms.get(path)
    for rid in (r["id"] for r in out["/snapshot"]["resources"]):
        out[f"/resources/{rid}"] = ms.get(f"/resources/{rid}")
    out["/events"] = ms.get("/events", last_state_version=1)
    points = out["/rewind-points"]["points"]
    if points:
        out["/preview"] = ms.get(f"/rewind-points/{points[0]['decision_id']}/preview")
    lens = c.post(
        f"{ms.base}/future-lens/projections",
        json={
            "candidates": [
                {"label": "shelter", "decisions": [{"option_id": "set_crew_location:shelter"}]}
            ],
            "horizon_ticks": 48,
            "samples": 2,
        },
    )
    assert lens.status_code == 200, lens.text
    out["/future-lens"] = lens.json()
    for path in ("/capabilities", "/science/claims", "/science/evidence", "/missions"):
        out[path] = c.get(f"{API}{path}").json()
    out["/session"] = c.get(ms.base).json()
    return out


@pytest.mark.parametrize("ticks", [0, 60, 100, 119])
def test_no_frontend_response_names_a_secret(client: TestClient, ticks: int) -> None:
    ms = Mission(client, seed=4)
    if ticks:
        ms.advance(min(ticks, 20))
        ms.decide("start_science_activity:regolith_survey")
        if ticks > 20:
            ms.advance(ticks - 20)
    tokens = secret_tokens(ms)
    assert "environmental_emergency" in tokens and "solar_particle_event" in tokens
    for path, body in frontend_responses(client, ms).items():
        text = json.dumps(body)
        leaked = sorted(t for t in tokens if t in text)
        assert not leaked, (path, leaked)


def test_bootstrap_lists_withheld_phases_by_position(client: TestClient) -> None:
    ms = Mission(client)
    phases = ms.get("/bootstrap")["scenario"]["phases"]
    assert len(phases) == len(SC.phases)
    assert [i for i, p in enumerate(phases) if p["withheld"]] == withheld(SC)
    assert all(p["id"] is None for p in phases if p["withheld"])
    ms.advance(125)
    phases = ms.get("/bootstrap")["scenario"]["phases"]
    ids = [p["id"] for p in phases]
    assert "environmental_emergency" in ids  # entered: now known
    assert "communication_loss" not in ids  # still ahead
    assert "power_management" in ids


def test_realtime_frames_do_not_name_a_secret(client: TestClient) -> None:
    ms = Mission(client, seed=4)
    with client.websocket_connect(f"{API}/ws/mission-sessions/{ms.sid}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        frames: list[dict[str, Any]] = []
        for ticks in (20, 40, 59):  # to tick 119, just before the emergency phase
            ms.advance(ticks)
            while not frames or frames[-1]["type"] != "MISSION_STATE_CHANGED":
                frames.append(ws.receive_json())
            frames.append({"type": "_"})
        tokens = secret_tokens(ms)
        text = json.dumps(frames)
        assert not sorted(t for t in tokens if t in text)
        ms.advance(2)  # tick 121: the emergency phase begins (a present fact)
        later: list[dict[str, Any]] = []
        while not later or later[-1]["type"] != "MISSION_STATE_CHANGED":
            later.append(ws.receive_json())
    phase_changes = [f["payload"]["to"] for f in later if f["type"] == "PHASE_CHANGED"]
    assert phase_changes == ["environmental_emergency"]
    assert "communication_loss" not in json.dumps(later)


# ----------------------------------------------------------------------------- Future Lens
def test_future_lens_engine_unchanged_view_withholds(engine: SimulationEngine) -> None:
    state = play(engine, 100)
    request = FutureLensRequest(
        candidates=[CandidateBranch(label="none", decisions=[])], horizon_ticks=48, samples=2
    )
    raw = FutureLens(engine).predict(state, request)
    assert {p.projected_phase for p in raw.predictions} == {
        "communication_loss"
    }  # engine as before
    view = build_future_lens_view(
        engine,
        raw,
        session_id="s",
        timeline_id="t",
        state_version=1,
        requested_ticks=48,
        entered=entered_phases(state),
    )
    assert all(b.projected_phase is None and b.projected_phase_withheld for b in view.branches)
    omni_raw = FutureLens(engine).predict(
        state, request.model_copy(update={"knowledge_policy": "omniscient"})
    )
    omni = build_future_lens_view(
        engine,
        omni_raw,
        session_id="s",
        timeline_id="t",
        state_version=1,
        requested_ticks=48,
        entered=entered_phases(state),
    )
    assert all(b.projected_phase == "communication_loss" for b in omni.branches)  # by design
    assert not any(b.projected_phase_withheld for b in omni.branches)
    later = play(engine, 150)  # inside communication_loss: projecting within known phases
    raw_later = FutureLens(engine).predict(later, request.model_copy(update={"horizon_ticks": 5}))
    view_later = build_future_lens_view(
        engine,
        raw_later,
        session_id="s",
        timeline_id="t",
        state_version=1,
        requested_ticks=5,
        entered=entered_phases(later),
    )
    assert {b.projected_phase for b in view_later.branches} == {"communication_loss"}


# ----------------------------------------------------------------------------- unchanged
def test_scenario_and_simulation_unchanged(engine: SimulationEngine) -> None:
    assert scenario_content_hash(SC) == V020_HASH
    assert SC.power.battery.capacity_kwh == 240.0 and SC.power.solar_rated_kw == 12.0
    state = play(engine, 240, seed=12345)
    assert state.state_hash().startswith("da7349cb7f1d5c75")  # Phase 3 determinism hash


def test_science_claims_do_not_name_unforeseeable_events(client: TestClient) -> None:
    claims = {c["id"]: c for c in client.get(f"{API}/science/claims").json()}
    usage = claims["donki_sep_events"]["simulation_usage"]
    assert WITHHELD_EVENT_USAGE in usage
    assert not any("solar_particle_event" in u for u in usage)
    from app.science.evidence import default_registry

    raw = next(e for e in default_registry().all() if e.id == "donki_sep_events")
    assert "events.solar_particle_event" in raw.simulation_usage  # source data untouched


def test_omniscient_projection_still_named_when_enabled(sqlite_url: str) -> None:
    settings = make_settings(sqlite_url, future_lens_omniscient_enabled=True)
    with TestClient(create_app(settings)) as c:
        ms = Mission(c)
        ms.advance(100)
        r = c.post(
            f"{ms.base}/future-lens/projections",
            json={
                "candidates": [{"label": "x", "decisions": []}],
                "horizon_ticks": 48,
                "samples": 1,
                "prediction_mode": "omniscient",
            },
        )
        assert {b["projected_phase"] for b in r.json()["branches"]} == {"communication_loss"}
