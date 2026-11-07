"""Future Lens: isolated, deterministic what-if projections.

For each candidate branch (a list of decisions applied *now*, then no further decisions) the
engine is run ``samples`` times over ``horizon_ticks`` on private copies of the current state.

Isolation: the caller's state is never mutated (the engine clones; tests assert hash equality).

Honesty of predictions (``knowledge_policy``):
* ``known_only`` (default) — scenario events marked ``foreseeable: false`` that have not fired
  yet are suppressed, and random draws use seeds *derived* from the mission seed, so the lens
  cannot leak the real mission's future random faults or surprise events.
* ``omniscient`` — sample 0 uses the real seed and nothing is suppressed (for debugging and
  teacher tools).

Determinism: same state + request → same result (sample seeds are derived, not random).

Confidence is an educational indicator (PROVISIONAL formula, see docs/FUTURE_LENS.md):
    score = model_factor · horizon_factor · spread_factor · knowledge_factor
    horizon_factor   = 1 / (1 + horizon / 72)
    spread_factor    = 1 − (max − min of end-of-horizon mission risk across samples)
    knowledge_factor = 0.85 if unforeseeable events were excluded, else 1.0
    model_factor     = 0.8 (simplified educational model)
    level: high ≥ 0.6 > medium ≥ 0.35 > low
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.simulation.analysis.root_cause import RootCauseTrace, trace_root_cause
from app.simulation.canonical import sha256_hex
from app.simulation.domain.decisions import DecisionInput, decision_payload
from app.simulation.domain.enums import AlertSeverity, EventKind, MissionStatus
from app.simulation.domain.events import MissionEvent
from app.simulation.domain.state import MissionState
from app.simulation.engine import rng
from app.simulation.engine.context import RunOptions
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine

KEY_METRICS = (
    "power.battery_soc",
    "thermal.habitat_temp_c",
    "life_support.oxygen_days",
    "life_support.co2_ppm",
    "life_support.water_days",
    "food.food_days",
    "crew.min_health",
    "crew.max_dose_msv",
    "science.points",
    "comms.data_downlinked_mb",
    "risk.mission",
)
# Projected only when the scenario defines them (e.g. a mission dose limit).
OPTIONAL_KEY_METRICS = ("crew.projected_dose_margin_msv",)
MODEL_FACTOR = 0.8
KNOWLEDGE_FACTOR_EXCLUDED = 0.85

KnowledgePolicy = Literal["known_only", "omniscient"]


class CandidateBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=64)
    decisions: list[DecisionInput] = Field(default_factory=list, max_length=8)


class FutureLensRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateBranch] = Field(min_length=1, max_length=4)
    include_baseline: bool = True
    horizon_ticks: int = Field(24, ge=1, le=240)
    samples: int = Field(4, ge=1, le=16)
    knowledge_policy: KnowledgePolicy = "known_only"
    explain: bool = True


class MetricProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    unit: str
    start: float
    end: float
    end_min: float
    end_max: float
    delta: float
    worst: float
    worst_tick: int


class PredictedWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    severity: AlertSeverity
    metric: str
    first_tick: int
    sample_fraction: float = Field(description="Share of samples in which it occurs")


class ObjectiveOutlook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    category: str
    status_now: str
    projected_status: str = Field(description="Status at the end of the projection (sample 0)")
    failed_fraction: float = Field(description="Share of samples in which it ends FAILED")
    achieved_fraction: float = Field(description="Share of samples in which it ends ACHIEVED")


class PredictionConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["high", "medium", "low"]
    score: float
    horizon_factor: float
    spread_factor: float
    knowledge_factor: float
    model_factor: float
    samples: int
    provisional: bool = True


class BranchPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    is_baseline: bool
    decisions: list[dict[str, Any]]
    valid: bool
    rejection: dict[str, str] | None = None
    ticks_projected: int = 0
    concludes: bool = False
    projected_outcome: str | None = None
    projected_phase: str | None = None
    metrics: list[MetricProjection] = Field(default_factory=list)
    warnings: list[PredictedWarning] = Field(default_factory=list)
    risk: dict[str, float] = Field(default_factory=dict)
    confidence: PredictionConfidence | None = None
    assumptions: list[str] = Field(default_factory=list)
    causal_explanation: list[RootCauseTrace] = Field(default_factory=list)
    vs_baseline: dict[str, float] = Field(default_factory=dict)
    new_warnings: list[str] = Field(
        default_factory=list,
        description="Alerts this candidate raises that the baseline does not (or raises later)",
    )
    objective_outlook: list[ObjectiveOutlook] = Field(default_factory=list)


class FutureLensResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_tick: int
    base_state_hash: str
    request_hash: str
    knowledge_policy: KnowledgePolicy
    excluded_events: list[str]
    predictions: list[BranchPrediction]


MAX_EXPLAINED_NEW = 5
MAX_EXPLAINED_OTHER = 3


def confidence_from_factors(
    *, horizon_factor: float, spread_factor: float, knowledge_factor: float, samples: int
) -> PredictionConfidence:
    """The confidence score and level from its factors (formula in the module docstring).

    Shared with the frontend projection (app/read_models/analysis.py), which recomputes the
    score with a constant knowledge factor so that it does not reveal whether unforeseeable
    events remain within the horizon."""
    score = MODEL_FACTOR * horizon_factor * spread_factor * knowledge_factor
    level: Literal["high", "medium", "low"] = (
        "high" if score >= 0.6 else "medium" if score >= 0.35 else "low"
    )
    return PredictionConfidence(
        level=level,
        score=score,
        horizon_factor=horizon_factor,
        spread_factor=spread_factor,
        knowledge_factor=knowledge_factor,
        model_factor=MODEL_FACTOR,
        samples=samples,
    )


@dataclass(slots=True)
class _ExplainContext:
    history: list[MissionState]
    events: list[MissionEvent]
    decision_info: dict[str, dict[str, Any]]
    start_tick: int


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


class FutureLens:
    def __init__(self, engine: SimulationEngine) -> None:
        self.engine = engine

    def excluded_events(self, state: MissionState, policy: KnowledgePolicy) -> list[str]:
        if policy == "omniscient":
            return []
        return sorted(
            e.id
            for e in self.engine.scenario.events
            if not e.foreseeable and state.event_fire_counts.get(e.id, 0) < e.max_fires
        )

    def predict(self, state: MissionState, request: FutureLensRequest) -> FutureLensResult:
        """Project every branch. ``state`` is never mutated."""
        excluded = self.excluded_events(state, request.knowledge_policy)
        branches: list[tuple[CandidateBranch, bool]] = []
        if request.include_baseline:
            branches.append((CandidateBranch(label="baseline", decisions=[]), True))
        branches.extend((c, False) for c in request.candidates)

        computed = [
            self._branch(state, branch, is_base, request, excluded) for branch, is_base in branches
        ]
        predictions = [p for p, _ in computed]
        baseline = next((p for p in predictions if p.is_baseline and p.valid), None)
        base_first = {w.alert_id: w.first_tick for w in baseline.warnings} if baseline else {}
        if baseline is not None:
            base_end = {m.metric: m.end for m in baseline.metrics}
            for p in predictions:
                if p is not baseline and p.valid:
                    p.vs_baseline = {
                        m.metric: m.end - base_end[m.metric]
                        for m in p.metrics
                        if m.metric in base_end
                    }
                    p.new_warnings = [
                        w.alert_id
                        for w in p.warnings
                        if w.alert_id not in base_first or w.first_tick < base_first[w.alert_id]
                    ]
        if request.explain:
            for p, ctx in computed:
                if ctx is not None and p.warnings:
                    self._explain(p, ctx, request)
        return FutureLensResult(
            base_tick=state.tick,
            base_state_hash=state.state_hash(),
            request_hash=sha256_hex(
                {"state": state.state_hash(), "request": request.model_dump(mode="json")}
            ),
            knowledge_policy=request.knowledge_policy,
            excluded_events=excluded,
            predictions=predictions,
        )

    # --------------------------------------------------------------------------------------
    def _branch(
        self,
        state: MissionState,
        branch: CandidateBranch,
        is_baseline: bool,
        req: FutureLensRequest,
        excluded: list[str],
    ) -> tuple[BranchPrediction, _ExplainContext | None]:
        eng = self.engine
        payloads = [decision_payload(d) for d in branch.decisions]
        pred = BranchPrediction(
            label=branch.label, is_baseline=is_baseline, decisions=payloads, valid=True
        )
        if state.status == MissionStatus.CONCLUDED:
            pred.valid = False
            pred.rejection = {"code": "mission_concluded", "message": "mission has concluded"}
            return pred, None

        start = state.clone()
        decision_info: dict[str, dict[str, Any]] = {}
        try:
            for i, d in enumerate(branch.decisions):
                did = f"lens:{branch.label}:{i}"
                start = eng.apply_decision(start, d, did).state
                decision_info[did] = {
                    "decision_type": d.type,
                    "inputs": payloads[i],
                    "phase": state.phase,
                    "sequence": i + 1,
                }
        except DecisionRejectedError as exc:
            pred.valid = False
            pred.rejection = {"code": exc.code, "message": exc.message}
            return pred, None

        horizon = min(req.horizon_ticks, max(0, eng.scenario.time.max_ticks - start.tick))
        suppressed = frozenset(excluded)
        runs = []
        for i in range(req.samples):
            if req.knowledge_policy == "omniscient" and i == 0:
                seed = None
            else:
                seed = rng.derive_seed(state.seed, f"lens:{state.tick}:{i}")
            opts = RunOptions(rng_seed=seed, suppressed_events=suppressed)
            runs.append(eng.advance(start, horizon, opts, record_history=True))

        primary = runs[0]
        histories = [[start, *(r.history or [])] for r in runs]
        pred.ticks_projected = primary.ticks_run
        pred.concludes = primary.state.status == MissionStatus.CONCLUDED
        pred.projected_outcome = primary.state.outcome.code if primary.state.outcome else None
        pred.projected_phase = primary.state.phase

        for metric in (*KEY_METRICS, *OPTIONAL_KEY_METRICS):
            if not eng.metrics.has(metric):
                continue
            spec = eng.metrics.spec(metric)
            ends = [eng.metrics.value(metric, h[-1]) for h in histories]
            series = [(s.tick, eng.metrics.value(metric, s)) for s in histories[0]]
            sev = spec.severity
            if sev is not None and sev.direction == "above":
                worst_tick, worst = max(series, key=lambda tv: (tv[1], -tv[0]))
            else:
                worst_tick, worst = min(series, key=lambda tv: (tv[1], tv[0]))
            begin = eng.metrics.value(metric, start)
            end = _median(ends)
            pred.metrics.append(
                MetricProjection(
                    metric=metric,
                    unit=spec.unit,
                    start=begin,
                    end=end,
                    end_min=min(ends),
                    end_max=max(ends),
                    delta=end - begin,
                    worst=worst,
                    worst_tick=worst_tick,
                )
            )

        rules = {a.id: a for a in eng.scenario.alerts}
        seen: dict[str, list[int]] = {}
        already = set(start.alerts)
        for r in runs:
            first: dict[str, int] = {}
            for e in r.events:
                if (
                    e.kind in (EventKind.ALERT_RAISED, EventKind.RESOURCE_WARNING)
                    and e.key not in already
                    and e.key not in first
                ):
                    first[e.key] = e.tick
            for k, t in first.items():
                seen.setdefault(k, []).append(t)
        for alert_id in sorted(seen, key=lambda k: (min(seen[k]), k)):
            rule = rules[alert_id]
            pred.warnings.append(
                PredictedWarning(
                    alert_id=alert_id,
                    severity=rule.severity,
                    metric=rule.metric,
                    first_tick=min(seen[alert_id]),
                    sample_fraction=len(seen[alert_id]) / len(runs),
                )
            )

        risks_end = [eng.metrics.value("risk.mission", h[-1]) for h in histories]
        risk_series = [eng.metrics.value("risk.mission", s) for s in histories[0]]
        pred.risk = {
            "end_risk": _median(risks_end),
            "peak_risk": max(risk_series),
            "peak_risk_tick": float(histories[0][risk_series.index(max(risk_series))].tick),
            "critical_warning_fraction": max(
                (w.sample_fraction for w in pred.warnings if w.severity == AlertSeverity.CRITICAL),
                default=0.0,
            ),
        }

        pred.confidence = confidence_from_factors(
            horizon_factor=1.0 / (1.0 + horizon / 72.0),
            spread_factor=_clamp(1.0 - (max(risks_end) - min(risks_end))),
            knowledge_factor=KNOWLEDGE_FACTOR_EXCLUDED if excluded else 1.0,
            samples=len(runs),
        )

        pred.assumptions = [
            "No further decisions are made after the candidate decisions.",
            f"Projection covers {primary.ticks_run} ticks "
            f"({primary.ticks_run * eng.scenario.time.tick_hours:g} h) from tick {state.tick}.",
            f"Random faults are sampled with {len(runs)} independent derived seeds; "
            "end values are medians across samples.",
            "The simulation is a simplified educational model (see SIMULATION_MODEL.md).",
        ]
        if excluded:
            pred.assumptions.append(
                "Unforeseeable scenario events are not anticipated: " + ", ".join(excluded)
            )
        if horizon < req.horizon_ticks:
            pred.assumptions.append("Horizon clipped to the scheduled end of the mission.")

        pred.objective_outlook = self._objective_outlook(start, histories)
        ctx = _ExplainContext(
            history=histories[0],
            events=list(primary.events),
            decision_info=decision_info,
            start_tick=start.tick,
        )
        return pred, ctx

    def _objective_outlook(
        self, start: MissionState, histories: list[list[MissionState]]
    ) -> list[ObjectiveOutlook]:
        out: list[ObjectiveOutlook] = []
        for spec in self.engine.scenario.objectives:
            ends = [h[-1].objectives[spec.id].status.value for h in histories]
            out.append(
                ObjectiveOutlook(
                    objective=spec.id,
                    category=spec.effective_category,
                    status_now=start.objectives[spec.id].status.value,
                    projected_status=ends[0],
                    failed_fraction=sum(1 for e in ends if e == "failed") / len(ends),
                    achieved_fraction=sum(1 for e in ends if e == "achieved") / len(ends),
                )
            )
        return out

    def _explain(
        self, pred: BranchPrediction, ctx: _ExplainContext, req: FutureLensRequest
    ) -> None:
        """Trace the warnings this branch introduces first, then the earliest others.

        Only warnings that actually occur in sample 0 (whose history is traced) are explained,
        so every explanation is grounded in a recorded projection, never inferred.
        """
        new = set(pred.new_warnings)
        # First tick each alert was raised in sample 0. A warning's ``first_tick`` is the
        # earliest across samples, so sample 0 may raise it a little later; it is traced at the
        # tick sample 0 actually raised it.
        raised_first: dict[str, int] = {}
        for e in ctx.events:
            if e.kind in (EventKind.ALERT_RAISED, EventKind.RESOURCE_WARNING):
                raised_first.setdefault(e.key, e.tick)
        ordered = [w for w in pred.warnings if w.alert_id in new] + [
            w for w in pred.warnings if w.alert_id not in new
        ]
        explained_new = explained_other = 0
        for w in ordered:
            is_new = w.alert_id in new
            if (is_new and explained_new >= MAX_EXPLAINED_NEW) or (
                not is_new and explained_other >= MAX_EXPLAINED_OTHER
            ):
                continue
            raised = raised_first.get(w.alert_id)
            if raised is None:  # not raised in the traced sample: nothing grounded to explain
                continue
            target_tick = min(raised + 1, ctx.history[-1].tick)
            pred.causal_explanation.append(
                trace_root_cause(
                    self.engine,
                    ctx.history,
                    w.metric,
                    target_tick,
                    start_tick=ctx.start_tick,
                    lookback_ticks=req.horizon_ticks,
                    decision_info=ctx.decision_info,
                )
            )
            if is_new:
                explained_new += 1
            else:
                explained_other += 1
