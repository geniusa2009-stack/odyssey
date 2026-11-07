"""Decision impact: does a decision actually change the mission?

For a mission played by a strategy, each selected decision is **forked**: the mission is
replayed from the initial state with identical earlier decisions (the engine is deterministic,
so the prefix is bit-identical), the decision is *omitted* or *replaced* by an alternative, and
the mission continues in one of two ways:

* ``replay`` (open loop) — every later recorded decision is re-applied as recorded (rejected
  ones are skipped and counted). Isolates the decision itself; this is the counterfactual the
  Black Box uses.
* ``strategy`` (closed loop) — from the next tick on, the same strategy plays on and reacts to
  the changed situation. Measures whether the decision matters once a player adapts.

The comparison covers outcome, objectives, resource minima, dose, science and risk.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.simulation.engine.engine import SimulationEngine

from .runner import AppliedDecision, MissionMetrics, run_mission
from .strategies import Observation, Raw, Strategy, make_strategy

Continuation = Literal["replay", "strategy"]
DELTA_FIELDS = (
    "battery_soc_min",
    "battery_zero_ticks",
    "crew_dose_max_msv",
    "crew_min_health",
    "science_points",
    "data_downlinked_mb",
    "objectives_achieved",
    "risk_final",
    "risk_peak",
    "duration_ticks",
    "co2_ppm_max",
    "habitat_temp_min",
    "water_days_min",
    "oxygen_days_min",
)
NO_EFFECT_TOLERANCE = 1e-9


@dataclass
class _ForkedPlay(Strategy):
    """Replays a recorded plan with one decision omitted/replaced, then continues."""

    name: str = "fork"
    plan: dict[int, list[Raw]] = field(default_factory=dict)
    fork_tick: int = 0
    resume: Strategy | None = None

    def decide(self, obs: Observation) -> list[Raw]:
        if self.resume is not None and obs.tick > self.fork_tick:
            return self.resume.decide(obs)
        return list(self.plan.get(obs.tick, []))


@dataclass(slots=True)
class ImpactRow:
    strategy: str
    seed: int
    continuation: str
    decision_sequence: int
    decision_tick: int
    decision_type: str
    decision_inputs: dict[str, Any]
    alternative: dict[str, Any] | None
    baseline_outcome: str
    alternative_outcome: str
    outcome_changed: bool
    objectives_changed: dict[str, list[str]]
    deltas: dict[str, float]
    no_effect: bool
    later_decisions_rejected: int

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


def _plan(
    decisions: Sequence[AppliedDecision],
    target: AppliedDecision,
    alternative: Raw | None,
    *,
    keep_after: bool,
) -> dict[int, list[Raw]]:
    plan: dict[int, list[Raw]] = defaultdict(list)
    for d in decisions:
        if d.sequence == target.sequence:
            if alternative is not None:
                plan[d.tick].append(alternative)
        elif d.sequence < target.sequence or keep_after or d.tick == target.tick:
            plan[d.tick].append(dict(d.inputs))
    return dict(plan)


def compare(
    base: MissionMetrics, alt: MissionMetrics
) -> tuple[dict[str, float], dict[str, list[str]], bool]:
    deltas = {f: float(getattr(alt, f)) - float(getattr(base, f)) for f in DELTA_FIELDS}
    changed: dict[str, list[str]] = {"gained": [], "lost": []}
    for oid, status in base.objectives.items():
        new = alt.objectives.get(oid)
        if status != "achieved" and new == "achieved":
            changed["gained"].append(oid)
        elif status == "achieved" and new != "achieved":
            changed["lost"].append(oid)
    no_effect = (
        base.outcome == alt.outcome
        and not changed["gained"]
        and not changed["lost"]
        and all(abs(v) <= NO_EFFECT_TOLERANCE for v in deltas.values())
    )
    return deltas, changed, no_effect


def decision_impact(
    engine: SimulationEngine,
    strategy: str,
    seed: int,
    *,
    alternatives: Callable[[AppliedDecision], Sequence[Raw | None]] | None = None,
    select: Callable[[AppliedDecision], bool] | None = None,
    continuation: Continuation = "replay",
) -> list[ImpactRow]:
    """Fork every selected decision of one mission and measure the difference.

    ``alternatives(d)`` returns the replacements to try; ``None`` in the list means "omit the
    decision". Default: omit only.
    """
    base = run_mission(engine, strategy, seed)
    rows: list[ImpactRow] = []
    for d in base.decisions:
        if select is not None and not select(d):
            continue
        for alt in alternatives(d) if alternatives else [None]:
            plan = _plan(base.decisions, d, alt, keep_after=continuation == "replay")
            resume = make_strategy(strategy, seed) if continuation == "strategy" else None
            fork = _ForkedPlay(plan=plan, fork_tick=d.tick, resume=resume)
            alt_run = run_mission(engine, fork, seed).metrics
            deltas, changed, no_effect = compare(base.metrics, alt_run)
            rows.append(
                ImpactRow(
                    strategy=base.metrics.strategy,
                    seed=seed,
                    continuation=continuation,
                    decision_sequence=d.sequence,
                    decision_tick=d.tick,
                    decision_type=str(d.inputs["type"]),
                    decision_inputs=dict(d.inputs),
                    alternative=alt,
                    baseline_outcome=base.metrics.outcome,
                    alternative_outcome=alt_run.outcome,
                    outcome_changed=alt_run.outcome != base.metrics.outcome,
                    objectives_changed=changed,
                    deltas=deltas,
                    no_effect=no_effect,
                    later_decisions_rejected=alt_run.decisions_rejected,
                )
            )
    return rows


@dataclass(slots=True)
class ImpactSummary:
    strategy: str
    decision_type: str
    alternative: str
    continuation: str
    forks: int
    outcome_changed_rate: float
    objective_changed_rate: float
    no_effect_rate: float
    mean_deltas: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


def _alt_label(alt: dict[str, Any] | None) -> str:
    if alt is None:
        return "omit"
    rest = {k: v for k, v in alt.items() if k != "type"}
    return f"{alt['type']}({', '.join(f'{k}={v}' for k, v in sorted(rest.items()))})"


def summarize_impact(rows: Iterable[ImpactRow]) -> list[ImpactSummary]:
    groups: dict[tuple[str, str, str, str], list[ImpactRow]] = defaultdict(list)
    for r in rows:
        key_inputs = {k: v for k, v in r.decision_inputs.items() if k != "type"}
        label = f"{r.decision_type}({', '.join(f'{k}={v}' for k, v in sorted(key_inputs.items()))})"
        groups[(r.strategy, label, _alt_label(r.alternative), r.continuation)].append(r)
    out = []
    for (strategy, label, alt, cont), rs in sorted(groups.items()):
        n = len(rs)
        out.append(
            ImpactSummary(
                strategy=strategy,
                decision_type=label,
                alternative=alt,
                continuation=cont,
                forks=n,
                outcome_changed_rate=sum(r.outcome_changed for r in rs) / n,
                objective_changed_rate=sum(
                    bool(r.objectives_changed["gained"] or r.objectives_changed["lost"]) for r in rs
                )
                / n,
                no_effect_rate=sum(r.no_effect for r in rs) / n,
                mean_deltas={f: sum(r.deltas[f] for r in rs) / n for f in DELTA_FIELDS},
            )
        )
    return out
