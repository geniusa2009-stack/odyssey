"""Radiation budget read model: what a rational player needs, and nothing hidden.

Exposed: the mission dose limit, the highest crew dose and the remaining margin, a *projected*
end-of-mission dose, the current surface, background and received dose rates, the acute
threshold, shelter and EVA state and the per-crew doses.

The projection uses the scenario's **baseline** dose rate only (``env.background_dose_rate_msv_h``
and ``crew.projected_dose_msv`` in the metric registry): it never anticipates space-weather
events, so it is identical with or without a future storm (tested). Scenarios without a mission
dose limit (v0.1.0) report ``budget_state: "no_limit"`` and no margins.
"""

from __future__ import annotations

from typing import Literal

from app.read_models.common import View, WarningState, active_alert_levels, rnd, worst_warning
from app.simulation.domain.enums import CrewLocation
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

BudgetState = Literal["within_budget", "budget_low", "budget_exceeded", "no_limit"]
ExposureStatus = Literal["background", "elevated"]
PROJECTION_BASIS = "baseline_rate_current_locations"
PROJECTION_STATEMENT = (
    "Projected dose assumes the background dose rate for the rest of the mission at the "
    "crew's current locations. It does not anticipate space-weather events."
)
_RADIATION_METRICS = frozenset(
    {
        "env.radiation_dose_rate_msv_h",
        "crew.received_dose_rate_msv_h",
        "crew.max_dose_msv",
        "crew.dose_margin_msv",
        "crew.projected_dose_msv",
        "crew.projected_dose_margin_msv",
    }
)


class CrewDoseView(View):
    crew_id: str
    dose_msv: float
    location: str
    margin_msv: float | None


class RadiationBudgetView(View):
    dose_limit_msv: float | None
    max_dose_msv: float
    dose_margin_msv: float | None
    projected_dose_msv: float | None
    projected_dose_margin_msv: float | None
    projection_basis: str = PROJECTION_BASIS
    projection_statement: str = PROJECTION_STATEMENT
    surface_dose_rate_msv_h: float
    background_dose_rate_msv_h: float | None
    received_dose_rate_msv_h: float
    acute_threshold_msv_h: float
    exposure_status: ExposureStatus
    budget_state: BudgetState
    warning_state: WarningState
    crew_in_shelter: int
    crew_on_eva: list[str]
    crew: list[CrewDoseView]


def build_radiation(engine: SimulationEngine, state: MissionState) -> RadiationBudgetView:
    sc, m = engine.scenario, engine.metrics
    limit = sc.radiation.dose_limit_msv

    def val(name: str, digits: int) -> float | None:
        return rnd(m.value(name, state), digits) if m.has(name) else None

    surface = m.value("env.radiation_dose_rate_msv_h", state)
    background = (
        m.value("env.background_dose_rate_msv_h", state)
        if m.has("env.background_dose_rate_msv_h")
        else None
    )
    if background is not None:
        elevated = surface > background * 1.001 + 1e-12
    else:
        elevated = m.severity("env.radiation_dose_rate_msv_h", state) > 0
    budget: BudgetState
    if limit is None:
        budget = "no_limit"
    elif m.value("crew.dose_margin_msv", state) <= 0:
        budget = "budget_exceeded"
    elif (
        m.severity("crew.dose_margin_msv", state) > 0
        or m.severity("crew.projected_dose_margin_msv", state) > 0
    ):
        budget = "budget_low"
    else:
        budget = "within_budget"
    crew = [
        CrewDoseView(
            crew_id=c.id,
            dose_msv=rnd(c.dose_msv, 2),
            location=c.location.value,
            margin_msv=rnd(limit - c.dose_msv, 2) if limit is not None else None,
        )
        for c in state.crew
    ]
    return RadiationBudgetView(
        dose_limit_msv=limit,
        max_dose_msv=rnd(m.value("crew.max_dose_msv", state), 2),
        dose_margin_msv=val("crew.dose_margin_msv", 2) if limit is not None else None,
        projected_dose_msv=val("crew.projected_dose_msv", 2) if limit is not None else None,
        projected_dose_margin_msv=val("crew.projected_dose_margin_msv", 2)
        if limit is not None
        else None,
        surface_dose_rate_msv_h=rnd(surface, 3),
        background_dose_rate_msv_h=rnd(background, 3) if background is not None else None,
        received_dose_rate_msv_h=rnd(m.value("crew.received_dose_rate_msv_h", state), 3),
        acute_threshold_msv_h=sc.radiation.health_threshold_msv_per_hour,
        exposure_status="elevated" if elevated else "background",
        budget_state=budget,
        warning_state=worst_warning(active_alert_levels(engine, state, _RADIATION_METRICS)),
        crew_in_shelter=sum(1 for c in state.crew if c.location == CrewLocation.SHELTER),
        crew_on_eva=[c.id for c in state.crew if c.location == CrewLocation.EVA],
        crew=crew,
    )
