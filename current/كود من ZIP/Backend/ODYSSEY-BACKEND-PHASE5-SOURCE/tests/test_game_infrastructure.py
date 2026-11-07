"""Persistent infrastructure (section 24), mission failure and replay through the API."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.game.application.memory import InMemoryGame
from app.game.campaign.campaign import complete_mission, initial_document
from app.game.content.loader import default_content
from app.game.realtime.derive import campaign_events
from app.game.world.conditions import Ctx
from app.game.world.state import InstalledModule
from app.game.world.views import _infrastructure_state, campaign_view
from tests.conftest import make_settings
from tests.game_api import (
    LUNA01,
    E,
    GamePlayer,
    charge_spacecraft,
    game_client,
    prepare_spacecraft,
    resolve_incident,
    to_incident,
)
from tests.test_game_properties import play_earth_command

SHELTER = "luna.asteria.shelter.module"


def _stub_ctx(requires: list[str], installed: list[str]) -> Any:
    """Just enough of Ctx for the infrastructure state rules."""
    items = {f"m.{c}": SimpleNamespace(module=SimpleNamespace(category=c)) for c in installed}
    it = SimpleNamespace(requires_modules=requires, depends_on_power=True)
    content = SimpleNamespace(index=SimpleNamespace(infrastructure_types={"t": it}, items=items))
    doc = SimpleNamespace(modules={"obj": {c: InstalledModule(item=f"m.{c}") for c in installed}})
    return SimpleNamespace(content=content, doc=doc)


def test_infrastructure_state_rules() -> None:
    obj: Any = SimpleNamespace(id="obj", infrastructure_type="t")
    two = ["power", "isru"]
    assert _infrastructure_state(_stub_ctx(two, []), obj, "operational", "powered") == "planned"
    assert (
        _infrastructure_state(_stub_ctx(two, ["power"]), obj, "operational", "powered")
        == "under_construction"
    )
    full = _stub_ctx(two, ["power", "isru"])
    assert _infrastructure_state(full, obj, "operational", "powered") == "operational"
    assert _infrastructure_state(full, obj, "operational", "partial") == "degraded"
    assert _infrastructure_state(full, obj, "degraded", "powered") == "degraded"
    assert _infrastructure_state(full, obj, "damaged", "powered") == "damaged"
    assert _infrastructure_state(full, obj, "operational", "unpowered") == "offline"
    assert _infrastructure_state(full, obj, "maintenance", "powered") == "offline"
    plain: Any = SimpleNamespace(id="obj", infrastructure_type=None)
    assert _infrastructure_state(full, plain, "operational", None) is None


def test_completion_commits_infrastructure_records_once() -> None:
    async def scenario() -> InMemoryGame:
        g = InMemoryGame(default_content(), seed=5)
        await play_earth_command(g)
        return g

    g = asyncio.run(scenario())
    content = g.content
    assert g.doc.mission_id == "luna_01.the_last_light"
    # the player removes the shelter liner before the mission ends: it is left 'planned'
    del g.doc.modules[SHELTER]["shielding"]
    before = campaign_view(content, g.meta)
    meta, doc = g.meta.model_copy(deep=True), g.doc.model_copy(deep=True)
    complete_mission(Ctx(content, doc, meta, g.sim), tier="success")
    records = meta.infrastructure
    world = content.index.worlds["luna_01"]
    expected = {o.id for o in world.objects if o.infrastructure_type}
    assert set(records) == expected
    assert records[SHELTER].state == "planned"
    assert records[SHELTER].modules == {}
    assert all(
        r.mission_id == "luna_01.the_last_light" and r.attempt == 1 for r in records.values()
    )
    after = campaign_view(content, meta)
    changed = [e for e in campaign_events(before, after) if e.type == "infrastructure.changed"]
    assert {e.payload["object"] for e in changed} == expected
    assert all(e.payload["persistent"] is True for e in changed)
    # a later mission that inherits infrastructure starts from the recorded state
    mission = content.index.missions["luna_01.the_last_light"]
    inherited = initial_document(
        content, meta, mission.model_copy(update={"inherit_infrastructure": True})
    )
    assert SHELTER not in inherited.modules
    authored = initial_document(content, meta, mission)
    assert authored.modules[SHELTER]["shielding"].item == "module.radiation_shelter_liner"


def test_failed_mission_commits_nothing_and_is_replayable(sqlite_url: str) -> None:
    with game_client(make_settings(sqlite_url)) as pair:
        g = GamePlayer(*pair)
        g.create()
        to_incident(g)
        resolve_incident(g)
        prepare_spacecraft(g)
        charge_spacecraft(g)
        g.act("world.zone_entered", E + "hangar")
        g.act("mission.authorize", LUNA01)
        campaign_before = g.snapshot()["campaign"]
        g.act("world.zone_entered", "luna.asteria.habitat")
        g.act("mission.clock_set", mode="ACCELERATED")
        for _ in range(60):  # neglect the outpost: let the server clock run it down
            snap = g.snapshot()
            if snap["mission"]["status"] != "active":
                break
            if snap["clock"]["mode"] != "ACCELERATED":
                g.act("mission.clock_set", mode="ACCELERATED")
            g.wait(20)
        snap = g.snapshot()
        assert snap["mission"]["status"] == "failed"
        campaign = snap["campaign"]
        assert campaign["certifications"] == campaign_before["certifications"]
        assert campaign["capabilities"] == campaign_before["capabilities"]
        assert campaign["infrastructure"] == []
        luna = next(m for m in campaign["missions"] if m["id"] == "luna_01.the_last_light")
        assert luna["status"] == "failed" and luna["attempts"] == 1
        # the commands on a finished timeline are refused
        r = g.send(g.command_body("world.zone_entered", "luna.asteria.habitat"))
        assert r.status_code == 409 and r.json()["error"]["code"] == "MISSION_COMPLETE"
        # replay: a fresh attempt on a fresh simulation, campaign history intact
        replay = g.post(
            "/missions/luna_01.the_last_light/start",
            {"expected_state_version": g.state_version},
        )
        assert replay["timeline"]["attempt"] == 2
        assert replay["mission"]["status"] == "active"
        assert replay["clock"]["sim_tick"] == 0
        luna = next(
            m for m in replay["campaign"]["missions"] if m["id"] == "luna_01.the_last_light"
        )
        assert luna["status"] == "active" and luna["attempts"] == 2
