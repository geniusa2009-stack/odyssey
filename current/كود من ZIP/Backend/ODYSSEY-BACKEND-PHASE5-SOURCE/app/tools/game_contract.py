"""Frozen ``odyssey.game.v1`` contract artifacts (separate from API v1).

* ``tests/fixtures/game/openapi-game-v1.json`` — normalised OpenAPI document of the game API
* ``tests/fixtures/game/examples/*.json``     — deterministic Unreal handoff examples

``python -m app.tools.game_contract --check`` (exit 1 and list differences when anything changed)
``python -m app.tools.game_contract --write`` (regenerate after a reviewed contract change)

The examples are *recorded* from a scripted Earth Command → LUNA-01 session driven through the
real mounted game API (temporary SQLite database, deterministic server clock, counter-based ids
and seed, fixed timestamps and request ids), so they are actual server output validated against
the real response models — never hand-written. Each example lists the model that validates it
in ``index.json``.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import json
import re
import secrets
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from app.tools.contract_fixtures import deterministic_uuids
from app.tools.openapi_snapshot import differences

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = ROOT / "tests" / "fixtures" / "game"
OPENAPI = GAME_DIR / "openapi-game-v1.json"
EXAMPLES = GAME_DIR / "examples"
GAME = "/api/game/v1"
E = "earth.command."
LUNA01 = E + "hangar.luna01"
STORAGE = E + "hangar.storage"
FIXED_TIME = "2026-10-27T06:00:00+00:00"
FIXED_REQUEST_ID = "00000000000000000000000000000000"
SESSION_SEED = 20261027
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")

# example name → (contract model path, description)
MODELS: dict[str, tuple[str, str]] = {
    "create_session_response": (
        "app.game.contracts.protocol:CreateGameSessionResponse",
        "POST /sessions → token (shown once) and bootstrap",
    ),
    "bootstrap": ("app.game.contracts.protocol:GameBootstrap", "GET /sessions/{id}/bootstrap"),
    "snapshot_incident": (
        "app.game.contracts.protocol:GameSnapshot",
        "GET /sessions/{id}/snapshot during the power incident (clock DECISION_PAUSED)",
    ),
    "command_request": (
        "app.game.contracts.protocol:GameCommandRequest",
        "POST /sessions/{id}/commands body (semantic action)",
    ),
    "command_response": (
        "app.game.contracts.protocol:CommandResult",
        "Response to the semantic action above",
    ),
    "error_stale_state": (
        "app.game.contracts.protocol:GameErrorResponse",
        "409 STALE_STATE: expected_state_version is behind; refresh the snapshot and retry",
    ),
    "error_action_unavailable": (
        "app.game.contracts.protocol:GameErrorResponse",
        "409 DECISION_UNAVAILABLE with a safe reason (not_at_location)",
    ),
    "error_mars_locked": (
        "app.game.contracts.protocol:GameErrorResponse",
        "409 mars_mission_locked: lock_code MARS_MISSION_LOCKED + missing capability ids",
    ),
    "event_inventory_changed": (
        "app.game.contracts.protocol:GameEventEnvelope",
        "cargo.changed/inventory.changed after a transfer",
    ),
    "event_incident_started": (
        "app.game.contracts.protocol:GameEventEnvelope",
        "incident.started (only once the hidden fault has happened)",
    ),
    "event_mission_updated": (
        "app.game.contracts.protocol:GameEventEnvelope",
        "objective/mission update",
    ),
    "event_certification_granted": (
        "app.game.contracts.protocol:GameEventEnvelope",
        "certification.granted at mission completion",
    ),
    "event_mission_transitioned": (
        "app.game.contracts.protocol:GameEventEnvelope",
        "mission.transitioned Earth Command → LUNA-01 (snapshot_required)",
    ),
    "future_lens_response": (
        "app.game.contracts.analysis:GameFutureLensView",
        "POST /sessions/{id}/future-lens (known_only)",
    ),
    "black_box_response": (
        "app.game.contracts.analysis:GameBlackBoxView",
        "GET /sessions/{id}/black-box for a concluded LUNA-01 timeline (causal graph)",
    ),
    "black_box_earth_command": (
        "app.game.contracts.analysis:GameBlackBoxView",
        "Black Box of the authorization-completed Earth Command timeline (simulation_status "
        "stays active: authorization ends the game mission, not the simulation)",
    ),
    "event_mission_failed_or_completed": (
        "app.game.contracts.protocol:GameEventEnvelope",
        "black_box.ready when a mission ends (here: LUNA-01 concluded)",
    ),
    "restore_response": (
        "app.game.contracts.protocol:RestoreResult",
        "POST /sessions/{id}/restore after a disconnect (single restore path)",
    ),
    "ws_resumed": (
        "app.game.contracts.protocol:GameControlFrame",
        "WebSocket RESUMED control frame (resume from last_seq)",
    ),
    "ws_resync_required": (
        "app.game.contracts.protocol:GameControlFrame",
        "WebSocket RESYNC_REQUIRED control frame (call the restore path)",
    ),
    "capabilities": ("app.game.contracts.progression:CapabilitiesView", "GET .../capabilities"),
    "readiness_mars": (
        "app.game.contracts.progression:ReadinessView",
        "GET .../readiness/mars_01_human_mission",
    ),
    "expansion_map": (
        "app.game.contracts.progression:ExpansionMapView",
        "GET .../expansion-map (Human Expansion Map)",
    ),
    "vehicle_luna01": ("app.game.contracts.progression:VehicleView", "GET .../vehicles/{id}"),
    "why_insight": ("app.game.contracts.progression:WhyView", "GET .../insights/{id}/why"),
    "features": ("app.game.contracts.protocol:ServerFeatures", "GET /features"),
}


# ------------------------------------------------------------------ determinism helpers
@contextlib.contextmanager
def deterministic_secrets() -> Iterator[None]:
    """Counter-based public ids/tokens and a fixed session seed for the recording run."""
    counter = itertools.count(1)

    def token_bytes(nbytes: int | None = None) -> bytes:
        return next(counter).to_bytes(nbytes or 32, "big")

    def token_urlsafe(nbytes: int | None = None) -> str:
        return f"fixture-token-{next(counter):04d}"

    def randbelow(exclusive_upper_bound: int) -> int:
        return SESSION_SEED % exclusive_upper_bound

    patched = {"token_bytes": token_bytes, "token_urlsafe": token_urlsafe, "randbelow": randbelow}
    originals = {name: getattr(secrets, name) for name in patched}
    for name, fn in patched.items():
        setattr(secrets, name, fn)
    try:
        yield
    finally:
        for name, fn in originals.items():
            setattr(secrets, name, fn)


def _normalise(value: Any) -> Any:
    if isinstance(value, dict):
        out = {k: _normalise(v) for k, v in value.items()}
        if "request_id" in out and isinstance(out["request_id"], str):
            out["request_id"] = FIXED_REQUEST_ID
        return out
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    if isinstance(value, str) and _TIMESTAMP.match(value):
        return FIXED_TIME
    return value


def render(value: Any) -> str:
    return json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def _model(path: str) -> Any:
    module, _, name = path.partition(":")
    mod = __import__(module, fromlist=[name])
    return getattr(mod, name)


# ------------------------------------------------------------------ OpenAPI
def current_openapi() -> dict[str, Any]:
    from app.core.config import Settings
    from app.game.api.app import create_game_app

    settings = Settings(
        environment="test", database_url="sqlite+aiosqlite:///:memory:", log_json=False
    )
    schema = create_game_app(settings).openapi()
    normalized: dict[str, Any] = json.loads(json.dumps(schema, sort_keys=True))
    return normalized


# ------------------------------------------------------------------ recorded examples
def generate_examples() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.game.application.identity import AnonymousIdentityProvider
    from app.game.application.runtime import GameRuntime
    from app.game.content.loader import default_content
    from app.game.realtime.bus import InMemoryGameBus
    from app.game.runtime.clock import FakeClock
    from app.main import create_app

    out: dict[str, Any] = {}
    clock = FakeClock()
    runtime = GameRuntime(
        content=default_content(),
        bus=InMemoryGameBus(),
        clock=clock,
        identity=AnonymousIdentityProvider(),
    )
    with tempfile.TemporaryDirectory() as tmp, deterministic_uuids(), deterministic_secrets():
        settings = Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{Path(tmp) / 'game-fixtures.db'}",
            auto_create_schema=True,
            log_json=False,
            log_level="WARNING",
            rate_limit_per_minute=100_000,
            rate_limit_expensive_per_minute=100_000,
            redis_url=None,
        )
        with TestClient(create_app(settings, game_runtime=runtime)) as c:
            created = c.post(f"{GAME}/sessions", json={"display_name": "Commander"})
            assert created.status_code == 201, created.text
            out["create_session_response"] = created.json()
            token = created.json()["session_token"]
            sid = created.json()["bootstrap"]["snapshot"]["session"]["id"]
            headers = {"Authorization": f"Bearer {token}"}
            base = f"{GAME}/sessions/{sid}"
            st = {"v": created.json()["bootstrap"]["snapshot"]["state_version"], "n": 0}
            events: list[dict[str, Any]] = []

            def ok(resp: Any) -> Any:
                assert resp.status_code < 300, resp.text
                return resp.json()

            def get(path: str, **params: Any) -> Any:
                return ok(c.get(f"{base}{path}", params=params, headers=headers))

            def body(action: str, target: str | None = None, **params: Any) -> dict[str, Any]:
                st["n"] += 1
                b: dict[str, Any] = {
                    "command_id": f"cmd-{st['n']:04d}",
                    "session_id": sid,
                    "expected_state_version": st["v"],
                    "idempotency_key": f"idem-{st['n']:06d}",
                    "action": action,
                    "params": params,
                }
                if target is not None:
                    b["target"] = target
                return b

            def act(action: str, target: str | None = None, **params: Any) -> Any:
                res = ok(
                    c.post(f"{base}/commands", json=body(action, target, **params), headers=headers)
                )
                st["v"] = res["state_version"]
                events.extend(res["events"])
                return res

            def wait(seconds: float) -> Any:
                clock.advance(seconds)
                res = ok(c.post(f"{base}/sync", json={}, headers=headers))
                st["v"] = res["state_version"]
                events.extend(res["events"])
                return res

            def first(etype: str) -> dict[str, Any]:
                return next(e for e in events if e["type"] == etype)

            out["features"] = ok(c.get(f"{GAME}/features"))
            out["bootstrap"] = get("/bootstrap")
            req = body("world.zone_entered", E + "engineering")
            st["n"] -= 1
            out["command_request"] = req
            out["command_response"] = act("world.zone_entered", E + "engineering")
            stale = dict(req, command_id="cmd-stale", idempotency_key="idem-stale-0001")
            r = c.post(f"{base}/commands", json=stale, headers=headers)
            assert r.status_code == 409, r.text
            out["error_stale_state"] = r.json()
            wait(30)
            out["snapshot_incident"] = get("/snapshot")
            out["event_incident_started"] = first("incident.started")
            act("system.inspect", E + "engineering.power_bus_b")
            # the training simulator is in another room: a safe, recoverable rejection
            r = c.post(
                f"{base}/commands",
                json=body("system.set_mode", E + "training.simulator", mode="off"),
                headers=headers,
            )
            assert r.status_code == 409, r.text
            st["n"] -= 1
            out["error_action_unavailable"] = r.json()
            act("world.zone_entered", E + "training")
            act("system.set_mode", E + "training.simulator", mode="off")
            act("world.zone_entered", E + "engineering")
            act("repair.perform", E + "engineering.power_bus_b")
            act("mission.clock_set", mode="ACCELERATED")
            for _ in range(4):
                wait(5)
            out["event_mission_updated"] = next(
                e for e in events if e["type"] in {"objective.updated", "mission.updated"}
            )
            act("world.zone_entered", E + "hangar")
            for sub in ("power", "life_support", "comms", "radiation_protection"):
                act("system.inspect", f"{LUNA01}.{sub}")
            act("system.inspect", LUNA01 + ".cargo_hold")
            act(
                "module.install",
                LUNA01,
                slot="radiation_protection",
                item="module.radiation_shelter_liner",
                **{"from": STORAGE},
            )
            act(
                "cargo.transfer",
                LUNA01 + ".cargo_hold",
                item="cargo.water_tank",
                quantity=2,
                **{"from": STORAGE},
            )
            out["event_inventory_changed"] = next(
                e for e in events if e["type"] in {"cargo.changed", "inventory.changed"}
            )
            act(
                "cargo.transfer",
                LUNA01 + ".cargo_hold",
                item="spare.habitat_spares_kit",
                quantity=1,
                **{"from": STORAGE},
            )
            out["vehicle_luna01"] = get(f"/vehicles/{LUNA01}")
            out["future_lens_response"] = ok(
                c.post(
                    f"{base}/future-lens",
                    json={
                        "candidates": [
                            {
                                "id": "ground-support-eco",
                                "action": "system.set_mode",
                                "target": E + "hangar.ground_support",
                                "params": {"mode": "eco"},
                            },
                            {
                                "id": "ground-support-off",
                                "action": "system.set_mode",
                                "target": E + "hangar.ground_support",
                                "params": {"mode": "off"},
                            },
                            {
                                "id": "heat-eco-remote",
                                "action": "system.set_mode",
                                "target": E + "engineering.thermal_plant",
                                "params": {"mode": "eco"},
                            },
                        ],
                        "horizon_ticks": 12,
                    },
                    headers=headers,
                )
            )
            for _ in range(200):
                snap = get("/snapshot")
                st["v"] = snap["state_version"]
                lander = next(o for o in snap["world"]["objects"] if o["id"] == LUNA01)
                if (lander.get("charge_kwh") or 0.0) >= 45.0:
                    break
                wait(5)
            ec_timeline = get("/snapshot")["timeline"]["id"]
            done = act("mission.authorize", LUNA01)
            out["event_certification_granted"] = first("certification.granted")
            out["event_mission_transitioned"] = first("mission.transitioned")
            out["black_box_earth_command"] = get("/black-box", timeline_id=ec_timeline)
            out["capabilities"] = get("/capabilities")
            out["readiness_mars"] = get("/readiness/mars_01_human_mission")
            out["expansion_map"] = get("/expansion-map")
            out["why_insight"] = get("/insights/power.generation_vs_demand/why")
            r = c.post(
                f"{base}/phases/MARS_01/start",
                json={"expected_state_version": st["v"]},
                headers=headers,
            )
            assert r.status_code == 409, r.text
            out["error_mars_locked"] = r.json()
            last = done["last_seq"]
            out["restore_response"] = ok(
                c.post(f"{base}/restore", json={"last_seq": last - 3}, headers=headers)
            )
            ws = f"{GAME}/ws/sessions/{sid}?token={token}"
            with c.websocket_connect(f"{ws}&last_seq={last - 1}") as sock:
                out["ws_resumed"] = json.loads(sock.receive_text())
            with c.websocket_connect(f"{ws}&last_seq={last + 1000}") as sock:
                out["ws_resync_required"] = json.loads(sock.receive_text())
            # LUNA-01 under the server clock until the simulation concludes, then its Black Box
            act("world.zone_entered", "luna.asteria.habitat")
            act("mission.clock_set", mode="ACCELERATED")
            for _ in range(60):
                snap = get("/snapshot")
                st["v"] = snap["state_version"]
                if snap["mission"]["status"] != "active":
                    break
                if snap["clock"]["mode"] != "ACCELERATED":
                    storm = any(
                        i["id"] == "luna.asteria.radiation_storm" and i["stage"] == "active"
                        for i in snap["world"]["incidents"]
                    )
                    if storm:
                        act("crew.assign_location", "luna.asteria.shelter")
                    act("mission.clock_set", mode="ACCELERATED")
                wait(20)
            out["event_mission_failed_or_completed"] = next(
                e for e in reversed(events) if e["type"] == "black_box.ready"
            )
            out["black_box_response"] = get("/black-box")
    return {name: _normalise(value) for name, value in out.items()}


def validate_examples(examples: dict[str, Any]) -> list[str]:
    """Every example must validate against its real contract model."""
    problems: list[str] = []
    for name, value in examples.items():
        spec = MODELS.get(name)
        if spec is None:
            problems.append(f"{name}: no model registered")
            continue
        try:
            _model(spec[0]).model_validate(value)
        except Exception as exc:  # pydantic.ValidationError, import errors
            problems.append(f"{name}: {exc}")
    missing = sorted(set(MODELS) - set(examples))
    problems += [f"{name}: missing" for name in missing]
    return problems


def _index() -> dict[str, Any]:
    return {
        "protocol": "odyssey.game.v1",
        "generated_by": "python -m app.tools.game_contract --write",
        "examples": {
            name: {"file": f"{name}.json", "model": model, "description": desc}
            for name, (model, desc) in sorted(MODELS.items())
        },
    }


def _files() -> dict[Path, str]:
    examples = generate_examples()
    problems = validate_examples(examples)
    if problems:
        raise SystemExit("game examples do not validate:\n" + "\n".join(problems))
    files = {OPENAPI: render(current_openapi()), EXAMPLES / "index.json": render(_index())}
    for name, value in examples.items():
        files[EXAMPLES / f"{name}.json"] = render(value)
    return files


def main(argv: list[str] | None = None, *, files: Callable[[], dict[Path, str]] = _files) -> int:
    parser = argparse.ArgumentParser(description="odyssey.game.v1 contract artifacts")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    wanted = files()
    if args.write:
        EXAMPLES.mkdir(parents=True, exist_ok=True)
        for stale in EXAMPLES.glob("*.json"):
            if stale not in wanted:
                stale.unlink()
        for path, text in wanted.items():
            path.write_text(text, encoding="utf-8")
        print(f"wrote {len(wanted)} files under {GAME_DIR.relative_to(ROOT)}")
        return 0
    failed = False
    existing = set(EXAMPLES.glob("*.json")) | ({OPENAPI} if OPENAPI.exists() else set())
    for extra in sorted(existing - set(wanted)):
        print(f"unexpected file: {extra.relative_to(ROOT)}")
        failed = True
    for path, text in wanted.items():
        rel = path.relative_to(ROOT)
        if not path.exists():
            print(f"missing {rel}; run with --write")
            failed = True
            continue
        old = json.loads(path.read_text(encoding="utf-8"))
        diff = differences(old, json.loads(text))
        if diff:
            print(f"{rel} changed:")
            print("\n".join(diff[:40]))
            failed = True
    if failed:
        return 1
    print(f"game contract unchanged ({len(wanted)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
