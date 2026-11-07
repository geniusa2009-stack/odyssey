"""Simulation port: how the game core reaches the authoritative mission simulation.

* :class:`ServiceSimPort` (app/game/application/service.py) records through the existing
  ``MissionService`` (ledger, snapshots, outcomes) inside the caller's database transaction.
* :class:`InMemorySimPort` drives the engine directly with the same decision-id derivation as the
  ledger; used by domain and fuzz tests (fast, no database).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from app.simulation.domain.decisions import DecisionInput, decision_payload
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.replay.ledger import make_decision_id

StopWhen = Callable[[MissionState], bool]


class SimPort(Protocol):
    @property
    def engine(self) -> SimulationEngine: ...

    async def state(self) -> MissionState: ...

    async def apply(
        self, decision: DecisionInput, metadata: Mapping[str, Any]
    ) -> tuple[MissionState, str]:
        """Apply and record one decision; returns the new state and the ledger decision id."""
        ...

    async def advance(self, ticks: int, stop_when: StopWhen | None) -> MissionState:
        """Advance up to ``ticks`` ticks, stopping after the first tick where ``stop_when``
        holds (or when the mission concludes)."""
        ...


class InMemorySimPort:
    def __init__(self, engine: SimulationEngine, seed: int, timeline_id: str = "memory") -> None:
        self._engine = engine
        self._state = engine.initial_state(seed)
        self._sequence = 0
        self.timeline_id = timeline_id
        self.decisions: list[tuple[str, int, dict[str, Any]]] = []

    @property
    def engine(self) -> SimulationEngine:
        return self._engine

    async def state(self) -> MissionState:
        return self._state

    async def apply(
        self, decision: DecisionInput, metadata: Mapping[str, Any]
    ) -> tuple[MissionState, str]:
        self._sequence += 1
        inputs = decision_payload(decision)
        did = make_decision_id(self.timeline_id, self._sequence, self._state.tick, inputs)
        self._state = self._engine.apply_decision(self._state, decision, did).state
        self.decisions.append((did, self._state.tick, inputs))
        return self._state, did

    def checkpoint(self) -> tuple[MissionState, int, int]:
        return self._state, self._sequence, len(self.decisions)

    def restore(self, saved: tuple[MissionState, int, int]) -> None:
        self._state, self._sequence, n = saved
        del self.decisions[n:]

    async def advance(self, ticks: int, stop_when: StopWhen | None) -> MissionState:
        result = self._engine.advance(self._state, ticks, stop_when=stop_when)
        self._state = result.state
        return self._state
