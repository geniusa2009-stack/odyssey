"""System read models: power, habitat, life support, thermal, communications, science, rover.

Per system: its consumers (mode, demand, allocation, supply ratio), the health and maintenance
condition of the components that gate it, the active alerts on its metrics and a status band.
Only quantities the engine models are exposed; nothing is estimated.
"""

from __future__ import annotations

from app.read_models.common import (
    StatusBand,
    View,
    WarningState,
    active_alert_levels,
    band,
    rnd,
    worst_warning,
)
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

# Display order of subsystem modes (lowest power first).
MODE_ORDER: tuple[str, ...] = ("off", "eco", "nominal", "boost")

SYSTEMS: tuple[tuple[str, str], ...] = (
    ("power", "Power"),
    ("habitat", "Habitat"),
    ("life_support", "Life support"),
    ("thermal", "Thermal control"),
    ("communications", "Communications"),
    ("science", "Science"),
    ("rover", "Rover"),
)
_SYSTEM_METRICS: dict[str, tuple[str, ...]] = {
    "power": ("power.battery_soc", "power.unmet_kw", "power.generation_ratio", "power.dust_factor"),
    "habitat": (),
    "life_support": (
        "life_support.oxygen_days",
        "life_support.co2_ppm",
        "life_support.water_days",
        "life_support.water_recovery_efficiency",
    ),
    "thermal": ("thermal.habitat_temp_c",),
    "communications": ("comms.link_up",),
    "science": (),
    "rover": ("rover.lost",),
}


class ConsumerView(View):
    id: str
    label: str
    priority: int
    mode: str
    available_modes: list[str]
    demand_kw: float
    allocated_kw: float
    supply_ratio: float


class ComponentStatus(View):
    id: str
    health: float
    condition: StatusBand
    in_maintenance: bool
    maintenance_remaining_ticks: int
    fault_count: int


class SystemStatus(View):
    id: str
    label: str
    state: StatusBand
    warning_state: WarningState
    load_kw: float
    allocated_kw: float
    supply_ratio: float
    consumers: list[ConsumerView]
    components: list[ComponentStatus]


class SystemOverview(View):
    systems: list[SystemStatus]


def _component(engine: SimulationEngine, state: MissionState, component_id: str) -> ComponentStatus:
    comp = state.components[component_id]
    metric = f"component.{component_id}.health"
    sev = engine.metrics.severity(metric, state) if engine.metrics.has(metric) else 0.0
    return ComponentStatus(
        id=component_id,
        health=rnd(comp.health, 3),
        condition=band(sev),
        in_maintenance=comp.maintenance_remaining_ticks > 0,
        maintenance_remaining_ticks=comp.maintenance_remaining_ticks,
        fault_count=comp.fault_count,
    )


def _system_components(engine: SimulationEngine, system: str) -> list[str]:
    sc = engine.scenario
    deg = sc.degradation
    out: list[str] = []
    if system == "power":
        out += [deg.battery_component, deg.solar_component]
    if system == "thermal":
        out.append(deg.heater_component)
    if system == "communications":
        out.append(deg.comms_component)
    if system == "rover":
        out.append(sc.rover.component)
    for c in sc.power.consumers:
        if c.system == system and c.component and c.component not in out:
            out.append(c.component)
    return [c for c in out if c in {x.id for x in deg.components}]


def build_system(
    engine: SimulationEngine, state: MissionState, system: str, label: str
) -> SystemStatus:
    sc = engine.scenario
    consumers = []
    for spec in sorted(
        (c for c in sc.power.consumers if c.system == system), key=lambda c: c.priority
    ):
        cs = state.power.consumers[spec.id]
        consumers.append(
            ConsumerView(
                id=spec.id,
                label=spec.label,
                priority=spec.priority,
                mode=cs.mode.value,
                available_modes=[
                    m for m in MODE_ORDER if m in {x.value for x in spec.mode_factors}
                ],
                demand_kw=rnd(cs.demand_kw, 2),
                allocated_kw=rnd(cs.allocated_kw, 2),
                supply_ratio=rnd(cs.supply_ratio, 3),
            )
        )
    components = [_component(engine, state, c) for c in _system_components(engine, system)]
    if system == "power":
        load = state.power.demand_kw
        allocated = state.power.allocated_kw
    else:
        load = sum(state.power.consumers[c.id].demand_kw for c in consumers)
        allocated = sum(state.power.consumers[c.id].allocated_kw for c in consumers)
    metrics = {m for m in _SYSTEM_METRICS.get(system, ()) if engine.metrics.has(m)}
    metrics |= {f"power.supply_ratio.{c.id}" for c in consumers}
    metrics |= {f"component.{c.id}.health" for c in components}
    severities = [
        engine.metrics.severity(m, state)
        for m in metrics
        if engine.metrics.has(m) and engine.metrics.spec(m).severity is not None
    ]
    return SystemStatus(
        id=system,
        label=label,
        state=band(max(severities, default=0.0)),
        warning_state=worst_warning(active_alert_levels(engine, state, metrics)),
        load_kw=rnd(load, 2),
        allocated_kw=rnd(allocated, 2),
        supply_ratio=rnd(allocated / load, 3) if load > 0 else 1.0,
        consumers=consumers,
        components=components,
    )


def build_systems(engine: SimulationEngine, state: MissionState) -> SystemOverview:
    return SystemOverview(
        systems=[build_system(engine, state, sid, label) for sid, label in SYSTEMS]
    )
