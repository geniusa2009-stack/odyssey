"""Counter-based deterministic random numbers.

Instead of a stateful generator, every random draw is a pure function of
``(seed, stream, tick, index)``. Consequences:

* Replays and forks reproduce draws exactly, no matter how many other draws happened before
  (adding a new random event to a scenario does not perturb existing ones).
* Future Lens can evaluate alternative futures with *different* seeds without touching the real
  mission's draws.
* Only integer hashing is involved, so results are identical across platforms and Python
  versions (``random.Random`` only guarantees ``random()`` sequence stability).
"""

from __future__ import annotations

import hashlib

_SCALE = float(1 << 64)


def uniform(seed: int, stream: str, tick: int, index: int = 0) -> float:
    """Deterministic float in [0, 1)."""
    material = f"{seed}|{stream}|{tick}|{index}".encode()
    digest = hashlib.blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big") / _SCALE


def bernoulli(seed: int, stream: str, tick: int, probability: float, index: int = 0) -> bool:
    if probability <= 0.0:
        return False
    if probability >= 1.0:
        return True
    return uniform(seed, stream, tick, index) < probability


def derive_seed(seed: int, label: str) -> int:
    """Derive an independent 63-bit seed (e.g. for Future Lens samples)."""
    digest = hashlib.blake2b(f"{seed}|derive|{label}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1
