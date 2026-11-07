"""Seed-reproducible fuzzing of odyssey.game.v1 through the production HTTP API (section 52).

Long randomized valid and invalid sequences: repeated interactions, rapid inventory transfers,
stale-state commands, duplicate idempotency keys, rewinds after progression, disconnect/restore,
multiple timelines, mission-transition boundaries, capability/phase unlock attempts and module
operations. After every step the authoritative snapshot must satisfy the invariants below; any
failure message carries the seed and step so it can be replayed exactly
(``GAME_API_FUZZ_SEEDS=…`` / ``GAME_API_FUZZ_STEPS=…`` widen the run).
"""

from __future__ import annotations

import os
import random
from collections import Counter
from typing import Any

import pytest

from app.game.content.loader import LoadedContent, default_content
from tests.conftest import make_settings
from tests.game_api import (
    LUNA01,
    E,
    GamePlayer,
    charge_spacecraft,
    game_client,
    prepare_spacecraft,
    resolve_incident,
)

SEEDS = int(os.environ.get("GAME_API_FUZZ_SEEDS", "4"))
STEPS = int(os.environ.get("GAME_API_FUZZ_STEPS", "70"))
OK_CODES = {200, 404, 409, 422}


def _units(content: LoadedContent, snap: dict[str, Any]) -> Counter[str]:
    total: Counter[str] = Counter()
    for c in snap["world"]["containers"]:
        for i in c["items"]:
            total[i["item"]] += i["quantity"]
    for o in snap["world"]["objects"]:
        for m in o["modules"]:
            total[m["item"]] += 1
    return total


def _mass(content: LoadedContent, units: Counter[str]) -> float:
    return sum(content.index.items[i].mass_kg * n for i, n in units.items())


def check_snapshot(content: LoadedContent, snap: dict[str, Any], where: str) -> None:
    for c in snap["world"]["containers"]:
        for i in c["items"]:
            assert i["quantity"] > 0, f"{where}: non-positive {i} in {c['id']}"
        if c["mass_limit_kg"] is not None:
            assert c["mass_kg"] <= c["mass_limit_kg"] + 1e-6, f"{where}: {c['id']} over limit"
    units = _units(content, snap)
    for item, n in units.items():
        if content.index.items[item].unique:
            assert n <= 1, f"{where}: unique {item} duplicated"
    ids = [d["id"] for d in snap["discoveries"]]
    assert len(ids) == len(set(ids)), f"{where}: duplicate discovery"
    campaign = snap["campaign"]
    for key in ("certifications", "discoveries", "insights"):
        assert len(campaign[key]) == len(set(campaign[key])), f"{where}: duplicate {key}"
    phases = sorted(campaign["phases"], key=lambda p: p["order"])
    seen_open = False
    for p in reversed(phases):  # a later phase active/completed ⇒ every earlier one completed
        if p["status"] in {"active", "completed"}:
            seen_open = True
        elif seen_open:
            assert p["status"] == "completed", f"{where}: phase {p['id']} skipped"
    mars = next(p for p in phases if p["id"] == "MARS_01")
    assert mars["status"] == "locked", f"{where}: Mars unlocked"
    known = content.index.objects
    for o in snap["world"]["objects"]:
        assert o["id"] in known, f"{where}: unknown world id {o['id']}"


def _random_body(
    rng: random.Random, g: GamePlayer, content: LoadedContent, snap: dict[str, Any]
) -> dict[str, Any]:
    world = content.index.worlds[snap["world"]["id"]]
    roll = rng.random()
    if roll < 0.2:
        return g.command_body("world.zone_entered", rng.choice(world.locations).id)
    if roll < 0.55:
        obj = rng.choice(world.objects)
        if obj.interactions and rng.random() < 0.9:
            inter = rng.choice(obj.interactions)
            params = {k: rng.choice(v.enum) for k, v in inter.params.items()}
            return g.command_body(inter.action, obj.id, **params)
        return g.command_body(rng.choice(["system.inspect", "repair.perform"]), obj.id)
    conts = [o.id for o in world.objects if o.container is not None]
    items = [i.id for i in content.content.catalog.items]
    if roll < 0.8:
        return g.command_body(
            rng.choice(["cargo.transfer", "inventory.move"]),
            rng.choice(conts),
            item=rng.choice(items),
            quantity=rng.randint(1, 4),
            **{"from": rng.choice(conts)},
        )
    hosts = [o.id for o in world.objects if o.vehicle_class or o.infrastructure_type]
    if roll < 0.88 and hosts:
        if rng.random() < 0.6:
            return g.command_body(
                "module.install",
                rng.choice(hosts),
                slot=rng.choice(["radiation_protection", "external_payload", "shielding"]),
                item=rng.choice(items),
                **{"from": rng.choice(conts)},
            )
        return g.command_body(
            "module.remove",
            rng.choice(hosts),
            slot=rng.choice(["radiation_protection", "shielding"]),
            to=rng.choice(conts),
        )
    if roll < 0.95:
        return g.command_body(
            "mission.clock_set", mode=rng.choice(["PAUSED", "REALTIME", "ACCELERATED"])
        )
    return g.command_body("mission.authorize", LUNA01)


def _step(
    rng: random.Random,
    g: GamePlayer,
    content: LoadedContent,
    sent: list[dict[str, Any]],
    where: str,
) -> None:
    snap = g.snapshot()
    before_version, before_seq = snap["state_version"], snap["session"]["last_seq"]
    before_units = _units(content, snap)
    roll = rng.random()
    if roll < 0.6:
        body = _random_body(rng, g, content, snap)
        r = g.send(body)
        assert r.status_code in OK_CODES, f"{where}: {r.status_code} {r.text}"
        if r.status_code == 200:
            sent.append(body)
            out = r.json()
            assert out["state_version"] in {before_version, before_version + 1}, where
            assert [e["seq"] for e in out["events"]] == list(
                range(before_seq + 1, out["last_seq"] + 1)
            ), f"{where}: event seq not contiguous"
            after = g.snapshot()
            if body["action"] in {
                "cargo.transfer",
                "inventory.move",
                "module.install",
                "module.remove",
            }:
                assert _units(content, after) == before_units, f"{where}: units not conserved"
                assert (
                    abs(_mass(content, _units(content, after)) - _mass(content, before_units))
                    < 1e-6
                )
        else:
            assert g.snapshot()["state_version"] == before_version, f"{where}: rejected but mutated"
    elif roll < 0.68 and sent:  # retry an earlier command verbatim (duplicate idempotency key)
        body = rng.choice(sent)
        r = g.send(body)
        assert r.status_code in {200, 422}, f"{where}: {r.text}"
        if r.status_code == 200:
            assert r.headers["Idempotent-Replayed"] == "true", where
        assert g.snapshot()["state_version"] == before_version, f"{where}: replay mutated"
    elif roll < 0.74:  # stale state
        body = g.command_body("world.zone_entered", E + "engineering")
        body["expected_state_version"] = max(1, before_version - 1)
        if body["expected_state_version"] != before_version:
            r = g.send(body)
            assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_STATE", where
    elif roll < 0.82:  # time passes (server clock)
        g.wait(rng.choice([1, 5, 15, 60]))
    elif roll < 0.88:  # disconnect / reconnect through the single restore path
        restored = g.post("/restore", {"last_seq": rng.randint(0, before_seq)})
        assert restored["snapshot"] == g.snapshot(), f"{where}: restore != snapshot"
    elif roll < 0.94:  # rewind to a random point of the active timeline
        points = g.get("/rewind-points")["points"]
        if points and snap["mission"]["status"] == "active":
            p = rng.choice(points)
            meta_before = snap["campaign"]
            r = g.client.post(
                g.url("/rewind"),
                json={"command_id": p["command_id"], "expected_state_version": before_version},
                headers=g.headers,
            )
            assert r.status_code in {200, 409}, f"{where}: {r.text}"
            if r.status_code == 200:
                after = g.snapshot()
                assert after["campaign"] == meta_before, f"{where}: rewind changed campaign"
                g.send(g.command_body("mission.clock_set", mode="REALTIME"))
                g.snapshot()
    else:  # unlock attempts that must fail
        phase = rng.choice(["LUNAR_SURVIVAL", "MARS_01", "PATH_TO_MARS", "LUNA_01"])
        r = g.client.post(
            g.url(f"/phases/{phase}/start"),
            json={"expected_state_version": before_version},
            headers=g.headers,
        )
        assert r.status_code in {409, 422}, f"{where}: {phase} {r.text}"
    after = g.snapshot()
    assert after["state_version"] >= before_version, f"{where}: version went backwards"
    assert after["session"]["last_seq"] >= before_seq, f"{where}: seq went backwards"
    check_snapshot(content, after, where)


@pytest.mark.parametrize("seed", range(SEEDS))
def test_api_fuzz(seed: int, tmp_path: Any) -> None:
    content = default_content()
    rng = random.Random(seed)
    url = f"sqlite+aiosqlite:///{tmp_path / f'fuzz-{seed}.db'}"
    with game_client(make_settings(url)) as pair:
        g = GamePlayer(*pair)
        g.create()
        sent: list[dict[str, Any]] = []
        transition_at = rng.randint(STEPS // 3, STEPS // 2) if seed % 2 == 0 else None
        for step in range(STEPS):
            where = f"seed={seed} step={step}"
            if step == transition_at and g.snapshot()["mission"]["id"].startswith("earth"):
                # drive across the mission-transition boundary, then keep fuzzing in LUNA-01
                try:
                    g.act("world.zone_entered", E + "engineering")  # starts the clock once
                    g.act("mission.clock_set", mode="REALTIME")
                    g.wait(30)
                    resolve_incident(g)
                    prepare_spacecraft(g)
                    charge_spacecraft(g)
                    g.act("world.zone_entered", E + "hangar")
                    g.act("mission.authorize", LUNA01)
                except AssertionError:
                    pass  # random play may have made the scripted path impossible; fine
                check_snapshot(content, g.snapshot(), where)
                continue
            _step(rng, g, content, sent, where)
        page = g.get("/events", after_seq=0, limit=500)
        if not page["resync_required"]:
            seqs = [e["seq"] for e in page["events"]]
            assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), f"seed={seed}: seq gap"
