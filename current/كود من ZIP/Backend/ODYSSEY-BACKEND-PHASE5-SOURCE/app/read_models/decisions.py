"""Available decisions: the backend decides what is legal.

Every decision a client can submit is an **option** with a stable id
``<decision_type>[:<arg>[:<arg>]]`` (``set_subsystem_mode:comms:eco``,
``start_science_activity:regolith_survey``, ``rover_command:traverse:far_crater_traverse``).
Parameterised options (thermostat setpoint, ration level) take ``parameters``.

* Availability and the machine-readable unavailability reason come from the engine's own
  validation, run on a private copy of the state (``SimulationEngine.validate_decision``).
* Science options are listed only once their window has opened (an unopened window is not
  known to the player). A command for an unopened window is refused exactly like one for a
  closed window (``opportunity_unavailable``).
* ``impact`` follows the Phase 3 measurement (docs/DECISION_IMPACT_MODEL.md): ``major`` for
  HIGH or MEDIUM decisions, ``local`` for LOCAL or REDUNDANT ones. Maintenance is LOCAL /
  CUMULATIVE by decision D24.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, ValidationError

from app.core.errors import DecisionRejected
from app.read_models.common import View
from app.simulation.domain.decisions import (
    DECISION_TYPES,
    CleanSolarArray,
    DecisionInput,
    RoverCommand,
    ScheduleMaintenance,
    SetCrewLocation,
    SetRationLevel,
    SetSubsystemMode,
    SetThermalSetpoint,
    StartScienceActivity,
    StopScienceActivity,
)
from app.simulation.domain.enums import CrewLocation, MissionStatus, SubsystemMode
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine

Impact = Literal["major", "local", "informational"]
OPTION_ID_PATTERN = r"^[a-z][a-z0-9_]*(:[a-z0-9_]{1,64}){0,2}$"
MODE_ORDER: tuple[str, ...] = ("off", "eco", "nominal", "boost")
ROVER_ACTIONS: tuple[str, ...] = ("traverse", "recall", "transfer_energy", "stow", "unstow")

# Phase 3 measurement (DECISION_IMPACT_MODEL.md), final verdict per option.
_MAJOR_MODES: dict[str, set[str]] = {
    "co2_scrubber": {"off", "eco", "nominal", "boost"},
    "oxygen_generation": {"off", "eco", "nominal", "boost"},
    "water_recovery": {"off", "eco", "nominal", "boost"},
    "comms": {"off"},
}
_MAJOR_TYPES = {"set_crew_location", "start_science_activity", "stop_science_activity"}
_MAJOR_ROVER = {"traverse", "transfer_energy", "stow", "recall"}


class ParameterView(View):
    name: str
    type: Literal["number"] = "number"
    min: float
    max: float
    unit: str
    current: float | None = None


class UnavailableView(View):
    reason: str
    message: str


class DecisionOptionView(View):
    option_id: str
    decision_type: str
    category: str
    impact: Impact
    available: bool
    unavailable: UnavailableView | None = None
    is_current_setting: bool = False
    affected_systems: list[str]
    parameters: list[ParameterView] = Field(default_factory=list)
    label_key: str
    required_capability: str | None = None


class AvailableDecisionsView(View):
    tick: int
    mission_active: bool
    options: list[DecisionOptionView]
    available_count: int
    tools: list[DecisionOptionView] = Field(
        default_factory=list,
        description="Informational tools (Future Lens, ORION). They never change mission "
        "state and are not submitted as decision commands.",
    )


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    option_id: str
    decision_type: str
    category: str
    decision: DecisionInput
    static_affected: tuple[str, ...]
    parameters: tuple[ParameterView, ...] = ()
    is_current_setting: bool = False


# ------------------------------------------------------------------------- option ids
def _inputs(decision: DecisionInput | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(decision, Mapping):
        return dict(decision)
    out: dict[str, Any] = decision.model_dump(mode="json")
    return out


def decision_to_option_id(decision: DecisionInput | Mapping[str, Any]) -> str:
    """The option id of a decision (typed or as recorded ``inputs``)."""
    d = _inputs(decision)
    t = str(d["type"])
    if t == "set_subsystem_mode":
        return f"{t}:{d['subsystem']}:{d['mode']}"
    if t == "schedule_maintenance":
        return f"{t}:{d['component']}"
    if t == "set_crew_location":
        return f"{t}:{d['location']}"
    if t == "start_science_activity":
        return f"{t}:{d['opportunity_id']}"
    if t == "rover_command":
        opp = d.get("opportunity_id")
        return f"{t}:{d['action']}:{opp}" if opp else f"{t}:{d['action']}"
    if t == "clean_solar_array":
        return f"{t}:{d['crew_id']}"
    return t


def decision_parameters(decision: DecisionInput | Mapping[str, Any]) -> dict[str, float]:
    """The ``parameters`` of a decision command (only parameterised options have any)."""
    d = _inputs(decision)
    if d["type"] == "set_thermal_setpoint":
        return {"target_c": float(d["target_c"])}
    if d["type"] == "set_ration_level":
        return {"level": float(d["level"])}
    return {}


def impact_of(option_id: str) -> Impact:
    parts = option_id.split(":")
    t = parts[0]
    if t == "set_subsystem_mode" and len(parts) == 3:
        return "major" if parts[2] in _MAJOR_MODES.get(parts[1], set()) else "local"
    if t == "rover_command" and len(parts) >= 2:
        return "major" if parts[1] in _MAJOR_ROVER else "local"
    return "major" if t in _MAJOR_TYPES else "local"


def _parameter_specs(
    engine: SimulationEngine, decision_type: str
) -> dict[str, tuple[float, float, str]]:
    sc = engine.scenario
    if decision_type == "set_thermal_setpoint":
        return {"target_c": (sc.thermal.setpoint_min_c, sc.thermal.setpoint_max_c, "°C")}
    if decision_type == "set_ration_level":
        return {"level": (sc.food.ration_min, 1.0, "fraction")}
    return {}


def _bad(reason: str, message: str) -> DecisionRejected:
    return DecisionRejected(message, code=reason)


def command_to_decision(
    engine: SimulationEngine,
    option_id: str,
    decision_type: str | None,
    parameters: Mapping[str, float],
) -> DecisionInput:
    """Map a decision command to an engine decision, or raise ``INVALID_DECISION``.

    Reasons: ``unknown_option`` (not an option of this scenario), ``option_type_mismatch``
    (``decision_type`` given and different), ``bad_parameters`` (missing, unexpected or out of
    range). Whether the decision is *possible now* is the engine's call."""
    sc = engine.scenario
    parts = option_id.split(":")
    t, args = parts[0], parts[1:]
    if t not in DECISION_TYPES:
        raise _bad("unknown_option", f"unknown option '{option_id}'")
    if decision_type is not None and decision_type != t:
        raise _bad("option_type_mismatch", f"option '{option_id}' is not a '{decision_type}'")
    specs = _parameter_specs(engine, t)
    if set(parameters) != set(specs):
        raise _bad(
            "bad_parameters",
            f"option '{option_id}' takes parameters {sorted(specs) or 'none'}",
        )
    for name, (lo, hi, _) in specs.items():
        value = parameters[name]
        if not lo <= value <= hi:
            raise _bad("bad_parameters", f"{name} must be within [{lo}, {hi}]")

    def unknown() -> DecisionRejected:
        return _bad("unknown_option", f"unknown option '{option_id}'")

    try:
        if t == "set_subsystem_mode":
            if len(args) != 2:
                raise unknown()
            consumer = next((c for c in sc.power.consumers if c.id == args[0]), None)
            if consumer is None or args[1] not in {m.value for m in consumer.mode_factors}:
                raise unknown()
            return SetSubsystemMode(subsystem=args[0], mode=SubsystemMode(args[1]))
        if args and t in ("set_thermal_setpoint", "set_ration_level", "stop_science_activity"):
            raise unknown()
        if t == "set_thermal_setpoint":
            return SetThermalSetpoint(target_c=float(parameters["target_c"]))
        if t == "set_ration_level":
            return SetRationLevel(level=float(parameters["level"]))
        if t == "stop_science_activity":
            return StopScienceActivity()
        if t == "schedule_maintenance":
            if len(args) != 1 or args[0] not in {c.id for c in sc.degradation.components}:
                raise unknown()
            return ScheduleMaintenance(component=args[0])
        if t == "set_crew_location":
            if len(args) != 1 or args[0] not in (CrewLocation.HABITAT, CrewLocation.SHELTER):
                raise unknown()
            return SetCrewLocation(location=CrewLocation(args[0]))
        if t == "start_science_activity":
            if len(args) != 1 or args[0] not in {o.id for o in sc.science.opportunities}:
                raise unknown()
            return StartScienceActivity(opportunity_id=args[0])
        if t == "rover_command":
            if not args or args[0] not in ROVER_ACTIONS:
                raise unknown()
            if args[0] == "traverse":
                if len(args) != 2 or args[1] not in {o.id for o in sc.science.opportunities}:
                    raise unknown()
                return RoverCommand(action="traverse", opportunity_id=args[1])
            if len(args) != 1:
                raise unknown()
            return RoverCommand(action=args[0])
        if t == "clean_solar_array":
            if len(args) != 1 or args[0] not in {c.id for c in sc.crew}:
                raise unknown()
            return CleanSolarArray(crew_id=args[0])
    except ValidationError as exc:
        raise _bad("bad_parameters", "invalid decision parameters") from exc
    raise unknown()  # pragma: no cover - every type handled above


# ------------------------------------------------------------------------- catalogue
_CATEGORIES = {
    "set_thermal_setpoint": "thermal",
    "set_ration_level": "life_support",
    "schedule_maintenance": "maintenance",
    "set_crew_location": "crew",
    "start_science_activity": "science",
    "stop_science_activity": "science",
    "rover_command": "rover",
    "clean_solar_array": "power",
}


def _catalogue(
    engine: SimulationEngine, state: MissionState, *, include_unopened: bool
) -> list[CatalogueEntry]:
    """Every option of the scenario in a stable order, with its static affected systems."""
    sc = engine.scenario
    out: list[CatalogueEntry] = []
    for spec in sc.power.consumers:
        modes = {m.value for m in spec.mode_factors}
        current = state.power.consumers[spec.id].mode.value
        for mode in MODE_ORDER:
            if mode not in modes:
                continue
            d = SetSubsystemMode(subsystem=spec.id, mode=SubsystemMode(mode))
            out.append(
                CatalogueEntry(
                    decision_to_option_id(d),
                    d.type,
                    spec.system,
                    d,
                    tuple(dict.fromkeys(("power", spec.system))),
                    is_current_setting=mode == current,
                )
            )
    th = sc.thermal
    d_set: DecisionInput = SetThermalSetpoint(target_c=state.thermal.setpoint_c)
    out.append(
        CatalogueEntry(
            "set_thermal_setpoint",
            "set_thermal_setpoint",
            "thermal",
            d_set,
            ("thermal", "power"),
            (
                ParameterView(
                    name="target_c",
                    min=th.setpoint_min_c,
                    max=th.setpoint_max_c,
                    unit="°C",
                    current=state.thermal.setpoint_c,
                ),
            ),
        )
    )
    d_ration: DecisionInput = SetRationLevel(level=state.food.ration_level)
    out.append(
        CatalogueEntry(
            "set_ration_level",
            "set_ration_level",
            "life_support",
            d_ration,
            ("food", "crew"),
            (
                ParameterView(
                    name="level",
                    min=sc.food.ration_min,
                    max=1.0,
                    unit="fraction",
                    current=state.food.ration_level,
                ),
            ),
        )
    )
    for comp in sc.degradation.components:
        d_m: DecisionInput = ScheduleMaintenance(component=comp.id)
        out.append(
            CatalogueEntry(
                decision_to_option_id(d_m), d_m.type, "maintenance", d_m, ("maintenance", comp.id)
            )
        )
    locations = {c.location for c in state.crew if c.health > 0 and c.location != CrewLocation.EVA}
    for loc in (CrewLocation.HABITAT, CrewLocation.SHELTER):
        d_l: DecisionInput = SetCrewLocation(location=loc)
        out.append(
            CatalogueEntry(
                decision_to_option_id(d_l),
                d_l.type,
                "crew",
                d_l,
                ("crew", "radiation"),
                is_current_setting=locations == {loc},
            )
        )
    opened = state.science.opportunities
    for opp in sc.science.opportunities:
        if opp.requires_rover or (opp.id not in opened and not include_unopened):
            continue
        d_s: DecisionInput = StartScienceActivity(opportunity_id=opp.id)
        out.append(
            CatalogueEntry(
                decision_to_option_id(d_s),
                d_s.type,
                "science",
                d_s,
                ("science", "power"),
                is_current_setting=state.science.active_opportunity == opp.id,
            )
        )
    d_stop: DecisionInput = StopScienceActivity()
    out.append(
        CatalogueEntry(
            "stop_science_activity", d_stop.type, "science", d_stop, ("science", "power")
        )
    )
    for opp in sc.science.opportunities:
        if not opp.requires_rover or (opp.id not in opened and not include_unopened):
            continue
        d_t: DecisionInput = RoverCommand(action="traverse", opportunity_id=opp.id)
        out.append(
            CatalogueEntry(
                decision_to_option_id(d_t), d_t.type, "rover", d_t, ("rover", "power", "science")
            )
        )
    for action in ROVER_ACTIONS[1:]:
        d_r: DecisionInput = RoverCommand(action=action)
        out.append(
            CatalogueEntry(
                decision_to_option_id(d_r), d_r.type, "rover", d_r, ("rover", "power", "science")
            )
        )
    for member in sc.crew:
        d_c: DecisionInput = CleanSolarArray(crew_id=member.id)
        out.append(
            CatalogueEntry(
                decision_to_option_id(d_c), d_c.type, "power", d_c, ("power", "crew", "radiation")
            )
        )
    return out


def informational_options(*, lens_enabled: bool, orion_enabled: bool) -> list[DecisionOptionView]:
    """Analysis tools offered next to decisions. They never change mission state. Both are
    always served (ORION degrades to its grounded mock without an AI provider)."""
    tools = []
    for option_id, enabled, capability in (
        ("tool:future_lens", lens_enabled, "future_lens"),
        ("tool:orion", orion_enabled, "orion"),
    ):
        tools.append(
            DecisionOptionView(
                option_id=option_id,
                decision_type="tool",
                category="analysis",
                impact="informational",
                available=enabled,
                unavailable=None
                if enabled
                else UnavailableView(reason="disabled", message="not enabled on this server"),
                affected_systems=[],
                label_key=f"decision.{option_id.replace(':', '.')}",
                required_capability=capability,
            )
        )
    return tools


def build_decision_options(engine: SimulationEngine, state: MissionState) -> AvailableDecisionsView:
    active = state.status != MissionStatus.CONCLUDED
    views: list[DecisionOptionView] = []
    for entry in _catalogue(engine, state, include_unopened=False):
        unavailable = None
        affected = list(entry.static_affected)
        try:
            result = engine.apply_decision(state, entry.decision, "validation")
            affected = list(result.affected_systems)
        except DecisionRejectedError as exc:
            unavailable = UnavailableView(reason=exc.code, message=exc.message)
        views.append(
            DecisionOptionView(
                option_id=entry.option_id,
                decision_type=entry.decision_type,
                category=entry.category,
                impact=impact_of(entry.option_id),
                available=unavailable is None,
                unavailable=unavailable,
                is_current_setting=entry.is_current_setting,
                affected_systems=affected,
                parameters=list(entry.parameters),
                label_key=f"decision.{entry.decision_type}",
            )
        )
    return AvailableDecisionsView(
        tick=state.tick,
        mission_active=active,
        options=views,
        available_count=sum(1 for v in views if v.available),
        tools=informational_options(lens_enabled=True, orion_enabled=True),
    )
