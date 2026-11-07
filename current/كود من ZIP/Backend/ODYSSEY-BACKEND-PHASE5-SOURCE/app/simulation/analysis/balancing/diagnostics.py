"""Automated detectors for balance pathologies.

Each detector reads sweep / ablation / impact results and emits a :class:`Finding` with the
evidence (rates, counts) that triggered it. Detectors report; they never decide whether a
finding is a bug, a balance issue or a product decision — that classification is done by a
person in ``docs/BALANCING_FINDINGS.md``.

Thresholds are reporting thresholds (what is worth a look), not balance targets.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.simulation.scenarios.schema import ScenarioDefinition

from .aggregate import StrategySummary
from .impact import ImpactSummary
from .runner import MissionMetrics
from .sensitivity import AblationRow

LOW_VARIETY = 0.25  # distinct results / missions below this → seeds barely matter
DECISIVE_EVENT_SHIFT = 0.2  # outcome-rate change when an event is removed
EXPLORATORY = {"random_valid"}


@dataclass(frozen=True, slots=True)
class Finding:
    detector: str
    subject: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "subject": self.subject,
            "summary": self.summary,
            "evidence": self.evidence,
        }


def _scripted(summaries: Sequence[StrategySummary]) -> list[StrategySummary]:
    return [s for s in summaries if s.strategy not in EXPLORATORY]


def objectives(summaries: Sequence[StrategySummary]) -> list[Finding]:
    out: list[Finding] = []
    ids = sorted({o for s in summaries for o in s.objective_rates})
    for oid in ids:
        rates = {s.strategy: s.objective_rates.get(oid, 0.0) for s in summaries}
        if all(r == 0.0 for r in rates.values()):
            out.append(
                Finding(
                    "objective_never_achieved",
                    oid,
                    f"'{oid}' was achieved by no strategy in any mission",
                    rates,
                )
            )
        elif all(r == 0.0 for k, r in rates.items() if k not in EXPLORATORY):
            out.append(
                Finding(
                    "objective_never_achieved_by_scripted_play",
                    oid,
                    f"'{oid}' only happens under random play",
                    rates,
                )
            )
        if all(r == 1.0 for r in rates.values()):
            out.append(
                Finding(
                    "objective_always_achieved",
                    oid,
                    f"'{oid}' is achieved in every mission by every strategy",
                    rates,
                )
            )
        elif rates.get("passive") == 1.0:
            out.append(
                Finding(
                    "objective_free",
                    oid,
                    f"'{oid}' is achieved by doing nothing (passive: 100%)",
                    rates,
                )
            )
    return out


def outcomes(scenario: ScenarioDefinition, rows: Sequence[MissionMetrics]) -> list[Finding]:
    seen = {r.outcome for r in rows}
    return [
        Finding(
            "outcome_unreachable",
            rule.code,
            f"outcome '{rule.code}' (rule '{rule.id}') never occurred in {len(rows)} missions",
            {"missions": len(rows)},
        )
        for rule in scenario.outcomes
        if rule.code not in seen
    ]


def alerts(scenario: ScenarioDefinition, summaries: Sequence[StrategySummary]) -> list[Finding]:
    out: list[Finding] = []
    scripted = _scripted(summaries)
    for rule in scenario.alerts:
        rates = {s.strategy: s.alert_rates.get(rule.id, 0.0) for s in summaries}
        if scripted and all(rates[s.strategy] == 1.0 for s in scripted):
            out.append(
                Finding(
                    "alert_unavoidable",
                    rule.id,
                    f"'{rule.id}' ({rule.severity.value}) fires in 100% of missions "
                    "for every scripted strategy",
                    rates,
                )
            )
        if all(r == 0.0 for r in rates.values()):
            out.append(
                Finding(
                    "alert_never_fires",
                    rule.id,
                    f"'{rule.id}' ({rule.metric} {rule.op} {rule.threshold}) never "
                    "fires — that resource/system never becomes critical",
                    rates,
                )
            )
    return out


def systems(summaries: Sequence[StrategySummary]) -> list[Finding]:
    out: list[Finding] = []
    scripted = _scripted(summaries)
    faults = {s.strategy: s.stats["random_faults"].mean for s in summaries}
    maint = {s.strategy: s.stats["maintenance_completed"].mean for s in summaries}
    if scripted and all(faults[s.strategy] < 0.1 for s in scripted):
        out.append(
            Finding(
                "negligible_system",
                "degradation",
                "random component faults average < 0.1 per mission for every scripted strategy",
                {"mean_random_faults": faults, "mean_maintenance_completed": maint},
            )
        )
    for s in summaries:
        variety = s.distinct_final_states / s.missions
        if variety < LOW_VARIETY:
            out.append(
                Finding(
                    "seed_insensitive",
                    s.strategy,
                    f"{s.distinct_final_states} distinct results from {s.missions} "
                    "seeds — randomness barely changes this strategy's mission",
                    {"distinct": s.distinct_final_states, "missions": s.missions},
                )
            )
    return out


def strategies(summaries: Sequence[StrategySummary]) -> list[Finding]:
    out: list[Finding] = []
    scripted = _scripted(summaries)
    if not scripted:
        return out
    best = max(s.success_rate for s in scripted)
    for s in scripted:
        decisions = s.stats["decisions_accepted"].p50
        if best > 0 and s.success_rate == best and decisions <= 6:
            out.append(
                Finding(
                    "degenerate_strategy",
                    s.strategy,
                    f"reaches the best success rate ({best:.0%}) with a median of "
                    f"{decisions:g} decisions",
                    {"success": best, "median_decisions": decisions},
                )
            )
    rates = {s.strategy: s.success_rate for s in scripted}
    if len({round(r, 6) for r in rates.values()}) <= 2:
        out.append(
            Finding(
                "binary_outcomes",
                "all",
                "scripted strategies split into at most two success levels",
                rates,
            )
        )
    return out


def events(rows: Sequence[AblationRow]) -> list[Finding]:
    out: list[Finding] = []
    by_event: dict[str, list[AblationRow]] = {}
    for r in rows:
        by_event.setdefault(r.event_id, []).append(r)
    for event_id, rs in sorted(by_event.items()):
        shifts = {}
        for r in rs:
            b, a = r.baseline["outcome_rates"], r.ablated["outcome_rates"]
            shifts[r.strategy] = max(abs(a[k] - b[k]) for k in b)
        objective_shift = {
            r.strategy: max(
                abs(r.ablated["objective_rates"][o] - r.baseline["objective_rates"][o])
                for o in r.baseline["objective_rates"]
            )
            for r in rs
        }
        if max(shifts.values()) >= DECISIVE_EVENT_SHIFT:
            out.append(
                Finding(
                    "decisive_event",
                    event_id,
                    f"removing '{event_id}' moves outcome rates by up to "
                    f"{max(shifts.values()):.0%}",
                    {"outcome_shift": shifts, "objective_shift": objective_shift},
                )
            )
        elif max(shifts.values()) == 0.0 and max(objective_shift.values()) == 0.0:
            out.append(
                Finding(
                    "event_without_outcome_effect",
                    event_id,
                    f"removing '{event_id}' changes no outcome or objective rate",
                    {"objective_shift": objective_shift},
                )
            )
    return out


def decisions(impact: Sequence[ImpactSummary]) -> list[Finding]:
    out: list[Finding] = []
    for s in impact:
        subject = f"{s.strategy}: {s.decision_type} → {s.alternative} [{s.continuation}]"
        if s.no_effect_rate == 1.0:
            out.append(
                Finding(
                    "no_op_decision",
                    subject,
                    f"no measurable effect in {s.forks} forks",
                    s.as_dict(),
                )
            )
        elif s.outcome_changed_rate >= 0.9:
            out.append(
                Finding(
                    "pivotal_decision",
                    subject,
                    f"changes the mission outcome in {s.outcome_changed_rate:.0%} of "
                    f"{s.forks} forks",
                    s.as_dict(),
                )
            )
    return out
