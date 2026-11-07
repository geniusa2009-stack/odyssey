"""Deterministic replay: initial state + decision ledger + engine → any later state.

Semantics: decisions recorded at tick ``t`` are applied (in sequence order) before the step
``t → t+1``. ``history[t]`` is the *effective* state at tick ``t`` (after that tick's decisions),
which is what analysis (root cause, profile) reads.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from app.simulation.domain.decisions import DecisionInput
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine
from app.simulation.replay.ledger import DecisionRecord


@dataclass(frozen=True, slots=True)
class ReplayDecision:
    decision_id: str
    sequence: int
    tick: int
    decision: DecisionInput
    expected_before_hash: str | None = None
    expected_after_hash: str | None = None

    @classmethod
    def from_record(cls, rec: DecisionRecord) -> ReplayDecision:
        return cls(
            rec.decision_id,
            rec.sequence,
            rec.tick,
            rec.decision(),
            rec.state_before_hash,
            rec.state_after_hash,
        )


@dataclass(frozen=True, slots=True)
class AppliedDecision:
    decision_id: str
    sequence: int
    tick: int
    decision_type: str
    state_before_hash: str
    state_after_hash: str


@dataclass(slots=True)
class ReplayResult:
    state: MissionState
    events: list[MissionEvent] = field(default_factory=list)
    history: list[MissionState] = field(default_factory=list)
    applied: list[AppliedDecision] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


class ReplayDivergenceError(RuntimeError):
    """Replayed state hash differs from the recorded one (non-determinism or tampering)."""


class ReplayOrderError(ValueError):
    pass


def replay(
    engine: SimulationEngine,
    initial_state: MissionState,
    decisions: Sequence[ReplayDecision],
    until_tick: int,
    *,
    record_history: bool = False,
    verify_hashes: bool = False,
    skip_invalid: bool = False,
    options: RunOptions | None = None,
) -> ReplayResult:
    """Replay ``decisions`` from ``initial_state`` up to ``until_tick``.

    ``skip_invalid`` (used for counterfactuals) drops decisions the engine rejects instead of
    raising. ``verify_hashes`` checks every applied decision against its recorded hashes.
    """
    ordered = sorted(decisions, key=lambda d: d.sequence)
    for a, b in pairwise(ordered):
        if b.tick < a.tick:
            raise ReplayOrderError(f"decision {b.decision_id} is earlier than {a.decision_id}")
    if ordered and ordered[-1].tick > until_tick:
        raise ReplayOrderError("decisions exist beyond the replay horizon")

    opts = options or RunOptions()
    state = initial_state.clone()
    result = ReplayResult(state=state)
    idx = 0
    while True:
        while idx < len(ordered) and ordered[idx].tick == state.tick:
            d = ordered[idx]
            idx += 1
            before = state.state_hash()
            if verify_hashes and d.expected_before_hash and before != d.expected_before_hash:
                raise ReplayDivergenceError(f"state before {d.decision_id} diverged")
            try:
                applied = engine.apply_decision(state, d.decision, d.decision_id)
            except DecisionRejectedError as exc:
                if skip_invalid:
                    result.skipped.append((d.decision_id, exc.code))
                    continue
                raise
            state = applied.state
            after = state.state_hash()
            if verify_hashes and d.expected_after_hash and after != d.expected_after_hash:
                raise ReplayDivergenceError(f"state after {d.decision_id} diverged")
            result.events.extend(applied.events)
            result.applied.append(
                AppliedDecision(d.decision_id, d.sequence, d.tick, d.decision.type, before, after)
            )
        if idx < len(ordered) and ordered[idx].tick < state.tick:
            if skip_invalid:
                result.skipped.extend((d.decision_id, "mission_concluded") for d in ordered[idx:])
                idx = len(ordered)
            else:
                raise ReplayOrderError(f"decision {ordered[idx].decision_id} is in the past")
        if record_history:
            result.history.append(state.clone())
        if state.tick >= until_tick or state.status == MissionStatus.CONCLUDED:
            break
        result.events.extend(engine._step_in_place(state, opts))
    if idx < len(ordered):
        if not skip_invalid:
            raise ReplayOrderError("mission concluded before all decisions were applied")
        result.skipped.extend((d.decision_id, "mission_concluded") for d in ordered[idx:])
    result.state = state
    return result
