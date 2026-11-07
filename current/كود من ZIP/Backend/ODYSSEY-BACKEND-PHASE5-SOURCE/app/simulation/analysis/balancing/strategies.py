"""Deterministic scripted player strategies: synthetic probes for balancing analysis.

These are **not** models of real players. Each one is a fixed, documented heuristic that
pushes the simulation in one direction so the Balancing Lab can measure what the scenario
rewards and punishes.

Fairness rule: a strategy may only use what a player could observe at the current tick — the
mission state, active alerts, open opportunities and the scenario's published limits (mode
names, setpoint range, mission length). It never reads future scenario events, other seeds'
outcomes or the RNG.

Every strategy instance is created per mission (``make_strategy``) so its memory never leaks
between runs. Thresholds below are *probe parameters*, not balancing decisions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.enums import (
    CrewLocation,
    CrewRole,
    OpportunityStatus,
    RoverStatus,
    SubsystemMode,
)
from app.simulation.domain.state import MissionState
from app.simulation.engine import rng
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine

Raw = dict[str, Any]

# Elevated radiation as a player sees it: the dose-rate reading, not the event schedule.
RADIATION_SHELTER_MSV_H = 0.3
# Solar availability below which a planning strategy starts preparing for the night.
DUSK_SOLAR_AVAILABILITY = 0.35
# Components ordered by how directly they keep the crew alive.
CRITICAL_COMPONENTS = (
    "co2_scrubber",
    "oxygen_generator",
    "water_processor",
    "heater",
    "battery",
    "solar_array",
    "radio",
    "rover",
)


@dataclass(frozen=True, slots=True)
class Observation:
    """What a strategy may look at (read-only by convention; the engine copies on apply)."""

    engine: SimulationEngine
    state: MissionState
    mission_seed: int

    @property
    def tick(self) -> int:
        return self.state.tick

    def metric(self, name: str) -> float:
        return self.engine.metrics.value(name, self.state)

    def alert(self, alert_id: str) -> bool:
        return alert_id in self.state.alerts

    @property
    def soc(self) -> float:
        return self.metric("power.battery_soc")

    def mode(self, subsystem: str) -> SubsystemMode:
        return self.state.power.consumers[subsystem].mode

    def radiation_high(self) -> bool:
        """Dose rate above the probe threshold, or any radiation alert the scenario raises."""
        return (
            self.state.environment.radiation_dose_rate_msv_h > RADIATION_SHELTER_MSV_H
            or self.alert("radiation_above_background")
            or self.alert("radiation_elevated")
        )

    def dose_budget_pressure(self) -> int:
        """0 = fine, 1 = projected dose close to the limit, 2 = projected to exceed it."""
        if self.alert("dose_budget_exceeded"):
            return 2
        return 1 if self.alert("dose_budget_low") else 0

    def dusk(self) -> bool:
        """The published premise of the mission: the Sun is setting (observed availability)."""
        return self.state.environment.solar_availability < DUSK_SOLAR_AVAILABILITY

    def night(self) -> bool:
        return self.state.environment.solar_availability <= 0.0

    def habitat_science_active(self) -> bool:
        active = self.state.science.active_opportunity
        return active is not None and not self.engine.scenario.opportunity(active).requires_rover

    def sheltered(self) -> bool:
        """Every active crew member who can move (not on EVA) is in the shelter."""
        movable = [c for c in self.state.crew if c.health > 0 and c.location != CrewLocation.EVA]
        return bool(movable) and all(c.location == CrewLocation.SHELTER for c in movable)

    def anyone_sheltered(self) -> bool:
        return any(c.location == CrewLocation.SHELTER for c in self.state.crew)

    def eva_active(self) -> bool:
        return any(c.location == CrewLocation.EVA for c in self.state.crew)

    def open_opportunities(self, *, rover: bool) -> list[str]:
        sc = self.engine.scenario
        return sorted(
            o.id
            for o in self.state.science.opportunities.values()
            if o.status == OpportunityStatus.OPEN and sc.opportunity(o.id).requires_rover == rover
        )

    def remaining_days(self) -> float:
        sc = self.engine.scenario
        return max(0.0, (sc.time.max_ticks - self.tick) * sc.time.tick_hours / 24.0)

    def rover_battery_fraction(self) -> float:
        return self.state.rover.battery_kwh / self.engine.scenario.rover.battery_capacity_kwh

    def any_maintenance(self) -> bool:
        return any(c.maintenance_remaining_ticks > 0 for c in self.state.components.values())

    def crew_member(self, role: CrewRole) -> str | None:
        healthy = [c for c in self.state.crew if c.health > 0.5 and c.location != CrewLocation.EVA]
        preferred = [c for c in healthy if c.role == role]
        pick = preferred or healthy
        return pick[0].id if pick else None


# ------------------------------------------------------------------------------ helpers
def set_mode(obs: Observation, subsystem: str, mode: SubsystemMode | str) -> list[Raw]:
    target = SubsystemMode(mode)
    if obs.mode(subsystem) == target:
        return []
    if target not in obs.engine.scenario.consumer(subsystem).mode_factors:
        return []
    return [{"type": "set_subsystem_mode", "subsystem": subsystem, "mode": target.value}]


def set_setpoint(obs: Observation, target_c: float) -> list[Raw]:
    th = obs.engine.scenario.thermal
    target = min(th.setpoint_max_c, max(th.setpoint_min_c, target_c))
    if abs(obs.state.thermal.setpoint_c - target) < 1e-9:
        return []
    return [{"type": "set_thermal_setpoint", "target_c": target}]


def set_ration(obs: Observation, level: float) -> list[Raw]:
    level = round(max(obs.engine.scenario.food.ration_min, min(1.0, level)), 2)
    if abs(obs.state.food.ration_level - level) < 1e-9:
        return []
    return [{"type": "set_ration_level", "level": level}]


def shelter_policy(obs: Observation, *, budget_aware: bool = False) -> list[Raw]:
    """Shelter while the measured dose rate is high; return when it drops.

    ``budget_aware``: also shelter when the projected mission dose is over the limit, or close
    to it while nobody needs to work in the habitat laboratory.
    """
    want = obs.radiation_high()
    if budget_aware and not want:
        pressure = obs.dose_budget_pressure()
        want = pressure == 2 or (pressure == 1 and not obs.habitat_science_active())
    if want and not obs.sheltered():
        # Re-issued after an EVA ends mid-storm: the returning member is not moved by the
        # first order (the engine skips crew on EVA) and comes back to the habitat.
        return [{"type": "set_crew_location", "location": "shelter"}]
    if not want and obs.anyone_sheltered():
        return [{"type": "set_crew_location", "location": "habitat"}]
    return []


def night_power_policy(obs: Observation, *, strict: bool) -> list[Raw]:
    """Prepare for the night once the Sun is low: shed what can wait, keep life support.

    Non-strict (balanced): eco habitat core and water recovery, comms eco once data is sent,
    18 °C setpoint, oxygen generation eco while > 4 days of oxygen remain, rover energy moved to
    the habitat at night. Strict (survival-first): additionally comms off when no data is
    waiting, 16 °C setpoint and oxygen generation off while > 3 days remain.
    """
    if not obs.dusk():
        return []
    out = set_mode(obs, "habitat_core", "eco")
    if obs.metric("life_support.water_days") > 5.0:
        out += set_mode(obs, "water_recovery", "eco")
    pending = obs.state.science.data_pending_mb > 0
    rover = obs.state.rover
    rover_out = rover.status in (RoverStatus.TRAVERSING, RoverStatus.RETURNING)
    if strict and not pending and not rover_out:
        out += set_mode(obs, "comms", "off")
    elif not pending:
        out += set_mode(obs, "comms", "eco")
    target = 16.0 if strict else 18.0
    out += set_setpoint(obs, target - 1.0 if obs.soc < 0.2 else target)
    o2_days = obs.metric("life_support.oxygen_days")
    if strict and o2_days > 3.0:
        out += set_mode(obs, "oxygen_generation", "off")
    elif o2_days > 4.0:
        out += set_mode(obs, "oxygen_generation", "eco")
    if rover.status == RoverStatus.DOCKED and obs.state.science.active_opportunity is None:
        out += set_mode(obs, "rover_charger", "off")
        if obs.night() and rover.battery_kwh > 1.0 and not rover.transfer_active:
            out.append({"type": "rover_command", "action": "transfer_energy"})
    return out


def ration_policy(obs: Observation, margin: float = 1.05) -> list[Raw]:
    """Stretch food so it lasts to the scheduled end of the mission (with a margin)."""
    need = obs.remaining_days() * margin
    have = obs.metric("food.food_days")
    if need <= 0 or have >= need:
        return (
            set_ration(obs, 1.0) if obs.state.food.ration_level < 1.0 and have > need * 1.2 else []
        )
    return set_ration(obs, have / need)


def maintenance_policy(obs: Observation, threshold: float, min_soc: float) -> list[Raw]:
    if obs.any_maintenance() or obs.soc < min_soc:
        return []
    for comp in CRITICAL_COMPONENTS:
        if comp in obs.state.components and obs.state.components[comp].health < threshold:
            return [{"type": "schedule_maintenance", "component": comp}]
    return []


def cleaning_policy(obs: Observation, dust_below: float) -> list[Raw]:
    if obs.state.power.dust_factor >= dust_below or obs.radiation_high() or obs.eva_active():
        return []
    crew_id = obs.crew_member(CrewRole.POWER_ENGINEER)
    return [{"type": "clean_solar_array", "crew_id": crew_id}] if crew_id else []


def life_support_policy(obs: Observation, *, keep_night_modes: bool = False) -> list[Raw]:
    """Scrubber boost on high CO2; O2 generation boost when oxygen is low, else nominal.

    ``keep_night_modes``: leave a reduced oxygen-generation mode set by the night policy alone
    unless oxygen is low.
    """
    out: list[Raw] = []
    out += set_mode(obs, "co2_scrubber", "boost" if obs.alert("co2_high") else "nominal")
    o2_low = (
        obs.metric("life_support.oxygen_days") < 3.0 and obs.metric("life_support.water_days") > 2.0
    )
    if o2_low:
        out += set_mode(obs, "oxygen_generation", "boost")
    elif not (keep_night_modes and obs.dusk()):
        out += set_mode(obs, "oxygen_generation", "nominal")
    return out


def start_habitat_science(obs: Observation, mode: str = "nominal") -> list[Raw]:
    out: list[Raw] = []
    if obs.state.science.active_opportunity is None:
        opps = obs.open_opportunities(rover=False)
        if opps:
            out.append({"type": "start_science_activity", "opportunity_id": opps[0]})
    if obs.state.science.active_opportunity is not None or out:
        out += set_mode(obs, "science_payload", mode)
    return out


def rover_traverse(obs: Observation, min_rover_fraction: float) -> list[Raw]:
    rv = obs.state.rover
    if rv.status != RoverStatus.DOCKED or not obs.state.comms.link_up:
        return []
    if obs.rover_battery_fraction() < min_rover_fraction:
        return []
    opps = obs.open_opportunities(rover=True)
    if not opps:
        return []
    return [{"type": "rover_command", "action": "traverse", "opportunity_id": opps[0]}]


# ------------------------------------------------------------------------------ strategies
@dataclass
class Strategy:
    """Base: subclasses implement ``decide``. ``memory`` is per-mission scratch space."""

    seed: int = 0
    memory: dict[str, Any] = field(default_factory=dict)
    name: str = "base"
    description: str = ""

    def decide(self, obs: Observation) -> list[Raw]:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class Passive(Strategy):
    name: str = "passive"
    description: str = "Control group: never makes a decision."

    def decide(self, obs: Observation) -> list[Raw]:
        return []


@dataclass
class SurvivalFirst(Strategy):
    name: str = "survival_first"
    description: str = (
        "Crew safety and reserves first: shelters on any radiation alert and when the dose "
        "budget runs low, strict night power plan, maintenance, array cleaning; habitat science "
        "only in eco mode with a full battery and no warnings; never sends the rover."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        out = shelter_policy(obs, budget_aware=True)
        out += life_support_policy(obs, keep_night_modes=True) + ration_policy(obs)
        soc = obs.soc
        warnings = any(a.severity in ("warning", "critical") for a in obs.state.alerts.values())
        calm = soc >= 0.8 and not warnings and not obs.radiation_high() and not obs.dusk()
        if calm:
            out += start_habitat_science(obs, mode="eco")
        elif obs.habitat_science_active() and (soc < 0.5 or obs.radiation_high()):
            out.append({"type": "stop_science_activity"})
        if soc < 0.5:
            out += set_mode(obs, "rover_charger", "off") + set_mode(obs, "comms", "eco")
        if soc < 0.3 and not obs.dusk():
            out += set_setpoint(obs, 16.0) + set_mode(obs, "habitat_core", "eco")
        out += night_power_policy(obs, strict=True)
        if soc > 0.7 and not obs.dusk():
            out += set_mode(obs, "comms", "nominal") + set_mode(obs, "habitat_core", "nominal")
            out += set_setpoint(obs, 21.0)
        out += maintenance_policy(obs, threshold=0.6, min_soc=0.25)
        out += cleaning_policy(obs, dust_below=0.9)
        return out


@dataclass
class ScienceFirst(Strategy):
    name: str = "science_first"
    description: str = (
        "Maximise science: every window, boosted payload, rover traverses, "
        "comms kept up for downlink; no sheltering or power saving."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        out = start_habitat_science(obs, mode="boost")
        out += rover_traverse(obs, min_rover_fraction=0.0)
        out += set_mode(obs, "comms", "nominal")
        return out


@dataclass
class Balanced(Strategy):
    name: str = "balanced"
    description: str = (
        "Compromise: shelters on radiation alerts and a low dose budget when not working, "
        "science when power allows (rover traverse only with a healthy battery), tiered load "
        "shedding, a night power plan once the Sun is low, maintenance, cleaning, rationing."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        out = shelter_policy(obs, budget_aware=True)
        out += life_support_policy(obs, keep_night_modes=True) + ration_policy(obs)
        soc = obs.soc
        if not obs.radiation_high() and soc > 0.35:
            out += start_habitat_science(obs)
        elif soc < 0.2 and obs.state.science.active_opportunity is not None:
            out.append({"type": "stop_science_activity"})
        if soc > 0.6:
            out += rover_traverse(obs, min_rover_fraction=0.75)
        if soc < 0.35:
            out += set_mode(obs, "comms", "eco")
            if obs.state.rover.status == RoverStatus.DOCKED:
                out += set_mode(obs, "rover_charger", "off")
        if soc < 0.2 and not obs.dusk():
            out += set_setpoint(obs, 17.0) + set_mode(obs, "habitat_core", "eco")
        if (
            soc < 0.12
            and obs.state.rover.status == RoverStatus.DOCKED
            and obs.state.rover.battery_kwh > 1.0
            and not obs.state.rover.transfer_active
        ):
            out.append({"type": "rover_command", "action": "transfer_energy"})
        out += night_power_policy(obs, strict=False)
        if soc > 0.55 and not obs.dusk():
            out += set_mode(obs, "comms", "nominal") + set_mode(obs, "habitat_core", "nominal")
            out += set_setpoint(obs, 21.0)
            if not obs.state.rover.transfer_active:
                out += set_mode(obs, "rover_charger", "nominal")
        out += maintenance_policy(obs, threshold=0.5, min_soc=0.3)
        out += cleaning_policy(obs, dust_below=0.88)
        return out


@dataclass
class PowerConservative(Strategy):
    name: str = "power_conservative"
    description: str = (
        "Aggressive energy saving from tick 0: eco loads, low setpoint, charger "
        "off, early rover energy transfer; science only with a full battery; the strict night "
        "plan at dusk (with the shared life-support safety reaction)."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        # Phase 3: v0.1.0 numbers let this probe save only by day (when the battery is full and
        # surplus is curtailed); under v0.2.0 that misrepresented "aggressive saving", so it now
        # also saves where energy is scarce, at dusk and night.
        out = shelter_policy(obs) + life_support_policy(obs, keep_night_modes=True)
        out += set_mode(obs, "habitat_core", "eco")
        if not obs.dusk():  # after dusk the night plan owns comms and the setpoint
            out += set_mode(obs, "comms", "eco") + set_setpoint(obs, 16.0)
        rover = obs.state.rover
        if rover.status == RoverStatus.DOCKED:
            out += set_mode(obs, "rover_charger", "off")
            if obs.soc < 0.5 and rover.battery_kwh > 1.0 and not rover.transfer_active:
                out.append({"type": "rover_command", "action": "transfer_energy"})
        if obs.soc > 0.85 and not obs.radiation_high():
            out += start_habitat_science(obs, mode="eco")
        elif obs.soc < 0.6 and obs.state.science.active_opportunity is not None:
            out.append({"type": "stop_science_activity"})
        out += cleaning_policy(obs, dust_below=0.92)
        out += night_power_policy(obs, strict=True)
        return out


@dataclass
class HighRisk(Strategy):
    name: str = "high_risk"
    description: str = (
        "Mission progress over margins: boosted science, traverses regardless "
        "of battery, no shelter, cold habitat, short rations, maintenance only "
        "when nearly broken."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        out = start_habitat_science(obs, mode="boost")
        out += rover_traverse(obs, min_rover_fraction=0.0)
        out += set_setpoint(obs, 12.0) + set_ration(obs, 0.7)
        out += maintenance_policy(obs, threshold=0.3, min_soc=0.0)
        return out


@dataclass
class NaiveBeginner(Strategy):
    name: str = "naive_beginner"
    description: str = (
        "Reacts to alerts one at a time with the first obvious fix (including "
        "counter-productive ones such as maxing the thermostat when cold); "
        "starts science whenever offered; inconsistent attention (notices alerts on a given "
        "tick with probability 0.6, seeded)."
    )
    attention: float = 0.6

    def decide(self, obs: Observation) -> list[Raw]:
        out: list[Raw] = []
        if obs.state.science.active_opportunity is None and obs.open_opportunities(rover=False):
            out.append(
                {
                    "type": "start_science_activity",
                    "opportunity_id": obs.open_opportunities(rover=False)[0],
                }
            )
        if not rng.bernoulli(self.seed, "strategy:naive:attention", obs.tick, self.attention):
            return out
        if obs.alert("battery_low") and obs.state.science.active_opportunity is not None:
            out.append({"type": "stop_science_activity"})
        if obs.alert("co2_high"):
            out += set_mode(obs, "co2_scrubber", "boost")
        if obs.alert("habitat_cold"):
            out += set_setpoint(obs, obs.engine.scenario.thermal.setpoint_max_c)
        if obs.alert("radiation_elevated") and not obs.sheltered():
            out.append({"type": "set_crew_location", "location": "shelter"})
        if not obs.alert("radiation_elevated") and obs.anyone_sheltered():
            out.append({"type": "set_crew_location", "location": "habitat"})
        return out


@dataclass
class RandomValid(Strategy):
    """Random valid actions; reproducible from the strategy seed (counter-based RNG)."""

    name: str = "random_valid"
    description: str = (
        "Each tick, with probability 0.1, one action drawn uniformly from the "
        "currently valid actions (seeded, reproducible)."
    )
    action_probability: float = 0.1

    def _candidates(self, obs: Observation) -> list[Raw]:
        sc = obs.engine.scenario
        cands: list[Raw] = []
        for spec in sc.power.consumers:
            for mode in sorted(spec.mode_factors):
                cands += set_mode(obs, spec.id, mode)
        for target in (12.0, 15.0, 18.0, 21.0, 24.0):
            cands += set_setpoint(obs, target)
        for level in (0.5, 0.75, 1.0):
            cands += set_ration(obs, level)
        cands += [
            {"type": "schedule_maintenance", "component": c.id} for c in sc.degradation.components
        ]
        cands += [{"type": "set_crew_location", "location": loc} for loc in ("habitat", "shelter")]
        cands += [
            {"type": "start_science_activity", "opportunity_id": o}
            for o in obs.open_opportunities(rover=False)
        ]
        cands.append({"type": "stop_science_activity"})
        cands += [
            {"type": "rover_command", "action": a, "opportunity_id": o}
            for o in obs.open_opportunities(rover=True)
            for a in ("traverse",)
        ]
        cands += [
            {"type": "rover_command", "action": a}
            for a in ("recall", "transfer_energy", "stow", "unstow")
        ]
        cands += [{"type": "clean_solar_array", "crew_id": c.id} for c in obs.state.crew]
        return cands

    def decide(self, obs: Observation) -> list[Raw]:
        if not rng.bernoulli(
            self.seed, "strategy:random_valid:act", obs.tick, self.action_probability
        ):
            return []
        cands = self._candidates(obs)
        for attempt in range(6):
            pick = int(
                rng.uniform(self.seed, "strategy:random_valid:pick", obs.tick, attempt) * len(cands)
            )
            raw = cands[pick]
            try:
                obs.engine.validate_decision(obs.state, parse_decision(raw))
            except DecisionRejectedError:
                continue
            return [raw]
        return []


@dataclass
class ReserveKeeper(Strategy):
    """Existence probe: can *any* play end the mission with reserves? (Not a player model.)"""

    name: str = "reserve_keeper"
    description: str = (
        "Existence probe for the reserves objective: Balanced by day, then a "
        "strict night mode once generation falls (O2 generation off while "
        "reserves last, eco life support, comms/science/charger off, rover energy "
        "moved to the habitat, minimum safe setpoint)."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        dark = obs.metric("power.generation_ratio") < 0.35 and obs.tick > 100
        if not dark:
            return Balanced(seed=self.seed, memory=self.memory).decide(obs)
        out = shelter_policy(obs) + ration_policy(obs)
        if obs.state.science.active_opportunity is not None:
            out.append({"type": "stop_science_activity"})
        out += set_mode(
            obs,
            "oxygen_generation",
            "off" if obs.metric("life_support.oxygen_days") > 2.0 else "eco",
        )
        out += set_mode(obs, "co2_scrubber", "nominal" if obs.alert("co2_high") else "eco")
        out += set_mode(obs, "water_recovery", "eco")
        out += set_mode(obs, "comms", "off") + set_mode(obs, "science_payload", "off")
        out += set_mode(obs, "habitat_core", "eco") + set_setpoint(obs, 15.5)
        rover = obs.state.rover
        if rover.status == RoverStatus.DOCKED:
            out += set_mode(obs, "rover_charger", "off")
            if rover.battery_kwh > 1.0 and not rover.transfer_active:
                out.append({"type": "rover_command", "action": "transfer_energy"})
        return out


@dataclass
class Expert(Strategy):
    """Existence probe: can deliberate play reach *exceptional* success? (Not a player model.)"""

    name: str = "expert"
    description: str = (
        "Existence probe for exceptional success: budget-aware sheltering, boosted habitat "
        "science while power is plentiful, oxygen generation eco above 6.5 days of oxygen and "
        "nominal below 5.5 (saves water and power), the far-crater traverse with comms kept up "
        "until its data is sent, then the strict night plan with oxygen generation off only "
        "above 4 days of oxygen, maintenance and cleaning."
    )

    def decide(self, obs: Observation) -> list[Raw]:
        out = shelter_policy(obs, budget_aware=True) + ration_policy(obs)
        out += set_mode(obs, "co2_scrubber", "boost" if obs.alert("co2_high") else "nominal")
        o2_days = obs.metric("life_support.oxygen_days")
        o2_mode = obs.mode("oxygen_generation")
        if o2_days < 3.0:
            out += set_mode(obs, "oxygen_generation", "boost")
        elif obs.dusk():
            pass  # the night plan below manages oxygen generation
        elif o2_days > 6.5 and o2_mode != SubsystemMode.ECO:
            out += set_mode(obs, "oxygen_generation", "eco")
        elif o2_days < 5.5 and o2_mode != SubsystemMode.NOMINAL:
            out += set_mode(obs, "oxygen_generation", "nominal")
        if not obs.radiation_high() and obs.soc > 0.5 and not obs.dusk():
            out += start_habitat_science(obs, mode="boost")
        elif obs.habitat_science_active() and obs.soc < 0.3:
            out.append({"type": "stop_science_activity"})
        rover = obs.state.rover
        survey_open = bool(obs.open_opportunities(rover=True))
        rover_busy = rover.status in (RoverStatus.TRAVERSING, RoverStatus.RETURNING)
        if obs.soc > 0.7:
            out += rover_traverse(obs, min_rover_fraction=0.75)
        keep_link = survey_open or rover_busy or obs.state.science.data_pending_mb > 0
        if keep_link:
            out += set_mode(obs, "comms", "nominal")
        managed = {"oxygen_generation"} | ({"comms"} if keep_link else set())
        out += [
            d for d in night_power_policy(obs, strict=True) if d.get("subsystem") not in managed
        ]
        if obs.dusk() and o2_days >= 3.0:
            # Oxygen off at night only while a margin above the 3-day reserve remains.
            out += set_mode(obs, "oxygen_generation", "off" if o2_days > 4.0 else "eco")
        out += maintenance_policy(obs, threshold=0.6, min_soc=0.3)
        out += cleaning_policy(obs, dust_below=0.9)
        return out


@dataclass
class AlwaysShelter(Strategy):
    """Probe: does sheltering for the whole mission cost anything besides habitat science?"""

    name: str = "always_shelter"
    description: str = "Probe: crew stays in the radiation shelter from tick 0; nothing else."

    def decide(self, obs: Observation) -> list[Raw]:
        return [] if obs.sheltered() else [{"type": "set_crew_location", "location": "shelter"}]


StrategyFactory = Callable[[int], Strategy]

STRATEGIES: dict[str, StrategyFactory] = {
    "passive": lambda seed: Passive(seed=seed),
    "survival_first": lambda seed: SurvivalFirst(seed=seed),
    "science_first": lambda seed: ScienceFirst(seed=seed),
    "balanced": lambda seed: Balanced(seed=seed),
    "power_conservative": lambda seed: PowerConservative(seed=seed),
    "high_risk": lambda seed: HighRisk(seed=seed),
    "naive_beginner": lambda seed: NaiveBeginner(seed=seed),
    "random_valid": lambda seed: RandomValid(seed=seed),
}
# The seven synthetic player probes from the Phase 2 brief, plus the passive control group.
PROBE_STRATEGIES = tuple(STRATEGIES)
# Diagnostic probes: answer "is X possible / free?" — not part of default sweeps.
DIAGNOSTIC_PROBES: dict[str, StrategyFactory] = {
    "reserve_keeper": lambda seed: ReserveKeeper(seed=seed),
    "always_shelter": lambda seed: AlwaysShelter(seed=seed),
    "expert": lambda seed: Expert(seed=seed),
}


def make_strategy(name: str, mission_seed: int) -> Strategy:
    """New strategy instance for one mission. RANDOM_VALID's seed is derived from the mission
    seed so its choices are reproducible but independent of the engine's random draws."""
    key = name.strip().lower().replace("-", "_")
    registry = {**STRATEGIES, **DIAGNOSTIC_PROBES}
    if key not in registry:
        raise KeyError(f"unknown strategy {name!r}; choose from {sorted(registry)}")
    return registry[key](rng.derive_seed(mission_seed, f"strategy:{key}"))
