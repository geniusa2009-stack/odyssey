"""Balancing Lab: backend-only, deterministic measurement of how LUNA-01 plays.

Runs thousands of missions with scripted strategies (no HTTP, no database), aggregates
outcomes and telemetry, probes parameter sensitivity, event decisiveness and decision impact,
and exports JSON/CSV. It *measures* balance; it never changes the shipped scenario.

Entry point: ``python -m app.simulation.analysis.balancing --help``. See docs/BALANCING_LAB.md.
"""

from .aggregate import StrategySummary, summarize
from .impact import ImpactRow, decision_impact, summarize_impact
from .overrides import OverrideError, apply_overrides, parse_override
from .runner import MissionMetrics, MissionRun, run_mission
from .sensitivity import run_ablation, run_sensitivity
from .strategies import DIAGNOSTIC_PROBES, PROBE_STRATEGIES, STRATEGIES, make_strategy
from .sweep import SweepResult, SweepSpec, run_sweep

__all__ = [
    "DIAGNOSTIC_PROBES",
    "PROBE_STRATEGIES",
    "STRATEGIES",
    "ImpactRow",
    "MissionMetrics",
    "MissionRun",
    "OverrideError",
    "StrategySummary",
    "SweepResult",
    "SweepSpec",
    "apply_overrides",
    "decision_impact",
    "make_strategy",
    "parse_override",
    "run_ablation",
    "run_mission",
    "run_sensitivity",
    "run_sweep",
    "summarize",
    "summarize_impact",
]
