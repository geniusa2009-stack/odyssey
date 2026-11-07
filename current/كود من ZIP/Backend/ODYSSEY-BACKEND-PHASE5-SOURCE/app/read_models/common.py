"""Shared building blocks of the frontend-safe read models.

Rules every read model follows (see docs/API_CONTRACT.md):

* **Composed from simulation truth.** Values come from the engine's metric registry, the
  mission state and the scenario definition. No read model re-implements simulation formulas.
* **No hidden information.** Never the random seed, never unfired unforeseeable events, never
  active-modifier end ticks or event trigger internals.
* **Honest precision.** Numbers are rounded to a per-unit display precision.
* **Stable shape.** Every model forbids extra fields and is frozen; additions are additive.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.simulation.domain.enums import AlertSeverity
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine

READ_MODEL_VERSION = 1

StatusBand = Literal["nominal", "degraded", "critical"]
WarningState = Literal["none", "caution", "warning", "critical"]

# Display precision (decimal places) per unit. Values are rounded to this before leaving the
# backend, so clients never show more precision than the model justifies.
UNIT_PRECISION: dict[str, int] = {
    "fraction": 3,
    "factor": 2,
    "index": 3,
    "kWh": 1,
    "kW": 2,
    "days": 2,
    "ppm": 0,
    "°C": 1,
    "mSv": 2,
    "mSv/h": 3,
    "MB": 1,
    "points": 1,
    "kg": 2,
    "count": 0,
    "people": 0,
    "bool": 0,
    "h": 1,
    "tick": 0,
    "code": 0,
}
DEFAULT_PRECISION = 3
_SEVERITY_RANK: dict[str, int] = {"none": 0, "caution": 1, "warning": 2, "critical": 3}


class View(BaseModel):
    """Base class of every read model: closed shape, immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def precision(unit: str) -> int:
    return UNIT_PRECISION.get(unit, DEFAULT_PRECISION)


def rnd(value: float, digits: int) -> float:
    """Round for display; never returns -0.0 or non-finite values."""
    if not math.isfinite(value):
        return 0.0
    out = round(float(value), digits)
    return 0.0 if out == 0 else out


def rnd_unit(value: float, unit: str) -> float:
    return rnd(value, precision(unit))


def band(severity: float) -> StatusBand:
    """Status band from a metric severity index (0 = at/better than nominal, 1 = critical).

    The band boundaries are the scenario's own severity scale: the nominal value maps to 0 and
    the critical value to 1.
    """
    if severity >= 1.0 - 1e-9:
        return "critical"
    if severity > 1e-9:
        return "degraded"
    return "nominal"


def worst_warning(levels: list[str]) -> WarningState:
    worst: WarningState = "none"
    for level in levels:
        if _SEVERITY_RANK.get(level, 0) > _SEVERITY_RANK[worst]:
            worst = level  # type: ignore[assignment]
    return worst


def active_alert_levels(
    engine: SimulationEngine, state: MissionState, metrics: set[str] | frozenset[str]
) -> list[str]:
    """Severities of the active alerts on any of ``metrics``."""
    return [a.severity.value for a in state.alerts.values() if a.metric in metrics]


def severity_value(severity: AlertSeverity | None) -> str | None:
    return severity.value if severity is not None else None


class MetricValue(View):
    id: str
    label: str
    value: float
    unit: str


def metric_value(
    engine: SimulationEngine, state: MissionState, metric: str, field_id: str | None = None
) -> MetricValue:
    spec = engine.metrics.spec(metric)
    return MetricValue(
        id=field_id or metric,
        label=spec.label,
        value=rnd_unit(engine.metrics.value(metric, state), spec.unit),
        unit=spec.unit,
    )


# Keys of engine event data that describe how the *scenario* produces an event (trigger
# parameters, effect parameters, random draws). Clients get what happened, never how the
# scenario schedules it.
INTERNAL_EVENT_KEYS = frozenset({"trigger", "effects", "random"})


def clean_data(data: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in data.items() if k not in INTERNAL_EVENT_KEYS}
