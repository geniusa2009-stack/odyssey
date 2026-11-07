"""Domain rule errors raised by the pure game core.

They carry a machine-readable ``reason`` and safe ``details``; the application boundary maps them
onto the frozen public error contract (``app/core/errors.py``):

* ``unavailable`` → ``DECISION_UNAVAILABLE`` (409, recoverable: the world state does not allow it
  now — e.g. ``fault_not_diagnosed``, ``slot_occupied``, ``container_mass_limit_exceeded``)
* ``invalid``     → ``INVALID_REQUEST`` (422: the request itself is wrong — unknown parameter
  value, action not supported by the target)
* ``not_found``   → ``NOT_FOUND`` (404: unknown or not-yet-known semantic id)
* ``complete``    → ``MISSION_COMPLETE`` (409: the mission/timeline has concluded)
"""

from __future__ import annotations

from typing import Any, Literal

RuleKind = Literal["unavailable", "invalid", "not_found", "complete"]


class GameRuleError(Exception):
    def __init__(
        self,
        reason: str,
        message: str | None = None,
        *,
        kind: RuleKind = "unavailable",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message or reason.replace("_", " ")
        self.kind: RuleKind = kind
        self.details = details or {}


def unavailable(reason: str, message: str | None = None, **details: Any) -> GameRuleError:
    return GameRuleError(reason, message, kind="unavailable", details=details)


def invalid(reason: str, message: str | None = None, **details: Any) -> GameRuleError:
    return GameRuleError(reason, message, kind="invalid", details=details)


def not_found(reason: str, message: str | None = None, **details: Any) -> GameRuleError:
    return GameRuleError(reason, message, kind="not_found", details=details)
