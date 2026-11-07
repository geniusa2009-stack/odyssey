"""Property-based and fuzz tests of the game core (reproducible by seed).

Invariants checked after every step: no negative quantities, container limits respected, unit
and mass conservation for transfers (items only appear through content effects and disappear
through declared consumption), unique items at most once, installed modules never also in a
container, unique discoveries/certifications, monotonic capability stages and campaign meta,
and phases never skipped.
"""

from __future__ import annotations

import asyncio
import os
import random
from collections import Counter

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.game.actions.errors import GameRuleError
from app.game.application.memory import InMemoryGame
from app.game.campaign.campaign import new_campaign, start_mission
from app.game.content.loader import LoadedContent, default_content
from app.game.inventory import containers
from app.game.world.state import TimelineGameState

E = "earth.command."
EC_CONTAINERS = [
    E + "hangar.storage",
    E + "hangar.luna01.cargo_hold",
    E + "player_kit",
    E + "engineering.spares_locker",
]
FUZZ_SEEDS = int(os.environ.get("GAME_FUZZ_SEEDS", "12"))
FUZZ_STEPS = int(os.environ.get("GAME_FUZZ_STEPS", "160"))


def _units(doc: TimelineGameState) -> Counter[str]:
    total: Counter[str] = Counter()
    for contents in doc.containers.values():
        total.update(contents)
    for slots in doc.modules.values():
        total.update(m.item for m in slots.values())
    return total


def check_invariants(content: LoadedContent, doc: TimelineGameState) -> None:
    for cid, contents in doc.containers.items():
        spec = content.index.objects[cid].container
        assert spec is not None
        for item, qty in contents.items():
            assert qty > 0, f"non-positive quantity {item} in {cid}"
        mass = containers.contents_mass(content, contents)
        if spec.mass_limit_kg is not None:
            assert mass <= spec.mass_limit_kg + 1e-6, f"{cid} over mass limit"
    units = _units(doc)
    for item, n in units.items():
        if content.index.items[item].unique:
            assert n <= 1, f"unique item {item} duplicated"
    installed = {m.item for slots in doc.modules.values() for m in slots.values()}
    for item in installed:
        if content.index.items[item].unique:
            assert all(item not in c for c in doc.containers.values())
    ids = [d.id for d in doc.discoveries]
    assert len(ids) == len(set(ids)), "duplicate discovery"
    assert len(doc.insights) == len(set(doc.insights))


# ------------------------------------------------------------------ inventory property test
@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    moves=st.lists(
        st.tuples(
            st.sampled_from(EC_CONTAINERS),
            st.sampled_from(EC_CONTAINERS),
            st.sampled_from(
                [
                    "cargo.water_tank",
                    "cargo.food_pack",
                    "spare.habitat_spares_kit",
                    "spare.breaker_module",
                    "tool.diagnostic_scanner",
                    "equipment.science_drill_kit",
                    "module.radiation_shelter_liner",
                ]
            ),
            st.integers(min_value=-2, max_value=9),
        ),
        max_size=40,
    )
)
def test_transfers_conserve_units_and_mass(moves: list[tuple[str, str, str, int]]) -> None:
    content = default_content()
    meta = new_campaign(content)
    doc = start_mission(content, meta, "earth_command.station_readiness")
    doc.objects[E + "hangar.luna01"].access = "inspection_ready"
    units0 = _units(doc)
    mass0 = sum(containers.contents_mass(content, c) for c in doc.containers.values())
    for src, dst, item, qty in moves:
        before = doc.model_copy(deep=True)
        try:
            containers.transfer(content, doc, src, dst, item, qty)
        except GameRuleError:
            assert doc == before, "a rejected transfer changed state"
        check_invariants(content, doc)
        assert _units(doc) == units0
        mass = sum(containers.contents_mass(content, c) for c in doc.containers.values())
        assert abs(mass - mass0) < 1e-6


# ------------------------------------------------------------------ action-sequence fuzzer
def _random_command(
    rng: random.Random, g: InMemoryGame
) -> tuple[str, str | None, dict[str, object]]:
    content = g.content
    world = content.index.worlds[g.doc.world_id]
    roll = rng.random()
    if roll < 0.18:
        return "world.zone_entered", rng.choice(world.locations).id, {}
    if roll < 0.55:
        obj = rng.choice(world.objects)
        if obj.interactions and rng.random() < 0.9:
            inter = rng.choice(obj.interactions)
            params: dict[str, object] = {k: rng.choice(v.enum) for k, v in inter.params.items()}
            if rng.random() < 0.05:
                params["bogus"] = "x"
            return inter.action, obj.id, params
        return rng.choice(["system.inspect", "repair.perform"]), obj.id, {}
    conts = [o.id for o in world.objects if o.container is not None]
    items = [i.id for i in content.content.catalog.items]
    if roll < 0.75:
        return (
            rng.choice(["cargo.transfer", "inventory.move"]),
            rng.choice(conts),
            {"item": rng.choice(items), "quantity": rng.randint(0, 5), "from": rng.choice(conts)},
        )
    hosts = [o.id for o in world.objects if o.vehicle_class or o.infrastructure_type]
    if roll < 0.83 and hosts:
        return (
            "module.install",
            rng.choice(hosts),
            {
                "slot": rng.choice(["radiation_protection", "external_payload", "shielding", "x"]),
                "item": rng.choice(items),
                "from": rng.choice(conts),
            },
        )
    if roll < 0.87 and hosts:
        return (
            "module.remove",
            rng.choice(hosts),
            {"slot": rng.choice(["radiation_protection", "shielding"]), "to": rng.choice(conts)},
        )
    if roll < 0.93:
        return (
            "mission.clock_set",
            None,
            {"mode": rng.choice(["PAUSED", "REALTIME", "ACCELERATED"])},
        )
    if roll < 0.97:
        gate = content.index.missions[g.doc.mission_id].completion.gate
        return "mission.authorize", gate.target if gate else None, {}
    return "npc.context_request", rng.choice(["maya", "omar", "sofia", "jay", "hal"]), {}


async def play_earth_command(g: InMemoryGame) -> None:
    await g.act("world.zone_entered", E + "engineering")
    await g.wait(30)
    await g.act("system.inspect", E + "engineering.power_bus_b")
    await g.act("repair.perform", E + "engineering.power_bus_b")
    await g.act("mission.clock_set", mode="ACCELERATED")
    for _ in range(4):
        await g.wait(5)
    await g.act("world.zone_entered", E + "hangar")
    for sub in ("power", "life_support", "comms", "radiation_protection"):
        await g.act("system.inspect", f"{E}hangar.luna01.{sub}")
    await g.act(
        "module.install",
        E + "hangar.luna01",
        slot="radiation_protection",
        item="module.radiation_shelter_liner",
        **{"from": E + "hangar.storage"},
    )
    for item, qty in (("cargo.water_tank", 2), ("spare.habitat_spares_kit", 1)):
        await g.act(
            "cargo.transfer",
            E + "hangar.luna01.cargo_hold",
            item=item,
            quantity=qty,
            **{"from": E + "hangar.storage"},
        )
    while g.sim.metric("rover.battery_kwh") < 45:
        await g.wait(5)
    await g.act("mission.authorize", E + "hangar.luna01")
    assert g.doc.mission_id == "luna_01.the_last_light"


async def _fuzz(seed: int, *, from_luna: bool = False) -> None:
    rng = random.Random(seed)
    g = InMemoryGame(default_content(), seed=seed)
    content = g.content
    if from_luna:
        await play_earth_command(g)
    prev_caps: dict[str, str] = {}
    prev_version = g.version
    phase_order = {p.id: p.order for p in content.content.campaign.phases}
    for step in range(FUZZ_STEPS):
        if g.doc.status != "active" and g.meta.active_mission is None:
            mission = g.doc.mission_id
            if g.meta.missions[mission].status in {"failed", "completed"}:
                g.start(mission)  # replay boundary
            continue
        if rng.random() < 0.15:
            await g.wait(rng.choice([1, 5, 30, 120, 600]))
        else:
            action, target, params = _random_command(rng, g)
            obj = content.index.objects.get(target or "")
            if (
                obj is not None
                and rng.random() < 0.7
                and g.doc.locations.get(obj.location) == "open"
            ):
                await g.act("world.zone_entered", obj.location)
            meta_before = g.meta.model_copy(deep=True)
            doc_before = g.doc.model_copy(deep=True)
            try:
                await g.act(action, target, **params)
            except GameRuleError:
                assert g.meta == meta_before, f"seed={seed} step={step}: rejection changed meta"
                # a rejected action may still have applied the clock catch-up of its turn? No:
                # rejections abort the whole turn.
                assert g.doc == doc_before, f"seed={seed} step={step}: rejection changed doc"
        check_invariants(content, g.doc)
        assert g.version >= prev_version
        prev_version = g.version
        for cap, stage in prev_caps.items():
            ladder = content.index.capabilities[cap].stages
            assert ladder.index(g.meta.capabilities[cap]) >= ladder.index(stage), seed
        prev_caps = dict(g.meta.capabilities)
        assert len(g.meta.certifications) == len(set(g.meta.certifications))
        assert len(g.meta.discoveries) == len(set(g.meta.discoveries))
        completed = [p for p, s in g.meta.phases.items() if s == "completed"]
        for p in completed:
            earlier = [q for q, o in phase_order.items() if o < phase_order[p]]
            assert all(g.meta.phases[q] == "completed" for q in earlier), f"seed={seed} skip"


@pytest.mark.parametrize("seed", range(FUZZ_SEEDS))
def test_fuzz_action_sequences(seed: int) -> None:
    asyncio.run(_fuzz(seed))


@pytest.mark.parametrize("seed", range(max(1, FUZZ_SEEDS // 2)))
def test_fuzz_after_mission_transition(seed: int) -> None:
    asyncio.run(_fuzz(1000 + seed, from_luna=True))
