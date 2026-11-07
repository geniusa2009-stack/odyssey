"""Mission role permission abstraction (multiplayer-ready).

Role → action rules are a product decision (docs/USER_DECISIONS_REQUIRED.md, "Multiplayer role
permissions"), so the default policy allows everything. A future policy only needs to implement
``allows``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from app.simulation.domain.enums import CrewRole

MissionRole = CrewRole  # mission participant roles mirror crew roles


class MissionAction(StrEnum):
    VIEW = "view"
    DECIDE = "decide"
    ADVANCE = "advance"
    REWIND = "rewind"
    FUTURE_LENS = "future_lens"
    ORION = "orion"


class PermissionPolicy(Protocol):
    def allows(
        self, role: MissionRole | None, action: MissionAction, decision_type: str | None = None
    ) -> bool: ...


class AllowAllPolicy:
    def allows(
        self, role: MissionRole | None, action: MissionAction, decision_type: str | None = None
    ) -> bool:
        return True


class RoleTablePolicy:
    """Example data-driven policy: {role: {action: [decision types] | ["*"]}}."""

    def __init__(self, table: dict[MissionRole, dict[MissionAction, list[str]]]) -> None:
        self._table = table

    def allows(
        self, role: MissionRole | None, action: MissionAction, decision_type: str | None = None
    ) -> bool:
        if role is None:
            return False
        allowed = self._table.get(role, {}).get(action)
        if allowed is None:
            return False
        return "*" in allowed or decision_type is None or decision_type in allowed
