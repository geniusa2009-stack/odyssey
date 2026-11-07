"""Engineering profile: describes *how* a player engineered the mission.

Two layers:

1. **Features** — deterministic, documented measurements in [0, 1] computed from the decision
   ledger and the reconstructed history (never from free text).
2. **Dimensions** — weighted averages of features. Weights live in ``profile_weights.yaml`` and
   are PROVISIONAL (a product decision), so they are data, not code.

Feature definitions:
    proactive_ratio       share of decisions taken while no warning/critical alert was active
    alert_response_speed  1 − clamp(mean ticks from a warning/critical alert to the next
                          decision / 24); 1.0 if no alerts were raised
    reserve_margin        mean over ticks of 1 − max severity of the resource metrics
    load_management       share of decisions that reduce load (eco/off modes, lower setpoint,
                          rations, stow/transfer)
    crew_protection       0.5·(mean of min crew health) + 0.5·(share of elevated-radiation
                          ticks spent sheltered; 1.0 if none)
    science_return        science points / maximum attainable points in the scenario
    risk_acceptance       peak composite mission risk
    boost_usage           share of ticks with any subsystem in boost
    anticipation          share of load-reducing decisions taken while battery SOC ≥ 0.5
    system_diversity      distinct systems touched / distinct systems available
    cascade_containment   1 − clamp(cascade warnings / 10)
    lens_usage            clamp(Future Lens requests / max(1, decisions))
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.analysis.reconstruct import MissionRecord
from app.simulation.domain.enums import AlertSeverity, EventKind
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import load_yaml

WEIGHTS_FILE = Path(__file__).parent / "profile_weights.yaml"
RESOURCE_METRICS = (
    "power.battery_soc",
    "life_support.oxygen_days",
    "life_support.water_days",
    "food.food_days",
    "life_support.co2_ppm",
    "thermal.habitat_temp_c",
)
DIMENSIONS = (
    "systems_thinking",
    "resource_efficiency",
    "crew_safety",
    "scientific_ambition",
    "risk_preference",
    "crisis_response",
    "long_term_planning",
)


class ProfileWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    dimensions: dict[str, dict[str, float]]


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    score: float
    contributions: dict[str, float]


class EngineeringProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights_version: str
    provisional: bool = True
    features: dict[str, float]
    dimensions: list[DimensionScore]
    decision_count: int
    ticks_analysed: int
    notes: list[str] = Field(default_factory=list)


@lru_cache(maxsize=1)
def default_weights() -> ProfileWeights:
    return ProfileWeights.model_validate(load_yaml(WEIGHTS_FILE.read_text(encoding="utf-8")))


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def _is_load_reducing(decision_type: str, inputs: dict[str, object]) -> bool:
    if decision_type == "set_subsystem_mode":
        return inputs.get("mode") in ("eco", "off")
    if decision_type in ("set_thermal_setpoint", "set_ration_level"):
        return True
    if decision_type == "rover_command":
        return inputs.get("action") in ("stow", "transfer_energy")
    return decision_type == "stop_science_activity"


def compute_features(
    engine: SimulationEngine, record: MissionRecord, *, lens_requests: int = 0
) -> dict[str, float]:
    m = engine.metrics
    sc = engine.scenario
    hist = record.history
    recs = record.records
    n_dec = len(recs)
    by_tick = {s.tick: s for s in hist}

    def state_at(tick: int) -> MissionState:
        return by_tick.get(tick, hist[min(len(hist) - 1, max(0, tick - hist[0].tick))])

    serious = (AlertSeverity.WARNING, AlertSeverity.CRITICAL)
    proactive = sum(
        1 for r in recs if not any(a.severity in serious for a in state_at(r.tick).alerts.values())
    )
    proactive_ratio = proactive / n_dec if n_dec else 0.0

    alert_ticks = [
        e.tick
        for e in record.events
        if e.kind in (EventKind.ALERT_RAISED, EventKind.RESOURCE_WARNING)
        and e.severity is not None
        and e.severity.value in ("warning", "critical")
    ]
    decision_ticks = sorted(r.tick for r in recs)
    latencies: list[int] = []
    for t in alert_ticks:
        nxt = next((d for d in decision_ticks if d > t), None)
        latencies.append(24 if nxt is None else min(24, nxt - t))
    response = 1.0 - _clamp(sum(latencies) / len(latencies) / 24.0) if latencies else 1.0

    margins = [1.0 - max(m.severity(k, s) for k in RESOURCE_METRICS) for s in hist]
    reserve_margin = sum(margins) / len(margins)

    reducing = [r for r in recs if _is_load_reducing(r.decision_type, r.inputs)]
    load_management = len(reducing) / n_dec if n_dec else 0.0
    anticipation = (
        sum(1 for r in reducing if m.value("power.battery_soc", state_at(r.tick)) >= 0.5)
        / len(reducing)
        if reducing
        else 0.0
    )

    min_health = [m.value("crew.min_health", s) for s in hist]
    elevated = [
        s
        for s in hist
        if s.environment.radiation_dose_rate_msv_h > sc.radiation.health_threshold_msv_per_hour
    ]
    sheltered = (
        sum(1 for s in elevated if m.value("crew.in_shelter", s) > 0) / len(elevated)
        if elevated
        else 1.0
    )
    crew_protection = 0.5 * (sum(min_health) / len(min_health)) + 0.5 * sheltered

    max_points = sum(o.points_per_tick * o.work_ticks_required for o in sc.science.opportunities)
    science_return = _clamp(record.final_state.science.points / max_points) if max_points else 0.0

    risk_acceptance = max(m.value("risk.mission", s) for s in hist)
    boost_usage = sum(1 for s in hist if m.value("control.boost_load_kw", s) > 0) / len(hist)

    available_systems = {c.system for c in sc.power.consumers} | {"crew", "food", "maintenance"}
    touched = {sys for r in recs for sys in r.affected_systems if sys in available_systems}
    system_diversity = len(touched) / len(available_systems)

    cascades = sum(1 for e in record.events if e.kind == EventKind.CASCADE_WARNING)
    cascade_containment = 1.0 - _clamp(cascades / 10.0)
    lens_usage = _clamp(lens_requests / max(1, n_dec))

    return {
        "proactive_ratio": proactive_ratio,
        "alert_response_speed": response,
        "reserve_margin": reserve_margin,
        "load_management": load_management,
        "crew_protection": crew_protection,
        "science_return": science_return,
        "risk_acceptance": risk_acceptance,
        "boost_usage": boost_usage,
        "anticipation": anticipation,
        "system_diversity": system_diversity,
        "cascade_containment": cascade_containment,
        "lens_usage": lens_usage,
    }


def build_profile(
    engine: SimulationEngine,
    record: MissionRecord,
    *,
    weights: ProfileWeights | None = None,
    lens_requests: int = 0,
) -> EngineeringProfile:
    w = weights or default_weights()
    features = compute_features(engine, record, lens_requests=lens_requests)
    dims: list[DimensionScore] = []
    for name in DIMENSIONS:
        spec = w.dimensions.get(name, {})
        total = sum(spec.values())
        contributions = (
            {f: features[f] * wt / total for f, wt in sorted(spec.items())} if total > 0 else {}
        )
        dims.append(
            DimensionScore(
                dimension=name,
                score=_clamp(sum(contributions.values())),
                contributions=contributions,
            )
        )
    notes = ["Scores describe engineering style, not a grade; weights are provisional."]
    if not record.records:
        notes.append("No decisions recorded: decision-based features default to 0.")
    return EngineeringProfile(
        weights_version=w.version,
        features=features,
        dimensions=dims,
        decision_count=len(record.records),
        ticks_analysed=len(record.history),
        notes=notes,
    )
