"""Idempotency keys for mutation endpoints.

Clients send ``Idempotency-Key: <8–128 chars of [A-Za-z0-9_.:-]>`` on create-session, decision,
advance and timeline-branch requests. The successful response is stored **in the same
transaction** as the mutation, so after a network failure a retry either finds the committed
response (and gets it back unchanged, with ``Idempotent-Replayed: true``) or finds nothing
because the mutation never committed. Reusing a key for a *different* request is rejected with
``IDEMPOTENCY_KEY_REUSED``. Failed requests are not stored. Keys are scoped by principal (the
auth seam; "anonymous" until authentication exists), endpoint and session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, InvalidRequestError
from app.db import models as m
from app.simulation.canonical import sha256_hex

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:\-]{8,128}$")
ANONYMOUS = "anonymous"


@dataclass(frozen=True, slots=True)
class IdempotencyContext:
    key: str
    request_hash: str
    principal: str = ANONYMOUS


def make_context(
    key: str | None, *, route: str, session_id: str | None, body: Any, principal: str = ANONYMOUS
) -> IdempotencyContext | None:
    if key is None:
        return None
    if not KEY_PATTERN.match(key):
        raise InvalidRequestError(
            "Idempotency-Key must be 8-128 characters of [A-Za-z0-9_.:-]",
            code="bad_idempotency_key",
        )
    fingerprint = sha256_hex({"route": route, "session": session_id, "body": body})
    return IdempotencyContext(key=key, request_hash=fingerprint, principal=principal)


class IdempotencyKeyReused(AppError):
    code = "idempotency_key_reused"
    public_code = "IDEMPOTENCY_KEY_REUSED"


async def find(
    db: AsyncSession, ctx: IdempotencyContext, scope: str, session_key: str
) -> m.IdempotencyRecord | None:
    row = (
        await db.execute(
            select(m.IdempotencyRecord).where(
                m.IdempotencyRecord.principal == ctx.principal,
                m.IdempotencyRecord.scope == scope,
                m.IdempotencyRecord.session_key == session_key,
                m.IdempotencyRecord.idempotency_key == ctx.key,
            )
        )
    ).scalar_one_or_none()
    if row is not None and row.request_hash != ctx.request_hash:
        raise IdempotencyKeyReused(
            "this Idempotency-Key was already used for a different request",
            details={"scope": scope},
        )
    return row


def record(
    db: AsyncSession,
    ctx: IdempotencyContext,
    scope: str,
    session_key: str,
    status_code: int,
    response: dict[str, Any],
) -> None:
    db.add(
        m.IdempotencyRecord(
            principal=ctx.principal,
            scope=scope,
            session_key=session_key,
            idempotency_key=ctx.key,
            request_hash=ctx.request_hash,
            status_code=status_code,
            response=response,
        )
    )
