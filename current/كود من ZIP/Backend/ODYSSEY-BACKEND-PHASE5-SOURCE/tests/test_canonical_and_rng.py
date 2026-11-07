"""Canonical serialization and the counter-based RNG (foundations of determinism)."""

from __future__ import annotations

import math
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.simulation.canonical import (
    CanonicalizationError,
    canonical_json,
    normalize,
    sha256_hex,
    short_hash,
)
from app.simulation.engine import rng

json_scalars = (
    st.none()
    | st.booleans()
    | st.integers(-(10**12), 10**12)
    | st.text(max_size=8)
    | st.floats(allow_nan=False, allow_infinity=False, width=64)
)
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=6), children, max_size=4)
    ),
    max_leaves=12,
)


class TestCanonicalJson:
    def test_key_order_and_whitespace(self) -> None:
        assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'

    def test_float_rounding_and_negative_zero(self) -> None:
        assert normalize(0.1 + 0.2) == 0.3
        assert canonical_json(-0.0) == "0.0"
        assert canonical_json(-1e-12) == "0.0"

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite_rejected(self, bad: float) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({"x": bad})

    def test_non_string_keys_rejected(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({1: "a"})

    def test_unsupported_type_rejected(self) -> None:
        with pytest.raises(CanonicalizationError):
            canonical_json({1, 2})

    def test_short_hash_format(self) -> None:
        code = short_hash({"a": 1}, length=10)
        assert re.fullmatch(r"[a-z2-7]{10}", code)
        assert code == short_hash({"a": 1}, length=10)

    @given(json_values)
    def test_normalize_is_idempotent(self, value: object) -> None:
        once = normalize(value)
        assert normalize(once) == once

    @given(st.dictionaries(st.text(max_size=5), st.integers(), max_size=6))
    def test_hash_independent_of_insertion_order(self, mapping: dict[str, int]) -> None:
        reversed_mapping = dict(reversed(list(mapping.items())))
        assert sha256_hex(mapping) == sha256_hex(reversed_mapping)


class TestRng:
    @given(
        st.integers(0, 2**63 - 1), st.text(max_size=12), st.integers(0, 10**6), st.integers(0, 100)
    )
    def test_uniform_is_pure_and_in_range(
        self, seed: int, stream: str, tick: int, index: int
    ) -> None:
        a = rng.uniform(seed, stream, tick, index)
        assert 0.0 <= a < 1.0
        assert a == rng.uniform(seed, stream, tick, index)

    def test_streams_ticks_and_seeds_are_independent(self) -> None:
        base = rng.uniform(1, "fault:battery", 10)
        assert base != rng.uniform(2, "fault:battery", 10)
        assert base != rng.uniform(1, "fault:radio", 10)
        assert base != rng.uniform(1, "fault:battery", 11)

    def test_bernoulli_edges(self) -> None:
        assert rng.bernoulli(1, "s", 0, 0.0) is False
        assert rng.bernoulli(1, "s", 0, -1.0) is False
        assert rng.bernoulli(1, "s", 0, 1.0) is True

    def test_distribution_is_roughly_uniform(self) -> None:
        draws = [rng.uniform(7, "dist", t) for t in range(20_000)]
        mean = sum(draws) / len(draws)
        assert abs(mean - 0.5) < 0.01
        hits = sum(rng.bernoulli(7, "p", t, 0.1) for t in range(20_000))
        assert 1800 < hits < 2200

    def test_known_values_are_pinned(self) -> None:
        """Pins the algorithm: changing it would silently change every stored replay."""
        assert f"{rng.uniform(0, 'x', 0):.12f}" == "0.729524843454"
        assert f"{rng.uniform(42, 'event:minor_flare', 100):.12f}" == "0.791376278325"
        assert rng.derive_seed(42, "lens:10:0") == 1474871570990180990

    def test_derive_seed(self) -> None:
        s = rng.derive_seed(42, "lens:10:0")
        assert 0 <= s < 2**63
        assert s == rng.derive_seed(42, "lens:10:0")
        assert s != rng.derive_seed(42, "lens:10:1")
