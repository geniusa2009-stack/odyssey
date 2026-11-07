"""Containers, inventory and cargo (pure, atomic).

A container holds whole-unit quantities of catalog items. Every mutation validates first and
mutates only when every check passes, so a failed transfer leaves no partial state. Invariants
(tested by property tests): quantities are never negative, transfers conserve mass and units,
unique items exist at most once per timeline, and an installed module is never also counted in a
container.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.game.actions.errors import invalid, not_found, unavailable
from app.game.content.loader import LoadedContent
from app.game.world.state import TimelineGameState

MASS_EPS = 1e-9


def contents_mass(content: LoadedContent, contents: Mapping[str, int]) -> float:
    items = content.index.items
    return sum(items[i].mass_kg * q for i, q in contents.items())


def contents_volume(content: LoadedContent, contents: Mapping[str, int]) -> float:
    items = content.index.items
    return sum((items[i].volume_l or 0.0) * q for i, q in contents.items())


def installed_mass(content: LoadedContent, doc: TimelineGameState, host: str) -> float:
    items = content.index.items
    return sum(items[m.item].mass_kg for m in doc.modules.get(host, {}).values())


def vehicle_payload_mass(content: LoadedContent, doc: TimelineGameState, vehicle: str) -> float:
    """Cargo in the vehicle's containers plus modules installed in payload slots."""
    idx = content.index
    obj = idx.objects[vehicle]
    total = 0.0
    for cid, contents in doc.containers.items():
        if idx.objects[cid].parent == vehicle:
            total += contents_mass(content, contents)
    vc = idx.vehicle_classes.get(obj.vehicle_class or "")
    if vc is not None:
        payload_slots = {s.id for s in vc.slots if s.payload}
        for slot, mod in doc.modules.get(vehicle, {}).items():
            if slot in payload_slots:
                total += idx.items[mod.item].mass_kg
    return total


def total_units(doc: TimelineGameState, item: str) -> int:
    held = sum(c.get(item, 0) for c in doc.containers.values())
    installed = sum(1 for slots in doc.modules.values() for m in slots.values() if m.item == item)
    return held + installed


def require_container(content: LoadedContent, doc: TimelineGameState, cid: str) -> None:
    obj = content.index.objects.get(cid)
    if obj is None or cid not in doc.containers or obj.container is None:
        raise not_found("unknown_container", container=cid)


def check_add(
    content: LoadedContent,
    doc: TimelineGameState,
    cid: str,
    item_id: str,
    qty: int,
    *,
    extra_mass_removed: float = 0.0,
    moving: bool = False,
) -> None:
    """Raise unless ``qty`` units of ``item_id`` fit in container ``cid``.

    ``moving``: the units already exist elsewhere in this timeline (a transfer or uninstall), so
    uniqueness is not re-checked."""
    if qty < 1:
        raise invalid("invalid_quantity", quantity=qty)
    idx = content.index
    item = idx.items.get(item_id)
    if item is None:
        raise not_found("unknown_item", item=item_id)
    require_container(content, doc, cid)
    obj = idx.objects[cid]
    spec = obj.container
    assert spec is not None
    contents = doc.containers[cid]
    if spec.accepts and item.category not in spec.accepts:
        raise unavailable(
            "container_rejects_category", container=cid, item=item_id, category=item.category
        )
    if item.stackable and contents.get(item_id, 0) + qty > item.max_stack:
        raise unavailable("stack_limit_exceeded", item=item_id, max_stack=item.max_stack)
    if item.unique and not moving and total_units(doc, item_id) + qty > 1:
        raise unavailable("unique_item_exists", item=item_id)
    mass = contents_mass(content, contents) + item.mass_kg * qty
    if spec.mass_limit_kg is not None and mass > spec.mass_limit_kg + MASS_EPS:
        raise unavailable(
            "container_mass_limit_exceeded",
            container=cid,
            mass_kg=round(mass, 3),
            limit_kg=spec.mass_limit_kg,
        )
    volume = contents_volume(content, contents) + (item.volume_l or 0.0) * qty
    if spec.volume_limit_l is not None and volume > spec.volume_limit_l + MASS_EPS:
        raise unavailable(
            "container_volume_limit_exceeded",
            container=cid,
            volume_l=round(volume, 3),
            limit_l=spec.volume_limit_l,
        )
    if obj.parent is not None:
        parent = idx.objects[obj.parent]
        vc = idx.vehicle_classes.get(parent.vehicle_class or "")
        if vc is not None:
            payload = vehicle_payload_mass(content, doc, parent.id) - extra_mass_removed
            payload += item.mass_kg * qty
            if payload > vc.cargo_mass_limit_kg + MASS_EPS:
                raise unavailable(
                    "vehicle_mass_limit_exceeded",
                    vehicle=parent.id,
                    mass_kg=round(payload, 3),
                    limit_kg=vc.cargo_mass_limit_kg,
                )


def check_remove(doc: TimelineGameState, cid: str, item_id: str, qty: int) -> None:
    if qty < 1:
        raise invalid("invalid_quantity", quantity=qty)
    have = doc.containers.get(cid, {}).get(item_id, 0)
    if have < qty:
        raise unavailable(
            "insufficient_quantity", container=cid, item=item_id, available=have, requested=qty
        )


def _add(doc: TimelineGameState, cid: str, item_id: str, qty: int) -> None:
    contents = doc.containers[cid]
    contents[item_id] = contents.get(item_id, 0) + qty
    doc.containers[cid] = dict(sorted(contents.items()))


def _remove(doc: TimelineGameState, cid: str, item_id: str, qty: int) -> None:
    contents = doc.containers[cid]
    left = contents[item_id] - qty
    assert left >= 0
    if left == 0:
        del contents[item_id]
    else:
        contents[item_id] = left


def add_items(
    content: LoadedContent, doc: TimelineGameState, cid: str, item_id: str, qty: int
) -> None:
    check_add(content, doc, cid, item_id, qty)
    _add(doc, cid, item_id, qty)


def remove_items(doc: TimelineGameState, cid: str, item_id: str, qty: int) -> None:
    check_remove(doc, cid, item_id, qty)
    _remove(doc, cid, item_id, qty)


def transfer(
    content: LoadedContent, doc: TimelineGameState, src: str, dst: str, item_id: str, qty: int
) -> None:
    """Move whole units between two containers atomically (mass and units are conserved)."""
    require_container(content, doc, src)
    require_container(content, doc, dst)
    if src == dst:
        raise invalid("same_container", container=src)
    check_remove(doc, src, item_id, qty)
    item = content.index.items[item_id]
    # Moving within the same vehicle does not change its payload.
    same_vehicle = (
        content.index.objects[src].parent is not None
        and content.index.objects[src].parent == content.index.objects[dst].parent
    )
    removed = item.mass_kg * qty if same_vehicle else 0.0
    check_add(content, doc, dst, item_id, qty, extra_mass_removed=removed, moving=True)
    _remove(doc, src, item_id, qty)
    _add(doc, dst, item_id, qty)
