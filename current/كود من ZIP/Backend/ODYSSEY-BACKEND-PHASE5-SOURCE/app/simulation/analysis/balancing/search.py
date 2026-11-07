"""Bounded offline search over candidate GAMEPLAY-parameter configurations.

The search evaluates every candidate in a small, explicit grid with the Balancing Lab's
strategy matrix, checks each against **diagnostic envelopes** (qualitative behaviours the
Phase 3 brief asks for, expressed as pass/fail tests), and ranks candidates by

1. number of envelopes passed (more is better), then
2. distance from the shipped values (smaller is better: prefer the least change).

It never modifies the shipped scenario: a candidate exists only as balancing overrides, and the
output is a report a human reads before deciding anything. Only parameters classified as
GAMEPLAY_PARAMETER or EDUCATIONAL_ABSTRACTION in ``docs/PARAMETER_GOVERNANCE.md`` may appear in a
search space; :data:`EVIDENCE_LOCKED_PATHS` are rejected outright.

The envelopes are deliberately loose bands, not targets: the goal is a credible system, so a
candidate is never rewarded for hitting a particular percentage.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.simulation.scenarios.loader import get_scenario

from .aggregate import StrategySummary, summarize
from .overrides import OverrideError, apply_overrides, get_path
from .sweep import SweepSpec, run_sweep

# Values anchored to cited evidence (docs/SCIENCE_EVIDENCE_AUDIT.md). A search may never vary
# them: balance is built around the science, not by rewriting it.
EVIDENCE_LOCKED_PATHS = frozenset(
    {
        "life_support.o2_consumption_kg_per_crew_day",
        "life_support.co2_production_kg_per_crew_day",
        "life_support.water_use_kg_per_crew_day",
        "life_support.water_per_kg_o2",
        "life_support.water_recovery_nominal",
        "food.consumption_kg_per_crew_day",
        "environment.radiation_dose_rate_msv_h",
    }
)
# Not evidence-locked, but protected in Phase 3 (docs/PARAMETER_GOVERNANCE.md): the story's
# environment (the "last light" and the cooling sink) and scripted event timing.
PROTECTED_PATHS = EVIDENCE_LOCKED_PATHS | {
    "environment.sink_temp_c",
    "environment.solar_availability",
    "events",
    "phases",
}

PLAYER_STRATEGIES = (
    "passive",
    "survival_first",
    "science_first",
    "balanced",
    "power_conservative",
    "high_risk",
    "naive_beginner",
    "random_valid",
)
SEARCH_STRATEGIES = (
    "passive",
    "survival_first",
    "science_first",
    "balanced",
    "power_conservative",
    "high_risk",
    "naive_beginner",
    "random_valid",
    "reserve_keeper",
    "always_shelter",
    "expert",
)


@dataclass(frozen=True, slots=True)
class Envelope:
    name: str
    description: str
    check: Callable[[Mapping[str, StrategySummary]], bool]


def _rate(s: StrategySummary, objective: str) -> float:
    return s.objective_rates.get(objective, 0.0)


def _loss(s: StrategySummary) -> float:
    return s.outcome_rates["failure"] + s.outcome_rates["crew_loss"]


def _p50(s: StrategySummary, stat: str) -> float:
    return s.stats[stat].p50


ENVELOPES: tuple[Envelope, ...] = (
    Envelope(
        "passive_cannot_win",
        "Passive play never reaches full success",
        lambda m: m["passive"].success_rate == 0.0,
    ),
    Envelope(
        "balanced_strong_not_guaranteed",
        "Balanced play usually succeeds (≥ 50 %) but not automatically (≤ 98 %)",
        lambda m: 0.5 <= m["balanced"].success_rate <= 0.98,
    ),
    Envelope(
        "depletion_informative",
        "Battery depletion is not universal: balanced ≤ 50 %, survival-first ≤ 20 %, "
        "science-first depletes at least as often as balanced",
        lambda m: (
            m["balanced"].battery_depletion_rate <= 0.5
            and m["survival_first"].battery_depletion_rate <= 0.2
            and m["science_first"].battery_depletion_rate >= m["balanced"].battery_depletion_rate
        ),
    ),
    Envelope(
        "reserve_profiles_differ",
        "Median end battery: survival-first ≥ balanced ≥ science-first, with survival-first at "
        "least 0.15 above science-first",
        lambda m: (
            _p50(m["survival_first"], "battery_soc_final")
            >= _p50(m["balanced"], "battery_soc_final")
            >= _p50(m["science_first"], "battery_soc_final")
            and _p50(m["survival_first"], "battery_soc_final")
            - _p50(m["science_first"], "battery_soc_final")
            >= 0.15
        ),
    ),
    Envelope(
        "survival_protects_crew",
        "Survival-first never loses the crew and keeps crew health ≥ 0.5 in ≥ 95 % of missions",
        lambda m: (
            m["survival_first"].outcome_rates["crew_loss"] == 0.0
            and _rate(m["survival_first"], "crew_health") >= 0.95
        ),
    ),
    Envelope(
        "science_has_a_cost",
        "Science-first returns more science than survival-first and ends with less battery",
        lambda m: (
            _p50(m["science_first"], "science_points") > _p50(m["survival_first"], "science_points")
            and _p50(m["science_first"], "battery_soc_final")
            < _p50(m["survival_first"], "battery_soc_final")
        ),
    ),
    Envelope(
        "conservation_has_a_cost",
        "Power-conservative play returns less science than balanced play",
        lambda m: (
            _p50(m["power_conservative"], "science_points") < _p50(m["balanced"], "science_points")
        ),
    ),
    Envelope(
        "reckless_is_riskier",
        "High-risk play reaches full success ≥ 30 points less often than balanced play and "
        "has a higher rate of serious failure (mission failed or crew loss)",
        lambda m: (
            m["high_risk"].success_rate <= m["balanced"].success_rate - 0.3
            and _loss(m["high_risk"]) > _loss(m["balanced"])
        ),
    ),
    Envelope(
        "beginner_not_predetermined",
        "Naive play reaches at least partial success in ≥ 50 % of missions and seeds produce "
        "varied missions (distinct results ≥ 40 % of missions)",
        lambda m: (
            m["naive_beginner"].success_rate + m["naive_beginner"].outcome_rates["partial"] >= 0.5
            and m["naive_beginner"].distinct_final_states >= 0.4 * m["naive_beginner"].missions
        ),
    ),
    Envelope(
        "random_is_worse",
        "Random play succeeds at most 20 % and ≥ 30 points less often than balanced play",
        lambda m: (
            m["random_valid"].success_rate <= 0.2
            and m["random_valid"].success_rate <= m["balanced"].success_rate - 0.3
        ),
    ),
    Envelope(
        "reserves_reachable",
        "Some strategy ends with the efficiency reserves in ≥ 50 % of missions",
        lambda m: max(_rate(s, "reserves_at_end") for s in m.values()) >= 0.5,
    ),
    Envelope(
        "excellence_is_earned",
        "No player-style strategy reaches exceptional success in ≥ 90 % of missions",
        lambda m: max(m[n].outcome_rates["exceptional"] for n in PLAYER_STRATEGIES if n in m) < 0.9,
    ),
    Envelope(
        "excellence_is_reachable",
        "Some strategy or existence probe reaches exceptional success in ≥ 50 % of missions",
        lambda m: max(s.outcome_rates["exceptional"] for s in m.values()) >= 0.5,
    ),
)


@dataclass(frozen=True, slots=True)
class SearchSpace:
    """Ordered parameter → candidate values. The first value need not be the shipped one."""

    parameters: tuple[tuple[str, tuple[Any, ...]], ...]

    def validate(self) -> None:
        for path, values in self.parameters:
            clean = path.rstrip("*")
            prefixes = {".".join(clean.split(".")[:i]) for i in range(1, len(clean.split(".")) + 1)}
            hit = sorted(prefixes & PROTECTED_PATHS)
            if hit:
                kind = "EVIDENCE_LOCKED" if set(hit) & EVIDENCE_LOCKED_PATHS else "protected"
                raise OverrideError(f"{path} is {kind} ({hit[0]}) and may not be searched")
            if not values:
                raise OverrideError(f"{path}: no candidate values")

    def candidates(self) -> list[tuple[tuple[str, Any], ...]]:
        names = [p for p, _ in self.parameters]
        grids = [v for _, v in self.parameters]
        return [tuple(zip(names, combo, strict=True)) for combo in itertools.product(*grids)]


def _baseline_value(path: str) -> Any:
    """Shipped value a candidate value is compared with (1 for scale factors)."""
    if path.endswith("*"):
        return 1.0
    data = get_scenario("luna-01").model_dump(mode="json", by_alias=True)
    return get_path(data, path)


def deviation(candidate: Sequence[tuple[str, Any]]) -> float:
    """Σ |ln(new / shipped)| over numeric parameters: 0 for the shipped configuration."""
    total = 0.0
    for path, value in candidate:
        base = _baseline_value(path)
        if isinstance(value, int | float) and isinstance(base, int | float) and base and value:
            total += abs(math.log(float(value) / float(base)))
        elif value != base:
            total += 1.0
    return total


@dataclass(slots=True)
class CandidateResult:
    overrides: tuple[tuple[str, Any], ...]
    seeds: int
    passed: list[str]
    failed: list[str]
    deviation: float
    summaries: dict[str, StrategySummary] = field(default_factory=dict)

    @property
    def score(self) -> tuple[int, float]:
        return (len(self.passed), -self.deviation)

    def as_dict(self) -> dict[str, Any]:
        return {
            "overrides": dict(self.overrides),
            "seeds": self.seeds,
            "passed": self.passed,
            "failed": self.failed,
            "deviation": self.deviation,
            "strategies": {
                name: {
                    "success_rate": s.success_rate,
                    "outcome_rates": s.outcome_rates,
                    "battery_depletion_rate": s.battery_depletion_rate,
                    "objective_rates": s.objective_rates,
                    "battery_soc_final_p50": s.stats["battery_soc_final"].p50,
                    "science_points_p50": s.stats["science_points"].p50,
                    "distinct_final_states": s.distinct_final_states,
                }
                for name, s in sorted(self.summaries.items())
            },
        }


def evaluate(
    overrides: Sequence[tuple[str, Any]],
    *,
    seeds: Sequence[int],
    workers: int = 1,
    strategies: Sequence[str] = SEARCH_STRATEGIES,
) -> CandidateResult:
    spec = SweepSpec(strategies=tuple(strategies), seeds=tuple(seeds), overrides=tuple(overrides))
    result = run_sweep(spec, workers=workers)
    by_name = {s.strategy: s for s in summarize(result.rows)}
    passed = [e.name for e in ENVELOPES if e.check(by_name)]
    failed = [e.name for e in ENVELOPES if e.name not in passed]
    return CandidateResult(
        overrides=tuple(overrides),
        seeds=len(seeds),
        passed=passed,
        failed=failed,
        deviation=deviation(overrides),
        summaries=by_name,
    )


def run_search(
    space: SearchSpace,
    *,
    seeds: Sequence[int],
    refine_seeds: Sequence[int] = (),
    top: int = 5,
    workers: int = 1,
    progress: Callable[[int, int, CandidateResult], None] | None = None,
) -> tuple[list[CandidateResult], list[CandidateResult]]:
    """Stage 1: every candidate on ``seeds``. Stage 2: the ``top`` re-run on ``refine_seeds``."""
    space.validate()
    apply_overrides(get_scenario("luna-01"), [])  # scenario loads
    cands = space.candidates()
    screened: list[CandidateResult] = []
    for i, cand in enumerate(cands, 1):
        res = evaluate(cand, seeds=seeds, workers=workers)
        screened.append(res)
        if progress is not None:
            progress(i, len(cands), res)
    screened.sort(key=lambda r: r.score, reverse=True)
    refined: list[CandidateResult] = []
    if refine_seeds:
        for res in screened[:top]:
            refined.append(evaluate(res.overrides, seeds=refine_seeds, workers=workers))
        refined.sort(key=lambda r: r.score, reverse=True)
    return screened, refined


def report_markdown(
    space: SearchSpace, screened: list[CandidateResult], refined: list[CandidateResult]
) -> str:
    """Human-readable recommendation: what was searched, what passed, and why."""
    lines = ["# Balance search report", ""]
    lines.append(
        "Generated by `python -m app.simulation.analysis.balancing search`. The shipped "
        "scenario was **not** modified; candidates exist only as overrides."
    )
    lines += ["", "## Search space", ""]
    lines.append("| Parameter | Shipped | Candidates |")
    lines.append("|---|---|---|")
    for path, values in space.parameters:
        lines.append(
            f"| `{path}` | {_baseline_value(path)} | {', '.join(str(v) for v in values)} |"
        )
    lines += ["", "## Diagnostic envelopes (pass/fail, not targets)", ""]
    for e in ENVELOPES:
        lines.append(f"* `{e.name}`: {e.description}")
    final = refined or screened
    lines += [
        "",
        f"## Ranking ({len(screened)} candidates screened on {screened[0].seeds} seeds"
        + (f"; top {len(refined)} re-run on {refined[0].seeds} seeds" if refined else "")
        + ")",
        "",
        "| # | Overrides | Passed | Failed | Deviation |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(final, 1):
        ov = ", ".join(f"`{k}={v}`" for k, v in r.overrides)
        lines.append(
            f"| {i} | {ov} | {len(r.passed)}/{len(ENVELOPES)} | "
            f"{', '.join(r.failed) or '—'} | {r.deviation:.3f} |"
        )
    best = final[0]
    lines += ["", "## Recommended candidate", ""]
    lines.append(
        f"Passes {len(best.passed)} of {len(ENVELOPES)} envelopes with deviation "
        f"{best.deviation:.3f} from the shipped values (the smallest change among the "
        "candidates passing that many)."
    )
    if best.failed:
        lines.append("")
        lines.append("Envelopes it does **not** pass (a human must judge whether that matters):")
        for name in best.failed:
            desc = next(e.description for e in ENVELOPES if e.name == name)
            lines.append(f"* `{name}`: {desc}")
    lines += [
        "",
        "| Strategy | Success | Exceptional | Partial | Failed | Crew loss | "
        "Battery depleted | End SOC p50 | Science p50 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in sorted(best.summaries.items()):
        o = s.outcome_rates
        lines.append(
            f"| `{name}` | {s.success_rate:.0%} | {o['exceptional']:.0%} | {o['partial']:.0%} | "
            f"{o['failure']:.0%} | {o['crew_loss']:.0%} | {s.battery_depletion_rate:.0%} | "
            f"{s.stats['battery_soc_final'].p50:.2f} | {s.stats['science_points'].p50:.0f} |"
        )
    lines.append("")
    return "\n".join(lines)
