"""Frontend-safe view of engine mission events.

Engine events carry the scenario's own description of how an event was produced (trigger
parameters, effect lists, random draws). Clients only learn *what happened*: the event's id,
tick, kind, key, severity, message key and the remaining data (e.g. which science windows a
milestone opened).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.read_models.common import View, clean_data
from app.simulation.domain.events import MissionEvent


class EventView(View):
    id: str
    tick: int
    kind: str
    key: str
    severity: str | None = None
    message_key: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def event_view(e: MissionEvent) -> EventView:
    raw = e.model_dump(mode="json")["data"]
    data = clean_data(raw)
    effects = raw.get("effects")
    if isinstance(effects, list):
        opened = [
            str(x["opportunity"])
            for x in effects
            if isinstance(x, dict) and x.get("type") == "open_opportunity"
        ]
        if opened:
            # what a science-window event opened (an observable fact once it happened)
            data["opened_opportunities"] = opened
    return EventView(
        id=e.id,
        tick=e.tick,
        kind=e.kind.value,
        key=e.key,
        severity=e.severity.value if e.severity is not None else None,
        message_key=e.message_key,
        data=data,
    )
