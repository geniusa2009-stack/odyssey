"""Deterministic serialization and hashing.

Every hash in ODYSSEY (state hashes, ledger record hashes, Mission DNA, decision ids) is
computed from *canonical JSON*:

* keys sorted,
* no insignificant whitespace,
* floats rounded to ``FLOAT_DECIMALS`` places (and ``-0.0`` normalised to ``0.0``),
* NaN / infinity rejected (they have no canonical JSON form).

Rounding makes hashes robust to last-bit differences that are irrelevant to mission state.
This module is pure standard library so it can be used by the simulation core.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

FLOAT_DECIMALS = 9


class CanonicalizationError(ValueError):
    """Raised when a value has no canonical JSON representation."""


def normalize(value: Any) -> Any:
    """Return a JSON-compatible structure with canonical float values."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CanonicalizationError(f"non-finite float {value!r} cannot be canonicalized")
        rounded = round(value, FLOAT_DECIMALS)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"mapping keys must be str, got {type(key).__name__}")
            out[key] = normalize(item)
        return out
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [normalize(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return normalize(model_dump(mode="json"))
    raise CanonicalizationError(f"unsupported type for canonical JSON: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize ``value`` to canonical JSON text."""
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    """SHA-256 of the canonical JSON of ``value`` (hex)."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def short_hash(value: Any, length: int = 16) -> str:
    """Compact, URL-safe, case-insensitive identifier (RFC 4648 base32, lowercase)."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:length]
