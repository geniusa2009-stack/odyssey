"""Read-only view of the mission simulation used by game rules.

Game conditions may look at simulation metrics, fired events, active alerts and the outcome.
This is backend-internal: nothing here is sent to clients directly (client views are built by
the read models, which apply hidden-information rules).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.read_models.mission import outcome_tier
from app.simulation.domain.enums import MissionStatus
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine


@dataclass(frozen=True, slots=True)
class SimView:
    engine: SimulationEngine
    state: MissionState

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def concluded(self) -> bool:
        return self.state.status == MissionStatus.CONCLUDED

    @property
    def scenario_id(self) -> str:
        return self.engine.scenario.id

    def has_metric(self, name: str) -> bool:
        return self.engine.metrics.has(name)

    def metric(self, name: str) -> float:
        return self.engine.metrics.value(name, self.state)

    def event_fired(self, event_id: str) -> bool:
        return self.state.event_fire_counts.get(event_id, 0) > 0

    def alert_active(self, alert_id: str) -> bool:
        return alert_id in self.state.alerts

    def has_event(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self.engine.scenario.events)

    def has_alert(self, alert_id: str) -> bool:
        return any(a.id == alert_id for a in self.engine.scenario.alerts)

    def outcome_tier(self) -> str | None:
        o = self.state.outcome
        if o is None:
            return None
        return outcome_tier(self.engine, o.code, o.rule_id)
