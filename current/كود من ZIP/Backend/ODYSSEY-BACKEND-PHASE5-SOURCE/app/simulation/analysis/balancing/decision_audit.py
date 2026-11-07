"""Decision audit: classify each decision kind by its measured consequences.

Method (open loop, so only the inserted decision differs):

1. A reference strategy plays a mission; its decisions are recorded.
2. For each catalogue decision and each probe tick, the reference plan is replayed with the
   catalogue decision **inserted** at that tick (later reference decisions are re-applied;
   any the engine now rejects are skipped). Inserting the decision the reference would make
   anyway is a no-op and is reported as such.
3. The resulting mission is compared with the reference: outcome tier, objectives, and
   resource / safety / science measures.

Classification (per decision kind, over all seeds and probe ticks where it was valid):

* ``HIGH``: changes the outcome tier or a primary/safety/stability objective in ≥ 25 % of
  insertions;
* ``MEDIUM``: changes some objective in ≥ 10 % of insertions, or moves end battery by ≥ 0.05
  SOC, dose by ≥ 1 mSv, science by ≥ 10 points, or water / oxygen by ≥ 0.5 day in ≥ 25 %;
* ``LOCAL``: a measurable change in ≥ 25 % of insertions, below the MEDIUM bars;
* ``REDUNDANT``: no measurable change in ≥ 75 % of valid insertions;
* ``INFORMATIONAL`` is reserved for actions with no state effect (none of the engine's
  decision types are informational; Future Lens and ORION queries are, and are not decisions).

Thresholds are analysis parameters, not balance targets.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.simulation.domain.decisions import parse_decision
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine
from app.simulation.replay.replay import ReplayDecision, replay

from .runner import outcome_class, run_mission

Raw = dict[str, Any]


def _mode(subsystem: str, mode: str) -> tuple[str, Raw]:
    return (
        f"{subsystem} {mode}",
        {"type": "set_subsystem_mode", "subsystem": subsystem, "mode": mode},
    )


def _maintain(component: str) -> tuple[str, Raw]:
    return f"maintain {component}", {"type": "schedule_maintenance", "component": component}


CATALOGUE: tuple[tuple[str, Raw], ...] = (
    _mode("habitat_core", "eco"),
    _mode("co2_scrubber", "eco"),
    _mode("co2_scrubber", "boost"),
    _mode("oxygen_generation", "off"),
    _mode("oxygen_generation", "eco"),
    _mode("thermal_heater", "eco"),
    _mode("water_recovery", "eco"),
    _mode("water_recovery", "off"),
    _mode("comms", "eco"),
    _mode("comms", "off"),
    _mode("science_payload", "boost"),
    _mode("rover_charger", "off"),
    ("setpoint 15 °C", {"type": "set_thermal_setpoint", "target_c": 15.0}),
    ("setpoint 24 °C", {"type": "set_thermal_setpoint", "target_c": 24.0}),
    ("rations 75 %", {"type": "set_ration_level", "level": 0.75}),
    _maintain("oxygen_generator"),
    _maintain("co2_scrubber"),
    _maintain("battery"),
    _maintain("solar_array"),
    ("crew to shelter", {"type": "set_crew_location", "location": "shelter"}),
    ("clean solar array", {"type": "clean_solar_array", "crew_id": "crew_pwr"}),
    ("rover transfer energy", {"type": "rover_command", "action": "transfer_energy"}),
    ("rover stow", {"type": "rover_command", "action": "stow"}),
    ("stop science", {"type": "stop_science_activity"}),
)
PROBE_TICKS = (30, 110, 175, 212)
HIGH_RATE = 0.25
MEDIUM_OBJECTIVE_RATE = 0.10
MEDIUM_RESOURCE_RATE = 0.25
LOCAL_RATE = 0.25
REDUNDANT_RATE = 0.75
MATERIAL = {
    "battery_soc_final": 0.05,
    "crew_dose_max_msv": 1.0,
    "science_points": 10.0,
    "water_days_final": 0.5,
    "oxygen_days_final": 0.5,
}
MEASURABLE = 1e-6
CORE_CATEGORIES = ("primary", "safety", "stability")


@dataclass(slots=True)
class Insertion:
    label: str
    seed: int
    tick: int
    valid: bool
    tier_changed: bool = False
    core_objectives_changed: list[str] = field(default_factory=list)
    objectives_changed: list[str] = field(default_factory=list)
    deltas: dict[str, float] = field(default_factory=dict)

    @property
    def material(self) -> bool:
        return any(abs(self.deltas.get(k, 0.0)) >= v for k, v in MATERIAL.items())

    @property
    def measurable(self) -> bool:
        return (
            self.tier_changed
            or bool(self.objectives_changed)
            or any(abs(v) > MEASURABLE for v in self.deltas.values())
        )


@dataclass(slots=True)
class DecisionClass:
    label: str
    decision: Raw
    insertions: int
    tier_change_rate: float
    core_objective_rate: float
    objective_rate: float
    material_rate: float
    measurable_rate: float
    mean_deltas: dict[str, float]
    classification: str
    objectives_touched: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


def _metrics(engine: SimulationEngine, final: Any) -> dict[str, float]:
    m = engine.metrics
    return {
        "battery_soc_final": m.value("power.battery_soc", final),
        "crew_dose_max_msv": m.value("crew.max_dose_msv", final),
        "science_points": final.science.points,
        "water_days_final": m.value("life_support.water_days", final),
        "oxygen_days_final": m.value("life_support.oxygen_days", final),
        "crew_min_health": m.value("crew.min_health", final),
        "data_downlinked_mb": final.comms.data_downlinked_mb,
    }


def audit(
    engine: SimulationEngine,
    *,
    reference: str = "balanced",
    seeds: Sequence[int] = (1, 2, 3, 4, 5),
    ticks: Sequence[int] = PROBE_TICKS,
    catalogue: Sequence[tuple[str, Raw]] = CATALOGUE,
) -> tuple[list[DecisionClass], list[Insertion]]:
    sc = engine.scenario
    cats = {o.id: o.effective_category for o in sc.objectives}
    rows: list[Insertion] = []
    for seed in seeds:
        run = run_mission(engine, reference, seed)
        base_final = run.final
        base_tier = outcome_class(engine, base_final)
        base_obj = {k: v.status.value for k, v in base_final.objectives.items()}
        base_m = _metrics(engine, base_final)
        recorded = [d.to_replay() for d in run.decisions]
        for tick in ticks:
            if tick >= base_final.tick:
                continue
            prefix = [d for d in recorded if d.tick < tick]
            state = replay(engine, run.initial, prefix, tick, skip_invalid=True).state
            for label, raw in catalogue:
                decision = parse_decision(raw)
                try:
                    engine.validate_decision(state, decision)
                except DecisionRejectedError:
                    rows.append(Insertion(label, seed, tick, valid=False))
                    continue
                inserted = ReplayDecision("audit:insert", 0, tick, decision)
                plan = sorted(
                    [*recorded, inserted],
                    key=lambda d: (d.tick, 0 if d.decision_id == "audit:insert" else 1, d.sequence),
                )
                plan = [
                    ReplayDecision(d.decision_id, i + 1, d.tick, d.decision)
                    for i, d in enumerate(plan)
                ]
                res = replay(engine, run.initial, plan, sc.time.max_ticks, skip_invalid=True)
                fin = res.state
                obj = {k: v.status.value for k, v in fin.objectives.items()}
                changed = sorted(k for k in obj if obj[k] != base_obj.get(k))
                m = _metrics(engine, fin)
                rows.append(
                    Insertion(
                        label,
                        seed,
                        tick,
                        valid=True,
                        tier_changed=outcome_class(engine, fin) != base_tier,
                        core_objectives_changed=[k for k in changed if cats[k] in CORE_CATEGORIES],
                        objectives_changed=changed,
                        deltas={k: m[k] - base_m[k] for k in m},
                    )
                )
    by_label: dict[str, list[Insertion]] = defaultdict(list)
    for r in rows:
        if r.valid:
            by_label[r.label].append(r)
    classes: list[DecisionClass] = []
    for label, raw in catalogue:
        ins = by_label.get(label, [])
        n = len(ins)
        if n == 0:
            classes.append(
                DecisionClass(label, raw, 0, 0, 0, 0, 0, 0, {}, "NOT_VALID_IN_PROBES", {})
            )
            continue
        tier = sum(r.tier_changed for r in ins) / n
        core = sum(bool(r.core_objectives_changed) for r in ins) / n
        anyobj = sum(bool(r.objectives_changed) for r in ins) / n
        material = sum(r.material for r in ins) / n
        measurable = sum(r.measurable for r in ins) / n
        touched: dict[str, int] = defaultdict(int)
        for r in ins:
            for o in r.objectives_changed:
                touched[o] += 1
        if tier >= HIGH_RATE or core >= HIGH_RATE:
            cls = "HIGH"
        elif anyobj >= MEDIUM_OBJECTIVE_RATE or material >= MEDIUM_RESOURCE_RATE:
            cls = "MEDIUM"
        elif 1 - measurable >= REDUNDANT_RATE:
            cls = "REDUNDANT"
        elif measurable >= LOCAL_RATE:
            cls = "LOCAL"
        else:
            cls = "REDUNDANT"
        keys = ins[0].deltas.keys()
        classes.append(
            DecisionClass(
                label=label,
                decision=raw,
                insertions=n,
                tier_change_rate=tier,
                core_objective_rate=core,
                objective_rate=anyobj,
                material_rate=material,
                measurable_rate=measurable,
                mean_deltas={k: sum(r.deltas[k] for r in ins) / n for k in keys},
                classification=cls,
                objectives_touched=dict(sorted(touched.items())),
            )
        )
    return classes, rows
