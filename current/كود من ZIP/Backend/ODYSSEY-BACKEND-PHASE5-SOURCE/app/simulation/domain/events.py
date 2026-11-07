"""Events emitted by the simulation engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.domain.enums import AlertSeverity, EventKind


class MissionEvent(BaseModel):
    """Something that happened during tick ``tick`` (the interval [tick, tick+1)).

    Deterministic id: ``{tick}:{seq}:{key}`` for step events, ``{decision_id}/{tick}:{seq}:{key}``
    for events emitted while applying a decision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    tick: int
    seq: int = Field(description="Order of emission within the tick")
    kind: EventKind
    key: str = Field(description="Scenario event id, alert id, phase id, etc.")
    severity: AlertSeverity | None = None
    message_key: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
