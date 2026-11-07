"""Declarative scenario definition.

A scenario is pure data (YAML) validated by these models. Mission designers can define phases,
events, objectives, alert rules and every balancing constant without touching engine code.

All numeric values in shipped scenarios are PROVISIONAL until the balancing decision in
``docs/USER_DECISIONS_REQUIRED.md`` is made; ``ScenarioDefinition.provisional`` flags this.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.simulation.domain.enums import AlertSeverity, CrewRole, EventKind, SubsystemMode


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------------------------
# Condition language (safe, declarative — no eval)
# --------------------------------------------------------------------------------------------

ComparisonOp = Literal["<", "<=", ">", ">=", "==", "!="]


class Condition(_Spec):
    """Exactly one of: ``metric``/``op``/``value``, ``all``, ``any``, ``not_``."""

    metric: str | None = None
    op: ComparisonOp | None = None
    value: float | None = None
    all: list[Condition] | None = None
    any: list[Condition] | None = None
    not_: Condition | None = Field(default=None, alias="not")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _exactly_one_form(self) -> Self:
        forms = [
            self.metric is not None,
            self.all is not None,
            self.any is not None,
            self.not_ is not None,
        ]
        if sum(forms) != 1:
            raise ValueError("condition must have exactly one of metric/all/any/not")
        if self.metric is not None and (self.op is None or self.value is None):
            raise ValueError("metric condition requires op and value")
        return self

    def metrics(self) -> set[str]:
        found: set[str] = set()
        if self.metric is not None:
            found.add(self.metric)
        for child in (self.all or []) + (self.any or []):
            found |= child.metrics()
        if self.not_ is not None:
            found |= self.not_.metrics()
        return found


# --------------------------------------------------------------------------------------------
# Systems configuration
# --------------------------------------------------------------------------------------------


class TimeConfig(_Spec):
    tick_hours: float = Field(gt=0, le=24)
    max_ticks: int = Field(gt=0, le=100_000)


class CrewSpec(_Spec):
    id: str
    role: CrewRole


class ConsumerSpec(_Spec):
    id: str
    label: str
    system: Literal["habitat", "thermal", "life_support", "science", "communications", "rover"]
    priority: int = Field(ge=0, description="Lower number = powered first")
    nominal_kw: float = Field(ge=0)
    component: str | None = Field(None, description="Component whose health/maintenance gates it")
    initial_mode: SubsystemMode = SubsystemMode.NOMINAL
    mode_factors: dict[SubsystemMode, float] = Field(
        description="Demand AND output multiplier per mode"
    )

    @model_validator(mode="after")
    def _modes(self) -> Self:
        if self.initial_mode not in self.mode_factors:
            raise ValueError(f"consumer {self.id}: initial_mode not in mode_factors")
        return self


class BatterySpec(_Spec):
    capacity_kwh: float = Field(gt=0)
    initial_soc: float = Field(ge=0, le=1)
    max_charge_kw: float = Field(gt=0)
    max_discharge_kw: float = Field(gt=0)
    charge_efficiency: float = Field(gt=0, le=1)
    discharge_efficiency: float = Field(gt=0, le=1)
    deep_discharge_soc: float = Field(ge=0, le=1, description="Below this SOC wear accelerates")


class PowerConfig(_Spec):
    solar_rated_kw: float = Field(gt=0)
    dust_deposition_per_tick: float = Field(ge=0, le=1)
    dust_floor: float = Field(ge=0, le=1)
    battery: BatterySpec
    consumers: list[ConsumerSpec]
    heater_consumer: str
    rover_charger_consumer: str
    science_consumer: str
    comms_consumer: str


class ThermalConfig(_Spec):
    initial_temp_c: float
    initial_setpoint_c: float
    setpoint_min_c: float
    setpoint_max_c: float
    conductance_kw_per_k: float = Field(gt=0, description="UA: heat loss per kelvin")
    capacitance_kwh_per_k: float = Field(gt=0, description="Lumped thermal mass")
    internal_heat_fraction: float = Field(ge=0, le=1, description="Share of non-heater load → heat")
    heater_max_kw: float = Field(gt=0)
    heater_gain_kw_per_k: float = Field(
        ge=0, description="Extra heater demand per kelvin below setpoint (recovery)"
    )
    overheat_relaxation_k_per_hour: float = Field(
        gt=0, description="Active thermal control: max cooling rate when above setpoint"
    )


class LifeSupportConfig(_Spec):
    initial_oxygen_kg: float = Field(ge=0)
    oxygen_capacity_kg: float = Field(gt=0)
    initial_co2_kg: float = Field(ge=0)
    initial_water_kg: float = Field(ge=0)
    o2_consumption_kg_per_crew_day: float = Field(gt=0)
    co2_production_kg_per_crew_day: float = Field(gt=0)
    water_use_kg_per_crew_day: float = Field(gt=0)
    o2_generation_capacity_kg_per_hour: float = Field(gt=0)
    water_per_kg_o2: float = Field(gt=0, description="Electrolysis stoichiometry, kg H2O per kg O2")
    co2_removal_capacity_kg_per_hour: float = Field(gt=0)
    co2_ppm_per_kg: float = Field(gt=0, description="Cabin CO2 mass → ppm conversion")
    co2_floor_kg: float = Field(ge=0, description="Scrubber cannot remove below this")
    water_recovery_nominal: float = Field(ge=0, le=1)
    water_recovery_min_temp_c: float
    water_recovery_zero_temp_c: float
    oxygen_generator_consumer: str
    co2_scrubber_consumer: str
    water_recovery_consumer: str

    @model_validator(mode="after")
    def _temps(self) -> Self:
        if self.water_recovery_zero_temp_c >= self.water_recovery_min_temp_c:
            raise ValueError("water_recovery_zero_temp_c must be below water_recovery_min_temp_c")
        return self


class FoodConfig(_Spec):
    initial_food_kg: float = Field(ge=0)
    consumption_kg_per_crew_day: float = Field(gt=0)
    ration_min: float = Field(gt=0, le=1)


class CommsConfig(_Spec):
    downlink_mb_per_hour: float = Field(ge=0)


class ScienceOpportunitySpec(_Spec):
    id: str
    window_ticks: int = Field(gt=0)
    work_ticks_required: int = Field(gt=0)
    points_per_tick: float = Field(ge=0)
    data_mb_per_tick: float = Field(ge=0)
    requires_rover: bool = False


class ScienceConfig(_Spec):
    opportunities: list[ScienceOpportunitySpec]


class RadiationConfig(_Spec):
    habitat_shielding_factor: float = Field(ge=0, le=1, description="Dose fraction inside habitat")
    shelter_shielding_factor: float = Field(ge=0, le=1)
    eva_shielding_factor: float = Field(ge=0, le=1)
    health_threshold_msv_per_hour: float = Field(
        ge=0, description="Received dose rate above which health is penalised"
    )
    health_penalty_per_msv: float = Field(ge=0)
    dose_limit_msv: float | None = Field(
        None,
        gt=0,
        description="Mission dose limit. When set, the engine exposes dose-margin and "
        "projected-dose metrics so players can budget exposure (no future events are used).",
    )


class RoverConfig(_Spec):
    battery_capacity_kwh: float = Field(gt=0)
    initial_battery_kwh: float = Field(ge=0)
    traverse_kw: float = Field(ge=0)
    charger_kw: float = Field(ge=0)
    transfer_efficiency: float = Field(gt=0, le=1)
    transfer_kw: float = Field(gt=0)
    outbound_ticks: int = Field(gt=0)
    component: str
    loss_probability_per_tick: float = Field(ge=0, le=1, description="Scaled by (1 - health)")
    teleop_requires_link: bool = True


class CrewHealthConfig(_Spec):
    recovery_per_tick: float = Field(ge=0)
    hypoxia_penalty_per_tick: float = Field(ge=0)
    co2_warning_ppm: float = Field(gt=0)
    co2_critical_ppm: float = Field(gt=0)
    co2_penalty_per_tick: float = Field(ge=0)
    cold_threshold_c: float
    cold_penalty_per_k_tick: float = Field(ge=0)
    dehydration_penalty_per_tick: float = Field(ge=0)
    starvation_penalty_per_tick: float = Field(ge=0)
    ration_penalty_per_tick: float = Field(ge=0, description="Scaled by (1 - ration_level)")
    eva_fatigue_per_tick: float = Field(ge=0)
    fatigue_recovery_per_tick: float = Field(ge=0)


class ComponentSpec(_Spec):
    id: str
    wear_per_tick: float = Field(ge=0)
    boost_wear_multiplier: float = Field(ge=1)
    fault_probability_per_tick: float = Field(ge=0, le=1, description="Scaled by (1 - health)")
    fault_damage: float = Field(ge=0, le=1)
    maintenance_ticks: int = Field(ge=1)
    maintenance_restore: float = Field(ge=0, le=1)
    performance_floor: float = Field(
        ge=0, le=1, description="Output multiplier at health 0 (linear between floor and 1)"
    )


class DegradationConfig(_Spec):
    components: list[ComponentSpec]
    battery_component: str
    solar_component: str
    heater_component: str
    comms_component: str
    deep_discharge_wear_multiplier: float = Field(ge=1)


class Keyframe(_Spec):
    tick: int = Field(ge=0)
    value: float


class EnvironmentProfile(_Spec):
    """Natural environment, linearly interpolated between keyframes (no trigonometry)."""

    solar_availability: list[Keyframe]
    sink_temp_c: list[Keyframe]
    radiation_dose_rate_msv_h: list[Keyframe]
    earth_visible: list[Keyframe] = Field(description="Step function: value >= 0.5 → visible")
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        for name in (
            "solar_availability",
            "sink_temp_c",
            "radiation_dose_rate_msv_h",
            "earth_visible",
        ):
            frames: list[Keyframe] = getattr(self, name)
            if not frames:
                raise ValueError(f"environment.{name} needs at least one keyframe")
            ticks = [f.tick for f in frames]
            if ticks != sorted(ticks) or len(set(ticks)) != len(ticks):
                raise ValueError(
                    f"environment.{name} keyframes must have strictly increasing ticks"
                )
        return self


# --------------------------------------------------------------------------------------------
# Alerts, events, phases, objectives, outcomes
# --------------------------------------------------------------------------------------------


class AlertRule(_Spec):
    id: str
    metric: str
    op: Literal["<", "<=", ">", ">="]
    threshold: float
    clear_threshold: float = Field(description="Hysteresis: clears when back past this value")
    severity: AlertSeverity
    category: Literal["resource", "system", "crew", "environment", "mission"] = "resource"


ModifierTarget = Literal[
    "env.solar_availability",
    "env.sink_temp_c",
    "env.radiation_dose_rate_msv_h",
    "env.earth_visible",
    "power.dust_deposition",
]


class ModifierEffect(_Spec):
    type: Literal["modifier"] = "modifier"
    target: ModifierTarget
    op: Literal["multiply", "add", "set"]
    value: float
    duration_ticks: int = Field(gt=0)


class DamageComponentEffect(_Spec):
    type: Literal["damage_component"] = "damage_component"
    component: str
    amount: float = Field(gt=0, le=1)


class OpenOpportunityEffect(_Spec):
    type: Literal["open_opportunity"] = "open_opportunity"
    opportunity: str


class AdjustResourceEffect(_Spec):
    type: Literal["adjust_resource"] = "adjust_resource"
    resource: Literal["oxygen_kg", "water_kg", "food_kg", "battery_charge_kwh", "co2_kg"]
    delta: float


class MilestoneEffect(_Spec):
    type: Literal["milestone"] = "milestone"


EventEffect = (
    ModifierEffect
    | DamageComponentEffect
    | OpenOpportunityEffect
    | AdjustResourceEffect
    | MilestoneEffect
)


class ScheduledTrigger(_Spec):
    type: Literal["scheduled"] = "scheduled"
    at_tick: int = Field(ge=0)


class StateTrigger(_Spec):
    type: Literal["state"] = "state"
    condition: Condition
    after_tick: int = 0


class DecisionTrigger(_Spec):
    type: Literal["decision"] = "decision"
    decision_type: str
    match: dict[str, str | float | bool] = Field(default_factory=dict)


class RandomTrigger(_Spec):
    type: Literal["random"] = "random"
    probability_per_tick: float = Field(ge=0, le=1)
    from_tick: int = 0
    to_tick: int | None = None


EventTrigger = ScheduledTrigger | StateTrigger | DecisionTrigger | RandomTrigger


class EventDefinition(_Spec):
    id: str
    kind: EventKind
    severity: AlertSeverity | None = None
    message_key: str = Field(description="Stable key for frontend copy; no dialogue here")
    trigger: EventTrigger = Field(discriminator="type")
    effects: list[EventEffect] = Field(default_factory=list)
    max_fires: int = Field(1, ge=1)
    foreseeable: bool = Field(
        True, description="Whether Future Lens may anticipate it under 'known_only' policy"
    )
    evidence: list[str] = Field(default_factory=list)


class PhaseDefinition(_Spec):
    id: str
    kind: Literal["simulated", "conclusion", "analysis"] = "simulated"
    advance_when: Condition | None = Field(
        None, description="Advance to next simulated phase when true (evaluated after each tick)"
    )


ObjectiveCategory = Literal["primary", "safety", "stability", "science", "efficiency", "discovery"]
OBJECTIVE_CATEGORIES: tuple[str, ...] = (
    "primary",
    "safety",
    "stability",
    "science",
    "efficiency",
    "discovery",
)
# Objectives of a scenario that declares no categories: required → primary, else secondary.
LEGACY_SECONDARY = "secondary"

OutcomeTier = Literal["critical_failure", "mission_failed", "partial", "success", "exceptional"]
OUTCOME_TIERS: tuple[str, ...] = (
    "critical_failure",
    "mission_failed",
    "partial",
    "success",
    "exceptional",
)
# Tier of the outcome codes used before tiers were declared explicitly (scenario v0.1.0).
LEGACY_OUTCOME_TIERS: dict[str, str] = {
    "mission_failed_crew_loss": "critical_failure",
    "mission_failed": "mission_failed",
    "mission_complete_partial": "partial",
    "mission_complete": "success",
}


class ObjectiveDefinition(_Spec):
    id: str
    required: bool
    achieve_when: Condition | None = None
    fail_when: Condition | None = None
    evaluate: Literal["continuous", "at_end"] = "continuous"
    category: ObjectiveCategory | None = Field(
        None,
        description="Pillar the objective belongs to. Primary objectives are mission-critical "
        "(and must be `required`). Omitted: required → primary, otherwise 'secondary'.",
    )

    @model_validator(mode="after")
    def _category_matches_required(self) -> Self:
        if self.category is not None and (self.category == "primary") != self.required:
            raise ValueError(
                f"objective {self.id}: 'required' must be true exactly for primary objectives"
            )
        return self

    @property
    def effective_category(self) -> str:
        if self.category is not None:
            return self.category
        return "primary" if self.required else LEGACY_SECONDARY


class OutcomeRule(_Spec):
    """One outcome rule. Rules are tried in order; the first that matches concludes the mission.

    Category requirements (all optional; omitted = not checked):
    * ``requires_categories``: every objective in these categories is ACHIEVED;
    * ``min_achieved_in_categories``: at least N objectives ACHIEVED per category;
    * ``any_failed_in_categories``: at least one objective in these categories FAILED.
    """

    id: str
    code: str
    when: Condition | None = None
    at_end: bool = False
    requires_required_objectives: bool | None = None
    min_optional_objectives_fraction: float | None = None
    tier: OutcomeTier | None = Field(
        None, description="Outcome class; omitted = inferred from legacy codes"
    )
    requires_categories: list[str] | None = None
    min_achieved_in_categories: dict[str, int] | None = None
    any_failed_in_categories: list[str] | None = None

    @property
    def effective_tier(self) -> str | None:
        return self.tier or LEGACY_OUTCOME_TIERS.get(self.code)

    def category_refs(self) -> set[str]:
        refs = set(self.requires_categories or [])
        refs |= set(self.min_achieved_in_categories or {})
        refs |= set(self.any_failed_in_categories or [])
        return refs

    def has_requirements(self) -> bool:
        return (
            self.when is not None
            or self.requires_required_objectives is not None
            or self.min_optional_objectives_fraction is not None
            or bool(self.category_refs())
        )


class RiskTerm(_Spec):
    metric: str
    weight: float = Field(ge=0, le=1)


class AnalysisConfig(_Spec):
    risk_terms: list[RiskTerm]
    severity_overrides: dict[str, tuple[Literal["below", "above"], float, float]] = Field(
        default_factory=dict
    )
    cascade_parent_threshold: float = Field(0.5, ge=0, le=1)
    cascade_child_threshold: float = Field(0.3, ge=0, le=1)


class DecisionLimits(_Spec):
    eva_ticks: int = Field(gt=0)
    dust_after_cleaning: float = Field(ge=0, le=1)


class ScenarioDefinition(_Spec):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str
    mission_id: str
    title: str
    description: str
    provisional: bool = True
    time: TimeConfig
    crew: list[CrewSpec]
    power: PowerConfig
    thermal: ThermalConfig
    life_support: LifeSupportConfig
    food: FoodConfig
    comms: CommsConfig
    science: ScienceConfig
    radiation: RadiationConfig
    rover: RoverConfig
    crew_health: CrewHealthConfig
    degradation: DegradationConfig
    environment: EnvironmentProfile
    alerts: list[AlertRule]
    events: list[EventDefinition]
    phases: list[PhaseDefinition]
    objectives: list[ObjectiveDefinition]
    outcomes: list[OutcomeRule]
    analysis: AnalysisConfig
    decisions: DecisionLimits
    evidence: dict[str, list[str]] = Field(
        default_factory=dict, description="Config path → ScienceEvidence ids"
    )

    @model_validator(mode="after")
    def _references(self) -> Self:
        consumers = {c.id for c in self.power.consumers}
        components = {c.id for c in self.degradation.components}
        opportunities = {o.id for o in self.science.opportunities}
        crew_ids = [c.id for c in self.crew]
        problems: list[str] = []

        def need(kind: str, value: str | None, pool: set[str]) -> None:
            if value is not None and value not in pool:
                problems.append(f"unknown {kind} '{value}'")

        if len(set(crew_ids)) != len(crew_ids):
            problems.append("duplicate crew ids")
        if len(consumers) != len(self.power.consumers):
            problems.append("duplicate consumer ids")
        for cid in (
            self.power.heater_consumer,
            self.power.rover_charger_consumer,
            self.power.science_consumer,
            self.power.comms_consumer,
            self.life_support.oxygen_generator_consumer,
            self.life_support.co2_scrubber_consumer,
            self.life_support.water_recovery_consumer,
        ):
            need("consumer", cid, consumers)
        for c in self.power.consumers:
            need("component", c.component, components)
        for cid in (
            self.rover.component,
            self.degradation.battery_component,
            self.degradation.solar_component,
            self.degradation.heater_component,
            self.degradation.comms_component,
        ):
            need("component", cid, components)
        for ev in self.events:
            for eff in ev.effects:
                if isinstance(eff, DamageComponentEffect):
                    need("component", eff.component, components)
                if isinstance(eff, OpenOpportunityEffect):
                    need("opportunity", eff.opportunity, opportunities)
        if len({e.id for e in self.events}) != len(self.events):
            problems.append("duplicate event ids")
        phase_ids = [p.id for p in self.phases]
        if len(set(phase_ids)) != len(phase_ids):
            problems.append("duplicate phase ids")
        kinds = [p.kind for p in self.phases]
        if kinds.count("conclusion") != 1 or kinds.count("analysis") != 1:
            problems.append("exactly one conclusion and one analysis phase are required")
        if not self.phases or self.phases[0].kind != "simulated":
            problems.append("first phase must be simulated")
        last = self.outcomes[-1] if self.outcomes else None
        if last is None or not last.at_end or last.has_requirements():
            problems.append("the last outcome rule must be an unconditional at_end catch-all")
        if len({o.id for o in self.objectives}) != len(self.objectives):
            problems.append("duplicate objective ids")
        categories = {o.effective_category for o in self.objectives}
        for rule in self.outcomes:
            for cat in sorted(rule.category_refs() - categories):
                problems.append(
                    f"outcome rule {rule.id} references category '{cat}' with no objectives"
                )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def consumer(self, consumer_id: str) -> ConsumerSpec:
        for c in self.power.consumers:
            if c.id == consumer_id:
                return c
        raise KeyError(consumer_id)

    def component(self, component_id: str) -> ComponentSpec:
        for c in self.degradation.components:
            if c.id == component_id:
                return c
        raise KeyError(component_id)

    def outcome_rule(self, rule_id: str) -> OutcomeRule:
        for r in self.outcomes:
            if r.id == rule_id:
                return r
        raise KeyError(rule_id)

    def objective(self, objective_id: str) -> ObjectiveDefinition:
        for o in self.objectives:
            if o.id == objective_id:
                return o
        raise KeyError(objective_id)

    def opportunity(self, opportunity_id: str) -> ScienceOpportunitySpec:
        for o in self.science.opportunities:
            if o.id == opportunity_id:
                return o
        raise KeyError(opportunity_id)

    def all_conditions(self) -> list[Condition]:
        conds: list[Condition] = []
        for ev in self.events:
            if isinstance(ev.trigger, StateTrigger):
                conds.append(ev.trigger.condition)
        for ph in self.phases:
            if ph.advance_when is not None:
                conds.append(ph.advance_when)
        for ob in self.objectives:
            conds.extend(c for c in (ob.achieve_when, ob.fail_when) if c is not None)
        conds.extend(r.when for r in self.outcomes if r.when is not None)
        return conds
