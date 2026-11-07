"""Mission state — the single source of simulation truth.

Units are part of every field name or docstring. The state is a tree of Pydantic models so it
can be validated when reloaded from persistence, serialized canonically, and hashed.

The engine never mutates a state object it was given: public engine methods deep-copy first.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.canonical import sha256_hex
from app.simulation.domain.enums import (
    AlertSeverity,
    CrewLocation,
    CrewRole,
    MissionStatus,
    ObjectiveStatus,
    OpportunityStatus,
    ProvenanceKind,
    RoverStatus,
    SubsystemMode,
)

STATE_SCHEMA_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=False)


class Provenance(_Model):
    """Who/what set a value, and when (simulation tick)."""

    kind: ProvenanceKind
    ref: str
    tick: int


class EnvironmentState(_Model):
    solar_availability: float = Field(description="Fraction of rated insolation, 0..1")
    sink_temp_c: float = Field(description="Effective external radiative sink temperature, °C")
    radiation_dose_rate_msv_h: float = Field(description="Unshielded surface dose rate, mSv/h")
    earth_visible: bool = Field(description="Direct-to-Earth/relay link geometrically available")


class ConsumerState(_Model):
    id: str
    mode: SubsystemMode
    mode_set_by: Provenance
    demand_kw: float = 0.0
    allocated_kw: float = 0.0
    supply_ratio: float = Field(1.0, description="allocated / demand (1.0 when demand is 0)")


class PowerState(_Model):
    generation_kw: float = 0.0
    demand_kw: float = 0.0
    allocated_kw: float = 0.0
    unmet_kw: float = 0.0
    battery_charge_kwh: float
    battery_net_kw: float = Field(0.0, description="+ charging, - discharging (battery side)")
    dust_factor: float = Field(1.0, description="Array transmission after dust, 0..1")
    dust_set_by: Provenance
    consumers: dict[str, ConsumerState]


class ThermalState(_Model):
    habitat_temp_c: float
    setpoint_c: float
    setpoint_set_by: Provenance
    heat_loss_kw: float = 0.0
    internal_heat_kw: float = 0.0


class LifeSupportState(_Model):
    oxygen_kg: float
    co2_kg: float
    water_kg: float
    o2_generated_kg: float = Field(0.0, description="Generated during the last tick")
    o2_required_kg: float = Field(0.0, description="Crew consumption during the last tick")
    co2_removed_kg: float = 0.0
    water_recovery_efficiency: float = Field(0.0, description="Effective fraction recovered")
    water_recovered_kg: float = 0.0


class FoodState(_Model):
    food_kg: float
    ration_level: float = Field(1.0, description="Fraction of nominal daily ration")
    ration_set_by: Provenance


class CommsState(_Model):
    link_up: bool = True
    data_downlinked_mb: float = 0.0


class OpportunityState(_Model):
    id: str
    status: OpportunityStatus
    opened_tick: int
    closes_tick: int
    progress_ticks: float = 0.0
    opened_by: Provenance
    started_by: Provenance | None = None


class ScienceState(_Model):
    points: float = 0.0
    data_pending_mb: float = 0.0
    active_opportunity: str | None = None
    opportunities: dict[str, OpportunityState] = Field(default_factory=dict)


class CrewMemberState(_Model):
    id: str
    role: CrewRole
    health: float = Field(1.0, description="Abstract health index, 0 (incapacitated) .. 1")
    fatigue: float = Field(0.0, description="Abstract fatigue index, 0..1")
    dose_msv: float = 0.0
    location: CrewLocation = CrewLocation.HABITAT
    eva_remaining_ticks: int = 0
    eva_task_ref: str | None = Field(None, description="Decision id that started the EVA")


class RoverState(_Model):
    status: RoverStatus
    battery_kwh: float
    progress_ticks: int = 0
    target_opportunity: str | None = None
    transfer_active: bool = Field(False, description="Rover battery feeding habitat bus")
    status_set_by: Provenance


class ComponentState(_Model):
    id: str
    health: float = 1.0
    maintenance_remaining_ticks: int = 0
    fault_count: int = 0
    last_damage: Provenance | None = None


class ActiveModifier(_Model):
    event_id: str
    target: str
    op: str
    value: float
    start_tick: int
    end_tick: int = Field(description="Exclusive")


class AlertState(_Model):
    id: str
    severity: AlertSeverity
    metric: str
    raised_tick: int
    value: float


class ObjectiveState(_Model):
    id: str
    status: ObjectiveStatus = ObjectiveStatus.PENDING
    resolved_tick: int | None = None


class PhaseTransition(_Model):
    phase: str
    tick: int


class OutcomeState(_Model):
    code: str
    tick: int
    rule_id: str
    objectives_achieved: list[str]
    objectives_failed: list[str]


class MissionState(_Model):
    """Complete, serializable mission state at an instant (between ticks)."""

    schema_version: int = STATE_SCHEMA_VERSION
    scenario_id: str
    scenario_version: str
    seed: int
    tick: int = 0
    status: MissionStatus = MissionStatus.ACTIVE
    phase: str
    phase_history: list[PhaseTransition]
    decisions_applied: int = 0
    environment: EnvironmentState
    power: PowerState
    thermal: ThermalState
    life_support: LifeSupportState
    food: FoodState
    comms: CommsState
    science: ScienceState
    crew: list[CrewMemberState]
    rover: RoverState
    components: dict[str, ComponentState]
    modifiers: list[ActiveModifier] = Field(default_factory=list)
    alerts: dict[str, AlertState] = Field(default_factory=dict)
    objectives: dict[str, ObjectiveState] = Field(default_factory=dict)
    event_fire_counts: dict[str, int] = Field(default_factory=dict)
    cascade_edges_active: list[str] = Field(default_factory=list)
    outcome: OutcomeState | None = None

    def state_hash(self) -> str:
        """Deterministic content hash (canonical JSON, SHA-256)."""
        return sha256_hex(self.model_dump(mode="json"))

    def clone(self) -> MissionState:
        return self.model_copy(deep=True)
