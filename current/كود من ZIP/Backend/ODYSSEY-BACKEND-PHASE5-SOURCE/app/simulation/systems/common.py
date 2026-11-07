"""Helpers shared by system update functions."""

from __future__ import annotations

from app.simulation.domain.enums import SubsystemMode
from app.simulation.domain.state import MissionState
from app.simulation.scenarios.schema import ComponentSpec, ScenarioDefinition


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(hi, max(lo, value))


def performance(spec: ComponentSpec, health: float) -> float:
    """Output multiplier of a component: linear from ``performance_floor`` (health 0) to 1."""
    return spec.performance_floor + (1.0 - spec.performance_floor) * clamp(health)


def component_performance(
    scenario: ScenarioDefinition, state: MissionState, component_id: str | None
) -> float:
    """Performance of a component, 0 while under maintenance (taken offline)."""
    if component_id is None:
        return 1.0
    comp = state.components[component_id]
    if comp.maintenance_remaining_ticks > 0:
        return 0.0
    return performance(scenario.component(component_id), comp.health)


def mode_factor(scenario: ScenarioDefinition, state: MissionState, consumer_id: str) -> float:
    spec = scenario.consumer(consumer_id)
    return spec.mode_factors.get(state.power.consumers[consumer_id].mode, 0.0)


def consumer_output(
    scenario: ScenarioDefinition,
    state: MissionState,
    consumer_id: str,
    *,
    cap_mode_at_nominal: bool = False,
) -> float:
    """Effective output fraction of a powered subsystem this tick.

    output = mode_factor (optionally capped at 1) * supply_ratio * component performance
    """
    spec = scenario.consumer(consumer_id)
    mf = mode_factor(scenario, state, consumer_id)
    if cap_mode_at_nominal:
        mf = min(mf, spec.mode_factors.get(SubsystemMode.NOMINAL, 1.0))
    supply = state.power.consumers[consumer_id].supply_ratio
    return mf * supply * component_performance(scenario, state, spec.component)


def alive_crew(state: MissionState) -> int:
    return sum(1 for c in state.crew if c.health > 0)
