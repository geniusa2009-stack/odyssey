"""Metric registry: named, read-only views of mission state.

Metrics are the *only* way scenario data (conditions, alerts, objectives) and analysis code
(dependency graph, root cause, Future Lens, profile) read state. This keeps the condition
language safe (no attribute access by string, no eval) and gives every analysable quantity a
stable name.

Each metric may have a *severity* spec mapping its value onto 0 (nominal) .. 1 (critical). The
severity is what root-cause tracing and cascade detection reason about.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.simulation.domain.enums import CrewLocation, RoverStatus, SubsystemMode
from app.simulation.domain.state import MissionState
from app.simulation.scenarios.schema import ConsumerSpec, ScenarioDefinition

Getter = Callable[[MissionState], float]

ROVER_STATUS_CODES: dict[RoverStatus, float] = {
    RoverStatus.DOCKED: 0.0,
    RoverStatus.TRAVERSING: 1.0,
    RoverStatus.RETURNING: 2.0,
    RoverStatus.STOWED: 3.0,
    RoverStatus.LOST: 4.0,
}


@dataclass(frozen=True, slots=True)
class SeveritySpec:
    direction: Literal["below", "above"]
    nominal: float
    critical: float

    def severity(self, value: float) -> float:
        span = self.nominal - self.critical
        if span == 0:
            return 0.0
        raw = (self.nominal - value) / span
        return min(1.0, max(0.0, raw))


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    unit: str
    label: str
    getter: Getter
    severity: SeveritySpec | None = None


class UnknownMetricError(KeyError):
    pass


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(hi, max(lo, v))


# Getter factories: bind loop variables explicitly (no late-binding lambdas).
def _supply_ratio_getter(consumer_id: str) -> Getter:
    def get(s: MissionState) -> float:
        return s.power.consumers[consumer_id].supply_ratio

    return get


def _mode_getter(spec: ConsumerSpec) -> Getter:
    nominal = max(spec.mode_factors.get(SubsystemMode.NOMINAL, 1.0), 1e-9)

    def get(s: MissionState) -> float:
        return spec.mode_factors.get(s.power.consumers[spec.id].mode, 0.0) / nominal

    return get


def _component_health_getter(component_id: str) -> Getter:
    def get(s: MissionState) -> float:
        return s.components[component_id].health

    return get


def _maintenance_getter(component_id: str) -> Getter:
    def get(s: MissionState) -> float:
        return 1.0 if s.components[component_id].maintenance_remaining_ticks > 0 else 0.0

    return get


class MetricRegistry:
    """Builds the metric table for one scenario (consumer/component metrics are per-scenario)."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self.scenario = scenario
        self._specs: dict[str, MetricSpec] = {}
        self._build()
        for name, (direction, nominal, critical) in scenario.analysis.severity_overrides.items():
            spec = self.spec(name)
            self._specs[name] = MetricSpec(
                spec.name,
                spec.unit,
                spec.label,
                spec.getter,
                SeveritySpec(direction, nominal, critical),
            )

    # ----------------------------------------------------------------------------------------
    def _add(
        self,
        name: str,
        unit: str,
        label: str,
        getter: Getter,
        severity: tuple[Literal["below", "above"], float, float] | None = None,
    ) -> None:
        sev = SeveritySpec(*severity) if severity is not None else None
        self._specs[name] = MetricSpec(name, unit, label, getter, sev)

    def _build(self) -> None:
        sc = self.scenario
        ls = sc.life_support
        crew_n = len(sc.crew)
        o2_day = ls.o2_consumption_kg_per_crew_day * crew_n
        water_day = ls.water_use_kg_per_crew_day * crew_n
        food_day = sc.food.consumption_kg_per_crew_day * crew_n
        discretionary_ids = {sc.power.science_consumer, sc.power.rover_charger_consumer}
        nominal_total_kw = sum(
            c.nominal_kw for c in sc.power.consumers if c.id not in discretionary_ids
        )
        battery_comp = sc.degradation.battery_component
        tick_h = sc.time.tick_hours
        ch = sc.crew_health

        def battery_capacity(s: MissionState) -> float:
            health = s.components[battery_comp].health
            return sc.power.battery.capacity_kwh * max(0.05, health)

        self._add("time.tick", "tick", "Simulation tick", lambda s: float(s.tick))
        self._add("time.hours", "h", "Mission elapsed time", lambda s: s.tick * tick_h)

        self._add(
            "env.solar_availability",
            "fraction",
            "Solar availability",
            lambda s: s.environment.solar_availability,
            ("below", 0.8, 0.0),
        )
        self._add(
            "env.sink_temp_c",
            "°C",
            "External sink temperature",
            lambda s: s.environment.sink_temp_c,
            ("below", -40.0, -170.0),
        )
        self._add(
            "env.radiation_dose_rate_msv_h",
            "mSv/h",
            "Surface radiation dose rate",
            lambda s: s.environment.radiation_dose_rate_msv_h,
            ("above", 0.06, 1.0),
        )
        self._add(
            "env.earth_visible",
            "bool",
            "Earth link geometry available",
            lambda s: 1.0 if s.environment.earth_visible else 0.0,
            ("below", 1.0, 0.0),
        )

        self._add("power.generation_kw", "kW", "Solar generation", lambda s: s.power.generation_kw)
        self._add(
            "power.generation_ratio",
            "fraction",
            "Generation vs rated",
            lambda s: s.power.generation_kw / sc.power.solar_rated_kw,
            ("below", 0.6, 0.0),
        )
        self._add("power.demand_kw", "kW", "Total electrical demand", lambda s: s.power.demand_kw)
        self._add(
            "power.demand_ratio",
            "fraction",
            "Demand vs nominal essential load",
            lambda s: s.power.demand_kw / nominal_total_kw if nominal_total_kw else 0.0,
            ("above", 1.0, 1.6),
        )
        self._add("power.unmet_kw", "kW", "Unmet demand (load shed)", lambda s: s.power.unmet_kw)
        self._add(
            "power.battery_charge_kwh",
            "kWh",
            "Battery charge",
            lambda s: s.power.battery_charge_kwh,
        )
        self._add(
            "power.battery_soc",
            "fraction",
            "Battery state of charge",
            lambda s: _clamp(s.power.battery_charge_kwh / battery_capacity(s)),
            ("below", 0.4, 0.05),
        )
        self._add(
            "power.dust_factor",
            "fraction",
            "Array dust transmission",
            lambda s: s.power.dust_factor,
            ("below", 1.0, 0.6),
        )

        boost_extra: Callable[[MissionState], float] = lambda s: sum(  # noqa: E731
            max(0.0, (sc.consumer(c.id).mode_factors.get(c.mode, 1.0) - 1.0))
            * sc.consumer(c.id).nominal_kw
            for c in s.power.consumers.values()
        )
        self._add(
            "control.boost_load_kw",
            "kW",
            "Extra load from boost modes",
            boost_extra,
            ("above", 0.0, 3.0),
        )
        discretionary = (sc.power.science_consumer, sc.power.rover_charger_consumer)
        self._add(
            "control.discretionary_load_kw",
            "kW",
            "Demand from discretionary loads (science payload, rover charging)",
            lambda s: sum(s.power.consumers[c].demand_kw for c in discretionary),
            ("above", 0.0, 3.0),
        )
        for spec in sc.power.consumers:
            self._add(
                f"power.supply_ratio.{spec.id}",
                "fraction",
                f"Power supply to {spec.label}",
                _supply_ratio_getter(spec.id),
                ("below", 1.0, 0.0),
            )
            self._add(
                f"control.mode.{spec.id}",
                "factor",
                f"Mode of {spec.label}",
                _mode_getter(spec),
                ("below", 1.0, 0.0),
            )

        self._add(
            "control.thermal_setpoint",
            "°C",
            "Thermostat setpoint",
            lambda s: s.thermal.setpoint_c,
            ("below", sc.thermal.initial_setpoint_c, sc.thermal.setpoint_min_c),
        )
        self._add(
            "control.ration_level",
            "fraction",
            "Food ration level",
            lambda s: s.food.ration_level,
            ("below", 1.0, sc.food.ration_min),
        )

        self._add(
            "thermal.habitat_temp_c",
            "°C",
            "Habitat temperature",
            lambda s: s.thermal.habitat_temp_c,
            ("below", ch.cold_threshold_c, ch.cold_threshold_c - 15.0),
        )

        self._add(
            "life_support.oxygen_kg", "kg", "Oxygen reserve", lambda s: s.life_support.oxygen_kg
        )
        self._add(
            "life_support.oxygen_days",
            "days",
            "Oxygen reserve (days of crew use)",
            lambda s: s.life_support.oxygen_kg / o2_day if o2_day else 0.0,
            ("below", 3.0, 0.0),
        )
        self._add(
            "life_support.o2_generation_ratio",
            "fraction",
            "O2 generation vs crew use",
            lambda s: (
                s.life_support.o2_generated_kg / s.life_support.o2_required_kg
                if s.life_support.o2_required_kg > 0
                else 1.0
            ),
            ("below", 1.0, 0.0),
        )
        self._add("life_support.co2_kg", "kg", "Cabin CO2 mass", lambda s: s.life_support.co2_kg)
        self._add(
            "life_support.co2_ppm",
            "ppm",
            "Cabin CO2 concentration",
            lambda s: s.life_support.co2_kg * ls.co2_ppm_per_kg,
            ("above", ch.co2_warning_ppm, ch.co2_critical_ppm),
        )
        self._add("life_support.water_kg", "kg", "Water reserve", lambda s: s.life_support.water_kg)
        self._add(
            "life_support.water_days",
            "days",
            "Water reserve (days of gross crew use, no recycling)",
            lambda s: s.life_support.water_kg / water_day if water_day else 0.0,
            ("below", 5.0, 0.0),
        )
        self._add(
            "life_support.water_recovery_efficiency",
            "fraction",
            "Water recovery efficiency",
            lambda s: s.life_support.water_recovery_efficiency,
            ("below", ls.water_recovery_nominal, 0.0),
        )

        self._add("food.food_kg", "kg", "Food reserve", lambda s: s.food.food_kg)
        self._add(
            "food.food_days",
            "days",
            "Food reserve (days at full ration)",
            lambda s: s.food.food_kg / food_day if food_day else 0.0,
            ("below", 5.0, 0.0),
        )

        self._add(
            "crew.min_health",
            "index",
            "Lowest crew health",
            lambda s: min((c.health for c in s.crew), default=0.0),
            ("below", 0.9, 0.0),
        )
        self._add(
            "crew.mean_health",
            "index",
            "Mean crew health",
            lambda s: sum(c.health for c in s.crew) / len(s.crew) if s.crew else 0.0,
        )
        self._add(
            "crew.max_dose_msv",
            "mSv",
            "Highest crew dose",
            lambda s: max((c.dose_msv for c in s.crew), default=0.0),
            ("above", 20.0, 250.0),
        )
        rad = sc.radiation
        shielding = {
            CrewLocation.HABITAT: rad.habitat_shielding_factor,
            CrewLocation.SHELTER: rad.shelter_shielding_factor,
            CrewLocation.EVA: rad.eva_shielding_factor,
        }

        def received_rate(s: MissionState) -> float:
            rate = s.environment.radiation_dose_rate_msv_h
            return max((rate * shielding[c.location] for c in s.crew if c.health > 0), default=0.0)

        # Severity starts exactly where the crew model starts harming health (acute threshold).
        self._add(
            "crew.received_dose_rate_msv_h",
            "mSv/h",
            "Highest dose rate received by a crew member (after shielding)",
            received_rate,
            ("above", rad.health_threshold_msv_per_hour, rad.health_threshold_msv_per_hour + 1.0),
        )
        if rad.dose_limit_msv is not None:
            self._add_dose_budget(rad.dose_limit_msv, shielding[CrewLocation.HABITAT])
        self._add(
            "crew.max_fatigue",
            "index",
            "Highest crew fatigue",
            lambda s: max((c.fatigue for c in s.crew), default=0.0),
        )
        self._add(
            "crew.active_count",
            "people",
            "Crew not incapacitated",
            lambda s: float(sum(1 for c in s.crew if c.health > 0)),
        )
        self._add(
            "crew.in_shelter",
            "bool",
            "Crew in radiation shelter",
            lambda s: 1.0 if any(c.location == CrewLocation.SHELTER for c in s.crew) else 0.0,
        )

        self._add(
            "comms.link_up",
            "bool",
            "Communication link up",
            lambda s: 1.0 if s.comms.link_up else 0.0,
            ("below", 1.0, 0.0),
        )
        self._add(
            "comms.data_downlinked_mb",
            "MB",
            "Science data downlinked",
            lambda s: s.comms.data_downlinked_mb,
        )

        self._add("science.points", "points", "Science return", lambda s: s.science.points)
        self._add(
            "science.data_pending_mb",
            "MB",
            "Science data awaiting downlink",
            lambda s: s.science.data_pending_mb,
        )
        self._add(
            "science.opportunities_completed",
            "count",
            "Science activities completed",
            lambda s: float(
                sum(1 for o in s.science.opportunities.values() if o.status == "completed")
            ),
        )

        self._add("rover.battery_kwh", "kWh", "Rover battery", lambda s: s.rover.battery_kwh)
        self._add(
            "rover.status_code",
            "code",
            "Rover status",
            lambda s: ROVER_STATUS_CODES[s.rover.status],
        )
        self._add(
            "rover.lost",
            "bool",
            "Rover lost",
            lambda s: 1.0 if s.rover.status == RoverStatus.LOST else 0.0,
            ("above", 0.0, 1.0),
        )

        for comp in sc.degradation.components:
            self._add(
                f"component.{comp.id}.health",
                "index",
                f"{comp.id} health",
                _component_health_getter(comp.id),
                ("below", 0.9, 0.3),
            )
            self._add(
                f"component.{comp.id}.in_maintenance",
                "bool",
                f"{comp.id} under maintenance",
                _maintenance_getter(comp.id),
            )

        self._add(
            "mission.critical_alerts",
            "count",
            "Active critical alerts",
            lambda s: float(sum(1 for a in s.alerts.values() if a.severity == "critical")),
        )
        self._add(
            "mission.concluded",
            "bool",
            "Mission concluded",
            lambda s: 1.0 if s.status == "concluded" else 0.0,
        )

        risk_terms = sc.analysis.risk_terms

        def risk(s: MissionState) -> float:
            survive = 1.0
            for term in risk_terms:
                survive *= 1.0 - term.weight * self.severity(term.metric, s)
            return _clamp(1.0 - survive)

        self._add(
            "risk.mission", "index", "Composite mission risk indicator", risk, ("above", 0.2, 1.0)
        )

    def _add_dose_budget(self, limit: float, habitat_shielding: float) -> None:
        """Dose-budget metrics: what a crew dosimeter and the mission plan already tell you.

        ``background(t)`` is the scenario's *baseline* surface dose rate (keyframes, no event
        modifiers), so the projection never uses knowledge of future space-weather events.
            projected = max over active crew of (dose + Σ_{k ≥ t} background(k) · s_habitat · Δt)
            margin    = limit − max dose;  projected margin = limit − projected
        """
        # Imported here: conditions imports this module (cycle at module level).
        from app.simulation.engine.conditions import interpolate

        sc = self.scenario
        frames = [(f.tick, f.value) for f in sc.environment.radiation_dose_rate_msv_h]
        dt = sc.time.tick_hours
        remaining = [0.0] * (sc.time.max_ticks + 2)
        for k in range(sc.time.max_ticks - 1, -1, -1):
            remaining[k] = remaining[k + 1] + interpolate(frames, k) * habitat_shielding * dt

        def background(s: MissionState) -> float:
            return interpolate(frames, s.tick)

        def projected(s: MissionState) -> float:
            future = remaining[min(max(s.tick, 0), len(remaining) - 1)]
            active = [c.dose_msv for c in s.crew if c.health > 0] or [0.0]
            return max(active) + future

        third = limit / 3.0
        self._add(
            "env.background_dose_rate_msv_h",
            "mSv/h",
            "Baseline surface dose rate (no space-weather events)",
            background,
        )
        self._add(
            "crew.dose_margin_msv",
            "mSv",
            "Dose remaining before the mission limit (highest crew dose)",
            lambda s: limit - max((c.dose_msv for c in s.crew), default=0.0),
            ("below", third, 0.0),
        )
        self._add(
            "crew.projected_dose_msv",
            "mSv",
            "Projected end-of-mission dose if the crew stays in the habitat at background",
            projected,
            ("above", limit - third, limit),
        )
        self._add(
            "crew.projected_dose_margin_msv",
            "mSv",
            "Mission dose limit minus the projected end-of-mission dose",
            lambda s: limit - projected(s),
            ("below", third, 0.0),
        )

    # ----------------------------------------------------------------------------------------
    def names(self) -> list[str]:
        return sorted(self._specs)

    def has(self, name: str) -> bool:
        return name in self._specs

    def spec(self, name: str) -> MetricSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise UnknownMetricError(name) from exc

    def value(self, name: str, state: MissionState) -> float:
        return float(self.spec(name).getter(state))

    def severity(self, name: str, state: MissionState) -> float:
        spec = self.spec(name)
        if spec.severity is None:
            return 0.0
        return spec.severity.severity(float(spec.getter(state)))

    def frame(self, state: MissionState) -> dict[str, float]:
        """All metric values for one state (used to build time series)."""
        return {name: float(spec.getter(state)) for name, spec in self._specs.items()}
