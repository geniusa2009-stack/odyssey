"""Structured, read-only mission context for ORION.

ORION never sees engine objects, database sessions or mutable state — only this frozen,
fact-indexed snapshot. Every fact has a stable id that answers must cite.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.science.evidence import ScienceEvidence
from app.simulation.analysis.root_cause import RootCauseTrace
from app.simulation.domain.state import MissionState
from app.simulation.engine.metrics import MetricRegistry
from app.simulation.replay.ledger import DecisionRecord

CONTEXT_METRICS = (
    "time.tick",
    "time.hours",
    "power.battery_soc",
    "power.generation_kw",
    "power.demand_kw",
    "power.unmet_kw",
    "env.solar_availability",
    "env.sink_temp_c",
    "env.radiation_dose_rate_msv_h",
    "thermal.habitat_temp_c",
    "life_support.oxygen_days",
    "life_support.co2_ppm",
    "life_support.water_days",
    "life_support.water_recovery_efficiency",
    "food.food_days",
    "crew.min_health",
    "crew.max_dose_msv",
    "science.points",
    "comms.link_up",
    "comms.data_downlinked_mb",
    "risk.mission",
)

FactSource = Literal["state", "ledger", "alert", "trace", "evidence", "scenario", "read_model"]


class ContextFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    value: float | str | bool | None
    unit: str | None = None
    source: FactSource
    url: str | None = None


class MissionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    tick: int
    phase: str
    status: str
    facts: tuple[ContextFact, ...]
    trace: RootCauseTrace | None = None
    severities: dict[str, float] = Field(default_factory=dict)

    def fact(self, fact_id: str) -> ContextFact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def fact_ids(self) -> set[str]:
        return {f.id for f in self.facts}

    def as_prompt_data(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario_id,
            "tick": self.tick,
            "phase": self.phase,
            "status": self.status,
            "facts": [f.model_dump(mode="json", exclude_none=True) for f in self.facts],
        }


def _round(value: float) -> float:
    return float(f"{value:.4g}")


def build_context(
    state: MissionState,
    metrics: MetricRegistry,
    *,
    decisions: Sequence[DecisionRecord] = (),
    trace: RootCauseTrace | None = None,
    evidence: Sequence[ScienceEvidence] = (),
    max_decisions: int = 10,
    extra_facts: Sequence[ContextFact] = (),
) -> MissionContext:
    facts: list[ContextFact] = [
        ContextFact(id="mission.phase", label="Mission phase", value=state.phase, source="state"),
        ContextFact(
            id="mission.status", label="Mission status", value=state.status.value, source="state"
        ),
    ]
    if state.outcome is not None:
        facts.append(
            ContextFact(
                id="mission.outcome",
                label="Mission outcome",
                value=state.outcome.code,
                source="state",
            )
        )
    severities: dict[str, float] = {}
    for name in CONTEXT_METRICS:
        spec = metrics.spec(name)
        facts.append(
            ContextFact(
                id=f"metric:{name}",
                label=spec.label,
                value=_round(metrics.value(name, state)),
                unit=spec.unit,
                source="state",
            )
        )
        severities[name] = metrics.severity(name, state)
    for alert in sorted(state.alerts.values(), key=lambda a: (a.raised_tick, a.id)):
        facts.append(
            ContextFact(
                id=f"alert:{alert.id}",
                label=f"Active {alert.severity.value} alert on {alert.metric}",
                value=alert.raised_tick,
                unit="tick raised",
                source="alert",
            )
        )
    for rec in list(decisions)[-max_decisions:]:
        facts.append(
            ContextFact(
                id=f"decision:{rec.decision_id}",
                label=f"Decision {rec.decision_type} {rec.inputs}",
                value=rec.tick,
                unit="tick",
                source="ledger",
            )
        )
    if trace is not None:
        for node in trace.nodes:
            facts.append(
                ContextFact(
                    id=f"trace:{node.id}",
                    label=f"{node.kind}: {node.label}",
                    value=_round(node.value) if node.value is not None else node.tick,
                    unit=node.unit if node.value is not None else "tick",
                    source="trace",
                )
            )
        for edge in trace.edges:
            facts.append(
                ContextFact(
                    id=f"trace:{edge.source}->{edge.target}",
                    label=edge.mechanism,
                    value=None,
                    source="trace",
                )
            )
    for ev in evidence:
        facts.append(
            ContextFact(
                id=f"evidence:{ev.id}",
                label=ev.claim,
                value=ev.value,
                unit=ev.unit,
                source="evidence",
                url=str(ev.source_url) if ev.source_url else None,
            )
        )
    # facts from the frontend-safe read models (radiation budget, objective statuses)
    facts.extend(extra_facts)
    return MissionContext(
        scenario_id=state.scenario_id,
        tick=state.tick,
        phase=state.phase,
        status=state.status.value,
        facts=tuple(facts),
        trace=trace,
        severities=severities,
    )
