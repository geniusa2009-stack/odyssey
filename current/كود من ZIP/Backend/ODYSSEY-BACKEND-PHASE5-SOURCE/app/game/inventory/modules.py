"""Hardware modules: installation compatibility and atomic install/remove.

Compatibility interfaces (deliberately simple, not CAD): slot category, mount type, power bus,
data bus, environment rating, mission rating, capability qualification and the host vehicle's
payload mass budget. "A good component in an incompatible system is not a valid installation":
every failed interface is reported (``details.incompatible``) with the first as the reason.
"""

from __future__ import annotations

from typing import Any

from app.game.actions.errors import GameRuleError, invalid, not_found, unavailable
from app.game.content.loader import LoadedContent
from app.game.content.schema import Item, Slot, WorldObject
from app.game.inventory.containers import (
    MASS_EPS,
    _add,
    _remove,
    check_add,
    check_remove,
    require_container,
    vehicle_payload_mass,
)
from app.game.world.conditions import capability_stage_met
from app.game.world.state import CampaignMeta, InstalledModule, TimelineGameState

_INACCESSIBLE = {"locked", "restricted"}


def _host(content: LoadedContent, doc: TimelineGameState, host_id: str) -> WorldObject:
    obj = content.index.objects.get(host_id)
    if obj is None or host_id not in doc.objects or not doc.objects[host_id].known:
        raise not_found("unknown_target", target=host_id)
    if obj.vehicle_class is None and obj.infrastructure_type is None:
        raise invalid("target_cannot_host_modules", target=host_id)
    if doc.objects[host_id].access in _INACCESSIBLE:
        raise unavailable("host_not_accessible", target=host_id, access=doc.objects[host_id].access)
    return obj


def _slot(content: LoadedContent, host: WorldObject, slot_id: str) -> Slot | None:
    vc = content.index.vehicle_classes.get(host.vehicle_class or "")
    if vc is None:
        return None
    return next((s for s in vc.slots if s.id == slot_id), None)


def compatibility_problems(
    content: LoadedContent,
    meta: CampaignMeta,
    doc: TimelineGameState,
    host: WorldObject,
    slot_id: str,
    item: Item,
) -> list[dict[str, Any]]:
    """Every interface the module fails for this host slot (empty = compatible)."""
    spec = item.module
    if spec is None:
        return [{"reason": "not_a_module", "item": item.id}]
    problems: list[dict[str, Any]] = []
    idx = content.index
    if host.vehicle_class is not None:
        vc = idx.vehicle_classes[host.vehicle_class]
        slot = _slot(content, host, slot_id)
        if slot is None:
            return [{"reason": "unknown_slot", "slot": slot_id}]
        if spec.category not in slot.accepts:
            problems.append(
                {
                    "reason": "module_category_incompatible",
                    "category": spec.category,
                    "accepts": list(slot.accepts),
                }
            )
        if spec.mount != slot.mount:
            problems.append(
                {"reason": "mount_incompatible", "module": spec.mount, "slot": slot.mount}
            )
        if spec.power_bus is not None and spec.power_bus != slot.power_bus:
            problems.append(
                {
                    "reason": "power_bus_incompatible",
                    "module": spec.power_bus,
                    "slot": slot.power_bus,
                }
            )
        if spec.data_bus is not None and spec.data_bus != slot.data_bus:
            problems.append(
                {"reason": "data_bus_incompatible", "module": spec.data_bus, "slot": slot.data_bus}
            )
        missing_env = sorted(set(vc.environment_rating) - set(spec.environment_rating))
        if missing_env:
            problems.append({"reason": "environment_rating_insufficient", "missing": missing_env})
        if spec.mission_rating and not set(spec.mission_rating) & set(vc.mission_rating):
            problems.append(
                {
                    "reason": "mission_rating_mismatch",
                    "module": list(spec.mission_rating),
                    "vehicle": list(vc.mission_rating),
                }
            )
        if slot.payload:
            payload = vehicle_payload_mass(content, doc, host.id) + item.mass_kg
            if payload > vc.cargo_mass_limit_kg + MASS_EPS:
                problems.append(
                    {
                        "reason": "vehicle_mass_limit_exceeded",
                        "mass_kg": round(payload, 3),
                        "limit_kg": vc.cargo_mass_limit_kg,
                    }
                )
    else:
        it = idx.infrastructure_types[host.infrastructure_type or ""]
        if spec.category not in it.requires_modules:
            problems.append(
                {
                    "reason": "module_category_incompatible",
                    "category": spec.category,
                    "accepts": list(it.requires_modules),
                }
            )
    if spec.qualification is not None and not capability_stage_met(
        content, meta, spec.qualification.capability, spec.qualification.stage
    ):
        problems.append(
            {
                "reason": "module_qualification_missing",
                "capability": spec.qualification.capability,
                "stage": spec.qualification.stage,
            }
        )
    return problems


def install(
    content: LoadedContent,
    meta: CampaignMeta,
    doc: TimelineGameState,
    host_id: str,
    slot_id: str,
    item_id: str,
    from_container: str,
) -> None:
    host = _host(content, doc, host_id)
    if host.vehicle_class is not None and _slot(content, host, slot_id) is None:
        raise invalid("unknown_slot", slot=slot_id)
    if slot_id in doc.modules.get(host_id, {}):
        raise unavailable("slot_occupied", slot=slot_id)
    require_container(content, doc, from_container)
    item = content.index.items.get(item_id)
    if item is None:
        raise not_found("unknown_item", item=item_id)
    check_remove(doc, from_container, item_id, 1)
    problems = compatibility_problems(content, meta, doc, host, slot_id, item)
    if problems:
        raise GameRuleError(
            problems[0]["reason"],
            "the module is not compatible with this slot",
            kind="unavailable",
            details={"incompatible": problems},
        )
    _remove(doc, from_container, item_id, 1)
    doc.modules.setdefault(host_id, {})[slot_id] = InstalledModule(item=item_id, state="installed")


def remove(
    content: LoadedContent,
    doc: TimelineGameState,
    host_id: str,
    slot_id: str,
    to_container: str,
) -> str:
    _host(content, doc, host_id)
    installed = doc.modules.get(host_id, {}).get(slot_id)
    if installed is None:
        raise unavailable("slot_empty", slot=slot_id)
    require_container(content, doc, to_container)
    host = content.index.objects[host_id]
    slot = _slot(content, host, slot_id)
    in_same_vehicle = content.index.objects[to_container].parent == host_id
    released = (
        content.index.items[installed.item].mass_kg
        if slot is not None and slot.payload and in_same_vehicle
        else 0.0
    )
    check_add(
        content, doc, to_container, installed.item, 1, moving=True, extra_mass_removed=released
    )
    del doc.modules[host_id][slot_id]
    if not doc.modules[host_id]:
        del doc.modules[host_id]
    _add(doc, to_container, installed.item, 1)
    return installed.item
