"""Application error taxonomy → structured HTTP errors (never stack traces).

Every error response uses one envelope (``docs/API_CONTRACT.md#errors``)::

    {"error": {"code": "STALE_STATE", "reason": "stale_state", "message": "...",
               "details": {...}, "request_id": "...", "recoverable": true,
               "state_version": 7}}

* ``code`` — one of :data:`PUBLIC_CODES`: a deliberately small, **frozen** list. The HTTP status
  is fixed per code, so a client can branch on either.
* ``reason`` — the specific machine-readable cause (e.g. ``science_busy``, ``session_not_found``).
  Reasons may be added over time; clients should treat unknown reasons as their ``code``.
* ``recoverable`` — true when the client can recover without changing its request semantics
  (refresh state and retry, wait and retry). False when the request itself must change.
* ``state_version`` — the authoritative timeline state version, when the error relates to state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PublicCode:
    status: int
    recoverable: bool
    description: str


PUBLIC_CODES: dict[str, PublicCode] = {
    "VALIDATION_ERROR": PublicCode(422, False, "The request does not match the schema"),
    "INVALID_REQUEST": PublicCode(422, False, "The request is well-formed but not acceptable"),
    "INVALID_DECISION": PublicCode(
        422, False, "The decision does not exist in this scenario or its parameters are invalid"
    ),
    "DECISION_UNAVAILABLE": PublicCode(
        409, True, "The decision exists but cannot be taken in the current state"
    ),
    "STALE_STATE": PublicCode(
        409, True, "The request was based on an older state version; refresh and retry"
    ),
    "MISSION_COMPLETE": PublicCode(409, False, "The mission (timeline) has concluded"),
    "IDEMPOTENCY_KEY_REUSED": PublicCode(
        422, False, "The idempotency key was already used for a different request"
    ),
    "SESSION_NOT_FOUND": PublicCode(404, False, "No such mission session"),
    "INVALID_TIMELINE": PublicCode(
        404, False, "No such timeline, or the decision is not part of it"
    ),
    "NOT_FOUND": PublicCode(404, False, "No such resource"),
    "METHOD_NOT_ALLOWED": PublicCode(405, False, "HTTP method not allowed on this path"),
    "PERMISSION_DENIED": PublicCode(403, False, "The caller may not perform this action"),
    "PAYLOAD_TOO_LARGE": PublicCode(413, False, "The request body is too large"),
    "RATE_LIMITED": PublicCode(429, True, "Too many requests; wait and retry"),
    "SIMULATION_ERROR": PublicCode(
        500, False, "Stored mission data failed an integrity check (replay or hash mismatch)"
    ),
    "AI_UNAVAILABLE": PublicCode(
        503,
        True,
        "Reserved: ORION has no usable provider (currently ORION degrades to its "
        "grounded mock instead of failing)",
    ),
    "NASA_PROVIDER_UNAVAILABLE": PublicCode(
        503,
        True,
        "Reserved: NASA data unavailable (currently the provider falls back to "
        "bundled fixtures instead of failing)",
    ),
    "INTERNAL_ERROR": PublicCode(500, False, "Unexpected server error"),
}

# Engine/decision reasons that mean "this decision does not exist / is malformed for this
# scenario" (INVALID_DECISION) rather than "not possible right now" (DECISION_UNAVAILABLE).
INVALID_DECISION_REASONS = frozenset(
    {
        "unknown_subsystem",
        "mode_not_supported",
        "setpoint_out_of_range",
        "ration_out_of_range",
        "unknown_component",
        "unsupported_decision",
        "unknown_option",
        "option_type_mismatch",
        "bad_parameters",
    }
)
_REASON_CODES: dict[str, str] = {
    "session_not_found": "SESSION_NOT_FOUND",
    "timeline_not_found": "INVALID_TIMELINE",
    "decision_not_in_timeline": "INVALID_TIMELINE",
    "stale_sequence": "STALE_STATE",
    "stale_state": "STALE_STATE",
    "concurrent_modification": "STALE_STATE",
    "write_conflict": "STALE_STATE",
    "mission_concluded": "MISSION_COMPLETE",
    "idempotency_key_reused": "IDEMPOTENCY_KEY_REUSED",
    "role_forbidden": "PERMISSION_DENIED",
    "omniscient_disabled": "PERMISSION_DENIED",
}


class AppError(Exception):
    """Base application error. ``code`` here is the specific *reason*."""

    status_code = 400
    code = "bad_request"
    public_code = "INVALID_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        state_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}
        self.state_version = state_version
        self.public_code = _REASON_CODES.get(self.code, type(self).public_code)
        self.status_code = PUBLIC_CODES[self.public_code].status

    @property
    def recoverable(self) -> bool:
        return PUBLIC_CODES[self.public_code].recoverable


class NotFoundError(AppError):
    code = "not_found"
    public_code = "NOT_FOUND"


class ForbiddenError(AppError):
    code = "forbidden"
    public_code = "PERMISSION_DENIED"


class ConflictError(AppError):
    code = "conflict"
    public_code = "STALE_STATE"


class DecisionRejected(AppError):
    """A decision the engine refused. Classified by reason into INVALID_DECISION,
    DECISION_UNAVAILABLE or MISSION_COMPLETE."""

    code = "decision_rejected"
    public_code = "DECISION_UNAVAILABLE"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        state_version: int | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details, state_version=state_version)
        if self.code in INVALID_DECISION_REASONS:
            self.public_code = "INVALID_DECISION"
            self.status_code = PUBLIC_CODES[self.public_code].status


class InvalidRequestError(AppError):
    code = "invalid_request"
    public_code = "INVALID_REQUEST"


class RateLimitedError(AppError):
    code = "rate_limited"
    public_code = "RATE_LIMITED"


class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    public_code = "PAYLOAD_TOO_LARGE"


class IntegrityFailure(AppError):
    code = "integrity_failure"
    public_code = "SIMULATION_ERROR"


def error_body(
    code: str,
    message: str,
    request_id: str | None,
    details: dict[str, Any] | None = None,
    *,
    reason: str | None = None,
    state_version: int | None = None,
) -> dict[str, Any]:
    """Build the error envelope. ``code`` must be a key of :data:`PUBLIC_CODES`."""
    spec = PUBLIC_CODES[code]
    return {
        "error": {
            "code": code,
            "reason": reason or code.lower(),
            "message": message,
            "details": details or {},
            "request_id": request_id,
            "recoverable": spec.recoverable,
            "state_version": state_version,
        }
    }


def app_error_body(exc: AppError, request_id: str | None) -> dict[str, Any]:
    """The envelope for an :class:`AppError`: its public code, its specific reason."""
    return error_body(
        exc.public_code,
        exc.message,
        request_id,
        exc.details,
        reason=exc.code,
        state_version=exc.state_version,
    )
