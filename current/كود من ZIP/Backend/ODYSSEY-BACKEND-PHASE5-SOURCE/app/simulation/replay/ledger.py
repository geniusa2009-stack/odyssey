"""Immutable, hash-chained decision ledger.

Every applied decision becomes a :class:`DecisionRecord`. Records are frozen and chained:
``record_hash = H(prev_record_hash, decision fields, state hashes)``. Any edit to a stored record
(or reordering) breaks :func:`verify_chain`. Together with the initial seed and scenario, the
ledger is sufficient to reconstruct any mission state by replay.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.canonical import sha256_hex, short_hash
from app.simulation.domain.decisions import DecisionInput, decision_payload, parse_decision
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import DecisionResult, SimulationEngine

GENESIS_HASH = "0" * 64


class DecisionRecord(BaseModel):
    """One immutable ledger entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    session_id: str
    timeline_id: str
    sequence: int = Field(ge=1)
    tick: int = Field(ge=0)
    decision_type: str
    inputs: dict[str, Any]
    phase: str
    affected_systems: tuple[str, ...]
    state_before_hash: str
    state_after_hash: str
    prev_record_hash: str
    record_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None

    def decision(self) -> DecisionInput:
        return parse_decision(self.inputs)


def make_decision_id(timeline_id: str, sequence: int, tick: int, inputs: Mapping[str, Any]) -> str:
    """Deterministic decision id (unique per timeline + sequence)."""
    return "dec_" + short_hash(
        {"timeline": timeline_id, "seq": sequence, "tick": tick, "inputs": dict(inputs)}, length=20
    )


def compute_record_hash(
    *,
    prev_record_hash: str,
    decision_id: str,
    timeline_id: str,
    sequence: int,
    tick: int,
    decision_type: str,
    inputs: Mapping[str, Any],
    state_before_hash: str,
    state_after_hash: str,
) -> str:
    return sha256_hex(
        {
            "prev": prev_record_hash,
            "id": decision_id,
            "timeline": timeline_id,
            "seq": sequence,
            "tick": tick,
            "type": decision_type,
            "inputs": dict(inputs),
            "before": state_before_hash,
            "after": state_after_hash,
        }
    )


def record_decision(
    engine: SimulationEngine,
    state: MissionState,
    decision: DecisionInput,
    *,
    session_id: str,
    timeline_id: str,
    sequence: int,
    prev_record_hash: str,
    metadata: Mapping[str, Any] | None = None,
    include_states: bool = True,
) -> tuple[DecisionRecord, DecisionResult]:
    """Apply ``decision`` to ``state`` (without mutating it) and build its ledger record."""
    inputs = decision_payload(decision)
    decision_id = make_decision_id(timeline_id, sequence, state.tick, inputs)
    result = engine.apply_decision(state, decision, decision_id)
    before_hash = state.state_hash()
    after_hash = result.state.state_hash()
    record = DecisionRecord(
        decision_id=decision_id,
        session_id=session_id,
        timeline_id=timeline_id,
        sequence=sequence,
        tick=state.tick,
        decision_type=decision.type,
        inputs=inputs,
        phase=state.phase,
        affected_systems=result.affected_systems,
        state_before_hash=before_hash,
        state_after_hash=after_hash,
        prev_record_hash=prev_record_hash,
        record_hash=compute_record_hash(
            prev_record_hash=prev_record_hash,
            decision_id=decision_id,
            timeline_id=timeline_id,
            sequence=sequence,
            tick=state.tick,
            decision_type=decision.type,
            inputs=inputs,
            state_before_hash=before_hash,
            state_after_hash=after_hash,
        ),
        metadata=dict(metadata or {}),
        state_before=state.model_dump(mode="json") if include_states else None,
        state_after=result.state.model_dump(mode="json") if include_states else None,
    )
    return record, result


class LedgerIntegrityError(ValueError):
    pass


def verify_chain(records: Sequence[DecisionRecord], *, start_hash: str = GENESIS_HASH) -> None:
    """Verify sequence ordering, tick monotonicity and the hash chain."""
    prev = start_hash
    last_seq = 0
    last_tick = -1
    for rec in records:
        if rec.sequence <= last_seq:
            raise LedgerIntegrityError(f"sequence not increasing at {rec.decision_id}")
        if rec.tick < last_tick:
            raise LedgerIntegrityError(f"tick went backwards at {rec.decision_id}")
        if rec.prev_record_hash != prev:
            raise LedgerIntegrityError(f"broken chain at {rec.decision_id}")
        expected = compute_record_hash(
            prev_record_hash=rec.prev_record_hash,
            decision_id=rec.decision_id,
            timeline_id=rec.timeline_id,
            sequence=rec.sequence,
            tick=rec.tick,
            decision_type=rec.decision_type,
            inputs=rec.inputs,
            state_before_hash=rec.state_before_hash,
            state_after_hash=rec.state_after_hash,
        )
        if expected != rec.record_hash:
            raise LedgerIntegrityError(f"record hash mismatch at {rec.decision_id}")
        prev, last_seq, last_tick = rec.record_hash, rec.sequence, rec.tick
