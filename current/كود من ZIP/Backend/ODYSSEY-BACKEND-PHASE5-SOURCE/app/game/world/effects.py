"""Applying content effects to the timeline document (pure, deterministic)."""

from __future__ import annotations

from app.game.actions.errors import unavailable
from app.game.content.loader import LoadedContent
from app.game.content.schema import Effects
from app.game.inventory.containers import add_items
from app.game.world.state import CampaignMeta, CrewState, DiscoveryRecord, TimelineGameState


def unlock_insight(doc: TimelineGameState, meta: CampaignMeta, insight: str) -> bool:
    """Knowledge is unlocked for the timeline and recorded in the campaign (it carries no
    gameplay power, so keeping it after a rewind cannot be exploited)."""
    new = insight not in doc.insights
    if new:
        doc.insights.append(insight)
    if insight not in meta.insights:
        meta.insights.append(insight)
    return new


def record_discovery(
    content: LoadedContent,
    doc: TimelineGameState,
    meta: CampaignMeta,
    discovery_id: str,
    *,
    tick: int,
    source: str = "player",
) -> bool:
    """Idempotent: a discovery is recorded at most once per timeline (and committed to the
    campaign at most once, at mission completion)."""
    if discovery_id in doc.discovery_ids():
        return False
    disc = content.index.discoveries[discovery_id]
    doc.discoveries.append(
        DiscoveryRecord(
            id=discovery_id,
            mission_id=doc.mission_id,
            location=disc.location,
            tick=tick,
            source=source,
        )
    )
    for ev in disc.capability_evidence:
        if ev not in doc.evidence:
            doc.evidence.append(ev)
    for insight in disc.insights:
        unlock_insight(doc, meta, insight)
    return True


def apply_effects(
    content: LoadedContent,
    doc: TimelineGameState,
    meta: CampaignMeta,
    effects: Effects,
    *,
    tick: int,
    default_container: str | None,
) -> None:
    for flag in effects.set_flags:
        doc.set_flag(flag)
    for flag in effects.clear_flags:
        doc.clear_flag(flag)
    for upd in effects.object_updates:
        obj = doc.objects.get(upd.object)
        if obj is None:
            continue  # object of another world (validated content never does this)
        setattr(obj, upd.field, upd.value)
    for loc, access in effects.location_access.items():
        if loc in doc.locations:
            doc.locations[loc] = access
    if effects.add_items:
        target = effects.add_items_to or default_container
        if target is None or target not in doc.containers:
            raise unavailable("no_container_for_items")
        for iq in effects.add_items:
            add_items(content, doc, target, iq.item, iq.quantity)
    for ev in effects.evidence:
        if ev not in doc.evidence:
            doc.evidence.append(ev)
    for d in effects.discoveries:
        record_discovery(content, doc, meta, d, tick=tick)
    for insight in effects.insights:
        unlock_insight(doc, meta, insight)
    for ci in effects.crew_intents:
        doc.crew.setdefault(ci.crew, CrewState()).intent = ci.intent
