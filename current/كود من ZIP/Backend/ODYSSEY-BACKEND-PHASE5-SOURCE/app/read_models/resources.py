"""Resource read models: one stable representation per resource a client shows.

Each resource names its headline metric (from the engine's metric registry), the value rounded
to display precision, its unit, the status band from the scenario's severity scale, the worst
active alert on its metrics, a fill fraction and range where meaningful, and a trend computed
**only** from recorded states (with no earlier recorded state: ``insufficient_data``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.read_models.common import (
    MetricValue,
    StatusBand,
    View,
    WarningState,
    active_alert_levels,
    band,
    metric_value,
    precision,
    rnd,
    rnd_unit,
    worst_warning,
)
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

RangeFn = Callable[[SimulationEngine, MissionState], tuple[float, float]]
TrendDirection = Literal["rising", "falling", "steady", "unknown"]


@dataclass(frozen=True, slots=True)
class ResourceDef:
    """Static description of one resource (which metrics it is made of)."""

    id: str
    label: str
    metric: str
    details: tuple[tuple[str, str], ...] = ()
    fill_metric: str | None = None
    value_range: RangeFn | None = None
    requires_metric: str | None = None
    extra_alert_metrics: tuple[str, ...] = field(default=())


def _solar_range(engine: SimulationEngine, _: MissionState) -> tuple[float, float]:
    return 0.0, engine.scenario.power.solar_rated_kw


def _unit_range(_: SimulationEngine, __: MissionState) -> tuple[float, float]:
    return 0.0, 1.0


def _rover_range(engine: SimulationEngine, _: MissionState) -> tuple[float, float]:
    return 0.0, engine.scenario.rover.battery_capacity_kwh


RESOURCES: tuple[ResourceDef, ...] = (
    ResourceDef(
        "power",
        "Power",
        "power.generation_kw",
        details=(
            ("demand_kw", "power.demand_kw"),
            ("unmet_kw", "power.unmet_kw"),
            ("generation_ratio", "power.generation_ratio"),
            ("dust_factor", "power.dust_factor"),
        ),
        value_range=_solar_range,
        extra_alert_metrics=("power.unmet_kw", "power.generation_ratio", "power.demand_ratio"),
    ),
    ResourceDef(
        "battery",
        "Battery",
        "power.battery_soc",
        details=(("charge_kwh", "power.battery_charge_kwh"),),
        fill_metric="power.battery_soc",
        value_range=_unit_range,
    ),
    ResourceDef(
        "oxygen",
        "Oxygen",
        "life_support.oxygen_days",
        details=(
            ("oxygen_kg", "life_support.oxygen_kg"),
            ("generation_ratio", "life_support.o2_generation_ratio"),
        ),
    ),
    ResourceDef("co2", "CO2", "life_support.co2_ppm", details=(("co2_kg", "life_support.co2_kg"),)),
    ResourceDef(
        "water",
        "Water",
        "life_support.water_days",
        details=(
            ("water_kg", "life_support.water_kg"),
            ("recovery_efficiency", "life_support.water_recovery_efficiency"),
        ),
    ),
    ResourceDef(
        "food",
        "Food",
        "food.food_days",
        details=(("food_kg", "food.food_kg"), ("ration_level", "control.ration_level")),
    ),
    ResourceDef(
        "thermal",
        "Habitat temperature",
        "thermal.habitat_temp_c",
        details=(("setpoint_c", "control.thermal_setpoint"), ("sink_temp_c", "env.sink_temp_c")),
    ),
    ResourceDef(
        "communications",
        "Communications",
        "comms.link_up",
        details=(
            ("data_downlinked_mb", "comms.data_downlinked_mb"),
            ("earth_visible", "env.earth_visible"),
        ),
        extra_alert_metrics=("env.earth_visible",),
    ),
    ResourceDef(
        "science",
        "Science",
        "science.points",
        details=(
            ("opportunities_completed", "science.opportunities_completed"),
            ("data_pending_mb", "science.data_pending_mb"),
        ),
    ),
    ResourceDef(
        "radiation",
        "Radiation",
        "crew.max_dose_msv",
        details=(
            ("received_dose_rate_msv_h", "crew.received_dose_rate_msv_h"),
            ("surface_dose_rate_msv_h", "env.radiation_dose_rate_msv_h"),
            ("dose_margin_msv", "crew.dose_margin_msv"),
            ("projected_dose_msv", "crew.projected_dose_msv"),
        ),
        extra_alert_metrics=(
            "env.radiation_dose_rate_msv_h",
            "crew.received_dose_rate_msv_h",
            "crew.dose_margin_msv",
            "crew.projected_dose_margin_msv",
        ),
    ),
    ResourceDef(
        "rover",
        "Rover",
        "rover.battery_kwh",
        value_range=_rover_range,
        requires_metric="rover.battery_kwh",
        extra_alert_metrics=("rover.lost",),
    ),
)
_BY_ID: dict[str, ResourceDef] = {r.id: r for r in RESOURCES}


def resource_defs(engine: SimulationEngine) -> list[ResourceDef]:
    """The resources this scenario has (a resource needs its metrics in the registry)."""
    has = engine.metrics.has
    return [
        r
        for r in RESOURCES
        if has(r.metric) and (r.requires_metric is None or has(r.requires_metric))
    ]


class Thresholds(View):
    """The scenario's severity scale for the headline metric."""

    direction: Literal["below", "above"]
    nominal: float
    critical: float


class ValueRange(View):
    min: float
    max: float


class TrendView(View):
    """Change since the most recent *recorded* earlier state (never extrapolated)."""

    basis: Literal["recorded_snapshot", "insufficient_data"]
    direction: TrendDirection
    delta: float | None = None
    per_hour: float | None = None
    window_hours: float | None = None
    from_tick: int | None = None


class ResourceView(View):
    id: str
    label: str
    metric: str
    value: float
    unit: str
    display_precision: int
    state: StatusBand
    pressure: float | None
    warning_state: WarningState
    fill_fraction: float | None = None
    range: ValueRange | None = None
    thresholds: Thresholds | None = None
    trend: TrendView
    details: list[MetricValue]


class AlertRuleView(View):
    alert_id: str
    metric: str
    op: str
    threshold: float
    clear_threshold: float
    severity: str
    active: bool


class HistoryPoint(View):
    tick: int
    hours: float
    value: float


class ResourceDetailView(View):
    resource: ResourceView
    alert_rules: list[AlertRuleView]
    history_basis: Literal["recorded_snapshots"] = "recorded_snapshots"
    history: list[HistoryPoint]


def _trend(
    engine: SimulationEngine,
    metric: str,
    unit: str,
    state: MissionState,
    previous: MissionState | None,
) -> TrendView:
    if previous is None or previous.tick >= state.tick:
        return TrendView(basis="insufficient_data", direction="unknown")
    now = engine.metrics.value(metric, state)
    before = engine.metrics.value(metric, previous)
    delta = rnd_unit(now - before, unit)
    hours = (state.tick - previous.tick) * engine.scenario.time.tick_hours
    direction: TrendDirection = "steady" if delta == 0 else ("rising" if delta > 0 else "falling")
    return TrendView(
        basis="recorded_snapshot",
        direction=direction,
        delta=delta,
        per_hour=rnd((now - before) / hours, precision(unit) + 1) if hours > 0 else None,
        window_hours=rnd(hours, 1),
        from_tick=previous.tick,
    )


def build_resource(
    engine: SimulationEngine,
    state: MissionState,
    rdef: ResourceDef,
    previous: MissionState | None = None,
) -> ResourceView:
    metrics = engine.metrics
    spec = metrics.spec(rdef.metric)
    sev = spec.severity
    details = [
        metric_value(engine, state, m, field_id) for field_id, m in rdef.details if metrics.has(m)
    ]
    watched = {rdef.metric, *rdef.extra_alert_metrics} | {
        m for _, m in rdef.details if metrics.has(m)
    }
    rng = rdef.value_range(engine, state) if rdef.value_range else None
    fill = (
        rnd(min(1.0, max(0.0, metrics.value(rdef.fill_metric, state))), 3)
        if rdef.fill_metric
        else None
    )
    if fill is None and rng is not None and rdef.id == "rover" and rng[1] > 0:
        fill = rnd(min(1.0, max(0.0, metrics.value(rdef.metric, state) / rng[1])), 3)
    severity = metrics.severity(rdef.metric, state) if sev is not None else None
    return ResourceView(
        id=rdef.id,
        label=rdef.label,
        metric=rdef.metric,
        value=rnd_unit(metrics.value(rdef.metric, state), spec.unit),
        unit=spec.unit,
        display_precision=precision(spec.unit),
        state=band(severity) if severity is not None else "nominal",
        pressure=rnd(severity, 2) if severity is not None else None,
        warning_state=worst_warning(active_alert_levels(engine, state, watched)),
        fill_fraction=fill,
        range=ValueRange(min=rng[0], max=rng[1]) if rng else None,
        thresholds=Thresholds(direction=sev.direction, nominal=sev.nominal, critical=sev.critical)
        if sev is not None
        else None,
        trend=_trend(engine, rdef.metric, spec.unit, state, previous),
        details=details,
    )


def build_resources(
    engine: SimulationEngine, state: MissionState, previous: MissionState | None = None
) -> list[ResourceView]:
    return [build_resource(engine, state, r, previous) for r in resource_defs(engine)]


def get_resource_def(engine: SimulationEngine, resource_id: str) -> ResourceDef | None:
    rdef = _BY_ID.get(resource_id)
    if rdef is None or rdef not in resource_defs(engine):
        return None
    return rdef


def build_resource_detail(
    engine: SimulationEngine,
    state: MissionState,
    rdef: ResourceDef,
    previous: MissionState | None,
    recorded: Sequence[MissionState],
) -> ResourceDetailView:
    """``recorded``: persisted states of this timeline up to now, oldest first (known past)."""
    view = build_resource(engine, state, rdef, previous)
    watched = {rdef.metric, *rdef.extra_alert_metrics} | {m for _, m in rdef.details}
    active = set(state.alerts)
    rules = [
        AlertRuleView(
            alert_id=a.id,
            metric=a.metric,
            op=a.op,
            threshold=a.threshold,
            clear_threshold=a.clear_threshold,
            severity=a.severity.value,
            active=a.id in active,
        )
        for a in engine.scenario.alerts
        if a.metric in watched
    ]
    tick_hours = engine.scenario.time.tick_hours
    seen: set[int] = set()
    history: list[HistoryPoint] = []
    for s in recorded:
        if s.tick in seen or s.tick > state.tick:
            continue
        seen.add(s.tick)
        history.append(
            HistoryPoint(
                tick=s.tick,
                hours=rnd(s.tick * tick_hours, 1),
                value=rnd_unit(engine.metrics.value(rdef.metric, s), view.unit),
            )
        )
    history.sort(key=lambda p: p.tick)
    return ResourceDetailView(resource=view, alert_rules=rules, history=history)
