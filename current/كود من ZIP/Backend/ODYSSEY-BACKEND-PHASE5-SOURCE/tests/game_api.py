"""Test client for ``odyssey.game.v1`` over the production HTTP API (no shortcuts).

Drives the mounted game sub-app through FastAPI's TestClient. The server clock is a
:class:`~app.game.runtime.clock.FakeClock` injected through ``create_app(game_runtime=...)`` so
open-world time is deterministic; everything else is the production path (router → service →
MissionService ledger → database).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.game.application.identity import AnonymousIdentityProvider
from app.game.application.runtime import GameRuntime
from app.game.content.loader import default_content
from app.game.realtime.bus import GameBus, InMemoryGameBus
from app.game.runtime.clock import FakeClock
from app.main import create_app

GAME = "/api/game/v1"
E = "earth.command."
LUNA01 = E + "hangar.luna01"
HANGAR_STORAGE = E + "hangar.storage"


def game_runtime(clock: FakeClock | None = None, bus: GameBus | None = None) -> GameRuntime:
    return GameRuntime(
        content=default_content(),
        bus=bus or InMemoryGameBus(),
        clock=clock or FakeClock(),
        identity=AnonymousIdentityProvider(),
    )


@contextmanager
def game_client(
    settings: Settings, runtime: GameRuntime | None = None, *, inject: bool = True
) -> Iterator[tuple[TestClient, GameRuntime]]:
    """``inject=False`` lets the application build its production runtime (system clock, Redis
    bus when ``settings.redis_url`` is set)."""
    rt = (runtime or game_runtime()) if inject else None
    app = create_app(settings, game_runtime=rt)
    with TestClient(app) as client:
        mounted = next(r for r in app.routes if getattr(r, "path", "") == GAME)
        yield client, mounted.app.state.game_runtime  # type: ignore[attr-defined]


_ids = itertools.count(1)


@dataclass
class GamePlayer:
    """One game session driven through the HTTP API."""

    client: TestClient
    runtime: GameRuntime
    session_id: str = ""
    token: str = ""
    state_version: int = 0
    last_seq: int = 0
    timeline_id: str = ""
    responses: list[dict[str, Any]] = field(default_factory=list)
    prefix: str = field(default_factory=lambda: f"c{next(_ids)}")
    _n: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    @property
    def clock(self) -> FakeClock:
        assert isinstance(self.runtime.clock, FakeClock)
        return self.runtime.clock

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def create(self, display_name: str = "Commander") -> dict[str, Any]:
        r = self.client.post(f"{GAME}/sessions", json={"display_name": display_name})
        assert r.status_code == 201, r.text
        body: dict[str, Any] = r.json()
        self.token = body["session_token"]
        snap = body["bootstrap"]["snapshot"]
        self.session_id = snap["session"]["id"]
        self._track_snapshot(snap)
        return body

    def _track_snapshot(self, snap: dict[str, Any]) -> None:
        self.state_version = snap["state_version"]
        self.last_seq = snap["session"]["last_seq"]
        self.timeline_id = snap["timeline"]["id"]

    def url(self, path: str) -> str:
        return f"{GAME}/sessions/{self.session_id}{path}"

    def get(self, path: str, **params: Any) -> Any:
        r = self.client.get(self.url(path), params=params, headers=self.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def post(self, path: str, body: dict[str, Any], expect: int = 200) -> Any:
        r = self.client.post(self.url(path), json=body, headers=self.headers)
        assert r.status_code == expect, r.text
        return r.json()

    def snapshot(self) -> dict[str, Any]:
        snap: dict[str, Any] = self.get("/snapshot")
        self._track_snapshot(snap)
        return snap

    def command_body(self, action: str, target: str | None = None, **params: Any) -> dict[str, Any]:
        n = next(self._n)
        body: dict[str, Any] = {
            "command_id": f"{self.prefix}-cmd-{n}",
            "session_id": self.session_id,
            "expected_state_version": self.state_version,
            "idempotency_key": f"{self.prefix}-idem-{n:06d}",
            "action": action,
            "params": params,
        }
        if target is not None:
            body["target"] = target
        return body

    def send(self, body: dict[str, Any]) -> Any:
        return self.client.post(self.url("/commands"), json=body, headers=self.headers)

    def act(self, action: str, target: str | None = None, **params: Any) -> dict[str, Any]:
        r = self.send(self.command_body(action, target, **params))
        assert r.status_code == 200, r.text
        out: dict[str, Any] = r.json()
        self.responses.append(out)
        self.state_version = out["state_version"]
        self.last_seq = out["last_seq"]
        self.timeline_id = out["timeline_id"]
        return out

    def sync(self) -> dict[str, Any]:
        out: dict[str, Any] = self.post("/sync", {})
        self.state_version = out["state_version"]
        self.last_seq = out["last_seq"]
        self.timeline_id = out["timeline_id"]
        return out

    def wait(self, seconds: float) -> dict[str, Any]:
        self.clock.advance(seconds)
        return self.sync()


# ------------------------------------------------------------------ Earth Command script
def to_incident(g: GamePlayer) -> None:
    g.act("world.zone_entered", E + "engineering")
    g.wait(30)


def resolve_incident(g: GamePlayer) -> None:
    g.act("system.inspect", E + "engineering.power_bus_b")
    g.act("world.zone_entered", E + "training")
    g.act("system.set_mode", E + "training.simulator", mode="off")
    g.act("world.zone_entered", E + "engineering")
    g.act("repair.perform", E + "engineering.power_bus_b")
    g.act("mission.clock_set", mode="ACCELERATED")
    for _ in range(4):
        g.wait(5)


def prepare_spacecraft(g: GamePlayer) -> None:
    g.act("world.zone_entered", E + "hangar")
    for sub in ("power", "life_support", "comms", "radiation_protection"):
        g.act("system.inspect", f"{LUNA01}.{sub}")
    g.act("system.inspect", LUNA01 + ".cargo_hold")
    g.act(
        "module.install",
        LUNA01,
        slot="radiation_protection",
        item="module.radiation_shelter_liner",
        **{"from": HANGAR_STORAGE},
    )
    g.act(
        "cargo.transfer",
        LUNA01 + ".cargo_hold",
        item="cargo.water_tank",
        quantity=2,
        **{"from": HANGAR_STORAGE},
    )
    g.act(
        "cargo.transfer",
        LUNA01 + ".cargo_hold",
        item="spare.habitat_spares_kit",
        quantity=1,
        **{"from": HANGAR_STORAGE},
    )


def charge_spacecraft(g: GamePlayer, kwh: float = 45.0) -> None:
    for _ in range(200):
        snap = g.snapshot()
        obj = next(o for o in snap["world"]["objects"] if o["id"] == LUNA01)
        if (obj.get("charge_kwh") or 0.0) >= kwh:
            return
        g.wait(5)
    raise AssertionError("spacecraft did not charge")
