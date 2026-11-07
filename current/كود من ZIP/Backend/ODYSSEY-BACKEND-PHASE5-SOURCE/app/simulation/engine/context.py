"""Per-tick working context passed to system update functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.simulation.domain.enums import AlertSeverity, EventKind
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine import rng
from app.simulation.engine.metrics import MetricRegistry
from app.simulation.scenarios.schema import ScenarioDefinition


@dataclass(frozen=True, slots=True)
class RunOptions:
    """Knobs that change *how* the engine runs without changing the scenario.

    ``rng_seed`` overrides the state's seed for random draws only (Future Lens samples).
    ``suppressed_events`` disables scenario events (Future Lens 'known_only' policy).
    """

    rng_seed: int | None = None
    suppressed_events: frozenset[str] = frozenset()


@dataclass(slots=True)
class TickContext:
    scenario: ScenarioDefinition
    metrics: MetricRegistry
    state: MissionState
    options: RunOptions
    tick: int
    events: list[MissionEvent] = field(default_factory=list)
    id_prefix: str = ""

    @property
    def dt_hours(self) -> float:
        return self.scenario.time.tick_hours

    @property
    def seed(self) -> int:
        return self.options.rng_seed if self.options.rng_seed is not None else self.state.seed

    def chance(self, stream: str, probability: float, index: int = 0) -> bool:
        return rng.bernoulli(self.seed, stream, self.tick, probability, index)

    def emit(
        self,
        kind: EventKind,
        key: str,
        *,
        severity: AlertSeverity | None = None,
        message_key: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> MissionEvent:
        seq = len(self.events)
        event = MissionEvent(
            id=f"{self.id_prefix}{self.tick}:{seq}:{key}",
            tick=self.tick,
            seq=seq,
            kind=kind,
            key=key,
            severity=severity,
            message_key=message_key,
            data=data or {},
        )
        self.events.append(event)
        return event
