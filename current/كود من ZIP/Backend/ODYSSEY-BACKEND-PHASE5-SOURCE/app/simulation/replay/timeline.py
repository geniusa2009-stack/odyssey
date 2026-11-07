"""Timelines and branching (rewind).

A timeline is ``(parent, fork point, own decisions)``. Its *effective ledger* is the parent's
effective ledger truncated at ``fork_sequence`` followed by its own records. Parents are never
modified by forking, so original timelines stay immutable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from app.simulation.replay.ledger import GENESIS_HASH, DecisionRecord


class TimelineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeline_id: str
    parent_timeline_id: str | None = None
    fork_sequence: int | None = None
    fork_tick: int | None = None


class TimelineError(ValueError):
    pass


def effective_ledger(
    timeline: TimelineSpec,
    get_timeline: Callable[[str], TimelineSpec],
    get_own_records: Callable[[str], Sequence[DecisionRecord]],
    *,
    max_depth: int = 64,
) -> list[DecisionRecord]:
    """Resolve the full decision history of ``timeline`` across its ancestors."""
    chain: list[TimelineSpec] = [timeline]
    seen = {timeline.timeline_id}
    while chain[-1].parent_timeline_id is not None:
        if len(chain) > max_depth:
            raise TimelineError("timeline ancestry too deep")
        parent = get_timeline(chain[-1].parent_timeline_id)
        if parent.timeline_id in seen:
            raise TimelineError("timeline ancestry contains a cycle")
        seen.add(parent.timeline_id)
        chain.append(parent)

    records: list[DecisionRecord] = []
    for depth, spec in enumerate(reversed(chain)):
        own = sorted(get_own_records(spec.timeline_id), key=lambda r: r.sequence)
        if depth > 0:
            fork_seq = spec.fork_sequence if spec.fork_sequence is not None else 0
            records = [r for r in records if r.sequence <= fork_seq]
        records.extend(own)
    return records


@dataclass(frozen=True, slots=True)
class ForkPlan:
    """Where a rewind branch starts relative to the parent's effective ledger."""

    fork_sequence: int
    fork_tick: int
    inherited: tuple[DecisionRecord, ...]
    replaced: DecisionRecord
    prev_record_hash: str

    @property
    def next_sequence(self) -> int:
        return self.fork_sequence + 1


def plan_fork(parent_effective: Sequence[DecisionRecord], decision_id: str) -> ForkPlan:
    """Plan a branch that rewinds to just before ``decision_id``."""
    target = next((r for r in parent_effective if r.decision_id == decision_id), None)
    if target is None:
        raise TimelineError(f"decision {decision_id} is not part of this timeline")
    inherited = tuple(r for r in parent_effective if r.sequence < target.sequence)
    prev = inherited[-1].record_hash if inherited else GENESIS_HASH
    return ForkPlan(
        fork_sequence=target.sequence - 1,
        fork_tick=target.tick,
        inherited=inherited,
        replaced=target,
        prev_record_hash=prev,
    )
