"""Game-session identity and authorization seam.

Phase 5 ships one mechanism, deliberately small and honest:

* Creating a game session returns a random **session token** (``gst_`` + 256 bits). Only its
  SHA-256 hash is stored. Every session call must present it (``Authorization: Bearer``; the
  WebSocket takes ``?token=`` because browsers/engines cannot always set headers there).
* Comparison is constant-time. A wrong or missing token is ``PERMISSION_DENIED``; an unknown
  session is ``SESSION_NOT_FOUND`` (no hint whether a session exists without its token beyond
  that).
* :class:`GameIdentityProvider` is the seam for real user authentication later: it maps a
  request to a *principal* (scoping idempotency keys and owning profiles). Today it always
  returns ``anonymous`` — there are no accounts, and no admin capability exists on the game
  API at all.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Protocol

from app.core.errors import ForbiddenError
from app.services.idempotency import ANONYMOUS

TOKEN_PREFIX = "gst_"  # noqa: S105 - a public prefix, not a secret


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str | None, expected_hash: str) -> None:
    if not token or not token.startswith(TOKEN_PREFIX) or len(token) > 128:
        raise ForbiddenError("a valid game session token is required", code="invalid_session_token")
    if not hmac.compare_digest(hash_token(token), expected_hash):
        raise ForbiddenError("a valid game session token is required", code="invalid_session_token")


def bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()


def new_public_id(prefix: str) -> str:
    """Opaque public id (``gs_``, ``gt_``, ``ck_``, ``gp_`` + 128 random bits, base32)."""
    import base64

    raw = base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=").lower()
    return f"{prefix}{raw}"


class GameIdentityProvider(Protocol):
    def principal(self, authorization: str | None) -> str: ...


class AnonymousIdentityProvider:
    """No accounts yet: every caller is ``anonymous``; session tokens authorize sessions."""

    def principal(self, authorization: str | None) -> str:
        return ANONYMOUS
