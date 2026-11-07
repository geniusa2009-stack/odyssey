"""Player decision inputs.

Each decision is a validated, typed command. The set of decision *types* is the engine's
technical control surface; which of them the product exposes to players (and when) is a product
decision recorded in ``docs/USER_DECISIONS_REQUIRED.md``.

Range limits that are balancing parameters (e.g. allowed thermostat range) are validated by the
engine against the scenario, not hard-coded here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.simulation.domain.enums import CrewLocation, SubsystemMode

_ID = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SetSubsystemMode(_Decision):
    type: Literal["set_subsystem_mode"] = "set_subsystem_mode"
    subsystem: _ID
    mode: SubsystemMode


class SetThermalSetpoint(_Decision):
    type: Literal["set_thermal_setpoint"] = "set_thermal_setpoint"
    target_c: float = Field(ge=-50, le=50)


class SetRationLevel(_Decision):
    type: Literal["set_ration_level"] = "set_ration_level"
    level: float = Field(gt=0, le=1.0)


class ScheduleMaintenance(_Decision):
    type: Literal["schedule_maintenance"] = "schedule_maintenance"
    component: _ID


class SetCrewLocation(_Decision):
    """Move the whole crew between habitat and radiation shelter."""

    type: Literal["set_crew_location"] = "set_crew_location"
    location: Literal[CrewLocation.HABITAT, CrewLocation.SHELTER]


class StartScienceActivity(_Decision):
    type: Literal["start_science_activity"] = "start_science_activity"
    opportunity_id: _ID


class StopScienceActivity(_Decision):
    type: Literal["stop_science_activity"] = "stop_science_activity"


class RoverCommand(_Decision):
    type: Literal["rover_command"] = "rover_command"
    action: Literal["traverse", "recall", "transfer_energy", "stow", "unstow"]
    opportunity_id: _ID | None = None


class CleanSolarArray(_Decision):
    """Send one crew member on EVA to clean the array (dust removal, radiation exposure)."""

    type: Literal["clean_solar_array"] = "clean_solar_array"
    crew_id: _ID


DecisionInput = Annotated[
    SetSubsystemMode
    | SetThermalSetpoint
    | SetRationLevel
    | ScheduleMaintenance
    | SetCrewLocation
    | StartScienceActivity
    | StopScienceActivity
    | RoverCommand
    | CleanSolarArray,
    Field(discriminator="type"),
]

DECISION_ADAPTER: TypeAdapter[DecisionInput] = TypeAdapter(DecisionInput)

DECISION_TYPES: tuple[str, ...] = (
    "set_subsystem_mode",
    "set_thermal_setpoint",
    "set_ration_level",
    "schedule_maintenance",
    "set_crew_location",
    "start_science_activity",
    "stop_science_activity",
    "rover_command",
    "clean_solar_array",
)


def parse_decision(raw: object) -> DecisionInput:
    """Validate an untrusted mapping into a typed decision."""
    return DECISION_ADAPTER.validate_python(raw)


def decision_payload(decision: DecisionInput) -> dict[str, object]:
    return decision.model_dump(mode="json")
