"""Simulation state invariants.

``check_state`` returns every violated invariant (empty list = valid). It is a pure read of the
state and is used by tests, the property/fuzz suite and the Balancing Lab (``--strict``). The
engine itself does not call it on the hot path; enforcement is by test, so production runs pay
nothing for it.

Invariants (``previous`` = the state one step earlier, when given):

* every number in the state is finite (no NaN / ±inf)
* battery 0 ≤ E ≤ capacity(health); rover 0 ≤ E ≤ rover capacity
* oxygen 0 ≤ O₂ ≤ storage capacity; CO₂, water, food ≥ 0
* dust_floor ≤ dust ≤ 1; ration_min ≤ ration ≤ 1; setpoint within the scenario range
* per consumer: demand ≥ 0, 0 ≤ allocated ≤ demand, 0 ≤ supply ≤ 1; unmet ≥ 0
* crew health, fatigue ∈ [0, 1]; dose ≥ 0; EVA flag ⇔ EVA ticks remaining
* component health ∈ [0, 1]; maintenance ticks ≥ 0
* science points, pending data ≥ 0; at most one active opportunity, and it is ACTIVE
* tick ≤ max_ticks; phase is a scenario phase; phase history is ordered
* alerts ⊆ alert rules; event fire counts ≤ max_fires; no expired modifier remains
* concluded ⇔ an outcome is recorded
* with ``previous``: tick advanced by exactly 1; doses, science points, downlinked data,
  decision count and event fire counts never decrease; resolved objectives stay resolved;
  the phase never moves backwards
"""

from __future__ import annotations

import math
from typing import Any

from app.simulation.domain.enums import (
    CrewLocation,
    MissionStatus,
    ObjectiveStatus,
    OpportunityStatus,
)
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

EPS = 1e-6


class InvariantViolationError(AssertionError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems[:10]))
        self.problems = problems


def _non_finite(value: Any, path: str, out: list[str]) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            out.append(f"{path} is not finite ({value})")
    elif isinstance(value, dict):
        for k, v in value.items():
            _non_finite(v, f"{path}.{k}", out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _non_finite(v, f"{path}[{i}]", out)


def _within(out: list[str], name: str, value: float, lo: float, hi: float) -> None:
    if value < lo - EPS or value > hi + EPS:
        out.append(f"{name}={value!r} outside [{lo}, {hi}]")


def check_state(
    engine: SimulationEngine, s: MissionState, previous: MissionState | None = None
) -> list[str]:
    sc = engine.scenario
    out: list[str] = []
    _non_finite(s.model_dump(mode="python"), "state", out)
    if out:
        return out  # further checks would compare against NaN

    cap = sc.power.battery.capacity_kwh * max(
        0.05, s.components[sc.degradation.battery_component].health
    )
    _within(out, "power.battery_charge_kwh", s.power.battery_charge_kwh, 0.0, cap)
    _within(out, "rover.battery_kwh", s.rover.battery_kwh, 0.0, sc.rover.battery_capacity_kwh)
    _within(
        out,
        "life_support.oxygen_kg",
        s.life_support.oxygen_kg,
        0.0,
        max(sc.life_support.oxygen_capacity_kg, sc.life_support.initial_oxygen_kg),
    )
    for name, value in (
        ("life_support.co2_kg", s.life_support.co2_kg),
        ("life_support.water_kg", s.life_support.water_kg),
        ("food.food_kg", s.food.food_kg),
        ("power.generation_kw", s.power.generation_kw),
        ("power.unmet_kw", s.power.unmet_kw),
        ("science.points", s.science.points),
        ("science.data_pending_mb", s.science.data_pending_mb),
    ):
        if value < -EPS:
            out.append(f"{name}={value!r} is negative")
    _within(out, "power.dust_factor", s.power.dust_factor, sc.power.dust_floor, 1.0)
    _within(out, "food.ration_level", s.food.ration_level, sc.food.ration_min, 1.0)
    _within(
        out,
        "thermal.setpoint_c",
        s.thermal.setpoint_c,
        sc.thermal.setpoint_min_c,
        sc.thermal.setpoint_max_c,
    )
    _within(
        out,
        "life_support.water_recovery_efficiency",
        s.life_support.water_recovery_efficiency,
        0.0,
        1.0,
    )
    _within(out, "environment.solar_availability", s.environment.solar_availability, 0.0, 1.0)

    for cid, c in s.power.consumers.items():
        if c.demand_kw < -EPS:
            out.append(f"consumer {cid} demand negative")
        _within(out, f"consumer {cid} allocated", c.allocated_kw, 0.0, c.demand_kw)
        _within(out, f"consumer {cid} supply_ratio", c.supply_ratio, 0.0, 1.0)

    for m in s.crew:
        _within(out, f"crew {m.id} health", m.health, 0.0, 1.0)
        _within(out, f"crew {m.id} fatigue", m.fatigue, 0.0, 1.0)
        if m.dose_msv < -EPS:
            out.append(f"crew {m.id} dose negative")
        if (m.location == CrewLocation.EVA) != (m.eva_remaining_ticks > 0):
            out.append(f"crew {m.id} EVA flag inconsistent with {m.eva_remaining_ticks} ticks")
    for cid, comp in s.components.items():
        _within(out, f"component {cid} health", comp.health, 0.0, 1.0)
        if comp.maintenance_remaining_ticks < 0:
            out.append(f"component {cid} maintenance ticks negative")

    active = s.science.active_opportunity
    if active is not None:
        opp = s.science.opportunities.get(active)
        if opp is None or opp.status != OpportunityStatus.ACTIVE:
            out.append(f"active opportunity {active} is not ACTIVE")
    if (
        sum(
            1
            for o in s.science.opportunities.values()
            if o.status == OpportunityStatus.ACTIVE and not sc.opportunity(o.id).requires_rover
        )
        > 1
    ):
        out.append("more than one habitat science activity is ACTIVE")

    if s.tick > sc.time.max_ticks or s.tick < 0:
        out.append(f"tick {s.tick} outside [0, {sc.time.max_ticks}]")
    phase_ids = [p.id for p in sc.phases]
    if s.phase not in phase_ids:
        out.append(f"unknown phase {s.phase}")
    hist = [(phase_ids.index(p.phase), p.tick) for p in s.phase_history if p.phase in phase_ids]
    if hist != sorted(hist):
        out.append("phase history is not ordered")
    rules = {a.id for a in sc.alerts}
    if not set(s.alerts) <= rules:
        out.append(f"unknown alerts {sorted(set(s.alerts) - rules)}")
    max_fires = {e.id: e.max_fires for e in sc.events}
    for eid, n in s.event_fire_counts.items():
        if n > max_fires.get(eid, 0):
            out.append(f"event {eid} fired {n} times (max {max_fires.get(eid, 0)})")
    for mod in s.modifiers:
        if mod.end_tick < s.tick:
            out.append(f"expired modifier from {mod.event_id} still active")
    if (s.status == MissionStatus.CONCLUDED) != (s.outcome is not None):
        out.append("status and outcome disagree")

    if previous is not None:
        if s.tick != previous.tick + 1:
            out.append(f"tick went {previous.tick} → {s.tick}")
        prev_dose = {c.id: c.dose_msv for c in previous.crew}
        for m in s.crew:
            if m.dose_msv < prev_dose.get(m.id, 0.0) - EPS:
                out.append(f"crew {m.id} dose decreased")
        for name, now, before in (
            ("science.points", s.science.points, previous.science.points),
            (
                "comms.data_downlinked_mb",
                s.comms.data_downlinked_mb,
                previous.comms.data_downlinked_mb,
            ),
            ("decisions_applied", float(s.decisions_applied), float(previous.decisions_applied)),
        ):
            if now < before - EPS:
                out.append(f"{name} decreased ({before} → {now})")
        for eid, n in previous.event_fire_counts.items():
            if s.event_fire_counts.get(eid, 0) < n:
                out.append(f"event fire count for {eid} decreased")
        for oid, obj in previous.objectives.items():
            if obj.status != ObjectiveStatus.PENDING and s.objectives[oid].status != obj.status:
                out.append(f"objective {oid} changed after being resolved")
        if phase_ids.index(s.phase) < phase_ids.index(previous.phase):
            out.append(f"phase moved backwards {previous.phase} → {s.phase}")
    return out
