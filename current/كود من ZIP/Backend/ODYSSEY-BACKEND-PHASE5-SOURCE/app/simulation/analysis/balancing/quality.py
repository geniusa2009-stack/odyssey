"""Quality measurements for Future Lens and the Black Box (measure, don't redesign).

Future Lens: determinism, isolation, sample stability, surprise-event blindness, whether
candidate decisions produce distinguishable predictions, confidence behaviour, and whether
causal explanations name the candidate decision when it is the cause.

Black Box: across many failures, whether traces are stable, follow declared dependencies,
respect causal order, keep decision context, avoid blaming decisions that counterfactual replay
shows had no (or a beneficial) effect, and explain the failure at all.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.future_lens import (
    BranchPrediction,
    FutureLens,
    FutureLensRequest,
)
from app.simulation.analysis.reconstruct import counterfactual_factory, reconstruct
from app.simulation.analysis.root_cause import RootCauseTrace
from app.simulation.domain.decisions import parse_decision
from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import DecisionRejectedError, SimulationEngine
from app.simulation.replay.ledger import GENESIS_HASH, DecisionRecord, record_decision

from .runner import run_mission

# Scale used to call two predictions "nearly identical" (absolute, in each metric's unit).
INDISTINGUISHABLE = {
    "power.battery_soc": 0.01,
    "thermal.habitat_temp_c": 0.1,
    "life_support.oxygen_days": 0.05,
    "life_support.co2_ppm": 50.0,
    "life_support.water_days": 0.05,
    "food.food_days": 0.05,
    "crew.min_health": 0.005,
    "crew.max_dose_msv": 0.1,
    "science.points": 0.5,
    "comms.data_downlinked_mb": 5.0,
    "risk.mission": 0.01,
}
CANDIDATES: tuple[dict[str, Any], ...] = (
    {"type": "set_subsystem_mode", "subsystem": "thermal_heater", "mode": "eco"},
    {"type": "set_subsystem_mode", "subsystem": "comms", "mode": "eco"},
    {"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "eco"},
    {"type": "set_subsystem_mode", "subsystem": "oxygen_generation", "mode": "off"},
    {"type": "set_subsystem_mode", "subsystem": "water_recovery", "mode": "off"},
    {"type": "set_subsystem_mode", "subsystem": "habitat_core", "mode": "eco"},
    {"type": "set_subsystem_mode", "subsystem": "rover_charger", "mode": "off"},
    {"type": "set_thermal_setpoint", "target_c": 15.0},
    {"type": "set_ration_level", "level": 0.8},
    {"type": "set_crew_location", "location": "shelter"},
)


def _label(raw: dict[str, Any]) -> str:
    rest = "_".join(str(v) for k, v in sorted(raw.items()) if k != "type")
    return f"{raw['type']}:{rest}"[:64]


@dataclass(slots=True)
class LensCase:
    seed: int
    tick: int
    candidate: str
    valid: bool
    distinguishable: bool
    max_abs_delta: dict[str, float]
    new_warnings: list[str]
    explained_by_candidate: bool | None
    confidence: float | None
    level: str | None
    # Phase 3: every signal the lens returns, not only end-of-horizon resource values.
    signals: list[str] = field(default_factory=list)

    @property
    def distinguishable_any(self) -> bool:
        return bool(self.signals)


@dataclass(slots=True)
class LensQuality:
    states: int = 0
    predictions: int = 0
    deterministic: bool = True
    isolated: bool = True
    cases: list[LensCase] = field(default_factory=list)
    sample_stability: list[dict[str, Any]] = field(default_factory=list)
    surprise: list[dict[str, Any]] = field(default_factory=list)
    confidence_by_horizon: list[dict[str, Any]] = field(default_factory=list)
    calibration: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        valid = [c for c in self.cases if c.valid]
        indist = Counter(c.candidate for c in valid if not c.distinguishable)
        indist_any = Counter(c.candidate for c in valid if not c.distinguishable_any)
        per_candidate = Counter(c.candidate for c in valid)
        signal_counts = Counter(sig for c in valid for sig in c.signals)
        explained = [
            c.explained_by_candidate for c in valid if c.explained_by_candidate is not None
        ]
        return {
            "states": self.states,
            "predictions": self.predictions,
            "deterministic": self.deterministic,
            "isolated": self.isolated,
            "candidate_cases": len(valid),
            "indistinguishable_rate": (sum(indist.values()) / len(valid)) if valid else 0.0,
            "indistinguishable_by_candidate": {
                k: indist[k] / per_candidate[k] for k in sorted(per_candidate)
            },
            "indistinguishable_any_signal_rate": (
                (sum(indist_any.values()) / len(valid)) if valid else 0.0
            ),
            "indistinguishable_any_signal_by_candidate": {
                k: indist_any[k] / per_candidate[k] for k in sorted(per_candidate)
            },
            "signal_counts": dict(sorted(signal_counts.items())),
            "causal_explanation_names_candidate_rate": (
                sum(explained) / len(explained) if explained else None
            ),
            "cases_with_new_warnings": len(explained),
            "sample_stability": self.sample_stability,
            "surprise": self.surprise,
            "confidence_by_horizon": self.confidence_by_horizon,
            "calibration": self.calibration,
        }


def _lens_signals(
    p: BranchPrediction,
    end_state_differs: bool,
    base_outlook: dict[str, str],
    base_worst: dict[str, float],
) -> list[str]:
    """Which kinds of difference from the baseline a prediction shows (empty = none).

    ``resources_end``: an end-of-horizon value differs beyond :data:`INDISTINGUISHABLE`;
    ``resources_worst``: the worst value inside the horizon differs beyond the same tolerance;
    ``warnings``: the candidate raises an alert the baseline does not (or raises it earlier);
    ``objectives``: an objective is projected to end in a different status.
    """
    out: list[str] = []
    if end_state_differs:
        out.append("resources_end")
    if any(
        m.metric in base_worst
        and m.metric in INDISTINGUISHABLE
        and abs(m.worst - base_worst[m.metric]) > INDISTINGUISHABLE[m.metric]
        for m in p.metrics
    ):
        out.append("resources_worst")
    if p.new_warnings:
        out.append("warnings")
    if any(base_outlook.get(o.objective) != o.projected_status for o in p.objective_outlook):
        out.append("objectives")
    return out


def _sample_states(
    engine: SimulationEngine, seeds: Sequence[int], ticks: Sequence[int]
) -> list[MissionState]:
    states = []
    for seed in seeds:
        run = run_mission(engine, "balanced", seed)
        # Re-create the effective state at each tick by replaying the recorded decisions.
        from app.simulation.replay.replay import replay

        res = replay(
            engine,
            run.initial,
            [d.to_replay() for d in run.decisions],
            run.final.tick,
            record_history=True,
        )
        states += [
            res.history[t]
            for t in ticks
            if t < len(res.history) and res.history[t].status.value == "active"
        ]
    return states


def measure_future_lens(
    engine: SimulationEngine,
    *,
    seeds: Sequence[int] = (1, 2, 3),
    ticks: Sequence[int] = (20, 60, 100, 115, 135, 155, 175, 200),
    horizon: int = 24,
    samples: int = 4,
) -> LensQuality:
    lens = FutureLens(engine)
    q = LensQuality()
    states = _sample_states(engine, seeds, ticks)
    q.states = len(states)
    for st in states:
        before = st.state_hash()
        req = FutureLensRequest.model_validate(
            {
                "candidates": [{"label": _label(c), "decisions": [c]} for c in CANDIDATES[:4]],
                "horizon_ticks": horizon,
                "samples": samples,
            }
        )
        req2 = FutureLensRequest.model_validate(
            {
                "candidates": [{"label": _label(c), "decisions": [c]} for c in CANDIDATES[4:8]],
                "horizon_ticks": horizon,
                "samples": samples,
            }
        )
        req3 = FutureLensRequest.model_validate(
            {
                "candidates": [{"label": _label(c), "decisions": [c]} for c in CANDIDATES[8:]],
                "horizon_ticks": horizon,
                "samples": samples,
            }
        )
        results = [lens.predict(st, r) for r in (req, req2, req3)]
        again = lens.predict(st, req)
        q.deterministic &= again.model_dump(mode="json") == results[0].model_dump(mode="json")
        q.isolated &= st.state_hash() == before
        q.predictions += sum(len(r.predictions) for r in results) + len(again.predictions)
        baseline = results[0].predictions[0]
        base_warn = {w.alert_id for w in baseline.warnings}
        base_outlook = {o.objective: o.projected_status for o in baseline.objective_outlook}
        base_worst = {m.metric: m.worst for m in baseline.metrics}
        for r in results:
            for p in r.predictions:
                if p.is_baseline:
                    continue
                if not p.valid:
                    q.cases.append(
                        LensCase(st.seed, st.tick, p.label, False, False, {}, [], None, None, None)
                    )
                    continue
                deltas = {m: abs(v) for m, v in p.vs_baseline.items()}
                distinct = any(deltas.get(m, 0.0) > tol for m, tol in INDISTINGUISHABLE.items())
                new = sorted({w.alert_id for w in p.warnings} - base_warn)
                explained: bool | None = None
                if new:
                    node = f"decision:lens:{p.label}:0"
                    explained = any(node in {n.id for n in t.nodes} for t in p.causal_explanation)
                c = p.confidence
                signals = _lens_signals(p, distinct, base_outlook, base_worst)
                q.cases.append(
                    LensCase(
                        st.seed,
                        st.tick,
                        p.label,
                        True,
                        distinct,
                        deltas,
                        new,
                        explained,
                        c.score if c else None,
                        c.level if c else None,
                        signals,
                    )
                )
    # Sample stability: does the median end state settle as samples grow?
    for st in states[:: max(1, len(states) // 6)]:
        row: dict[str, Any] = {"seed": st.seed, "tick": st.tick}
        for n in (1, 4, 16):
            p = lens.predict(
                st,
                FutureLensRequest.model_validate(
                    {
                        "candidates": [{"label": "noop", "decisions": []}],
                        "include_baseline": False,
                        "horizon_ticks": 48,
                        "samples": n,
                    }
                ),
            ).predictions[0]
            row[f"end_risk_samples_{n}"] = p.risk["end_risk"]
            row[f"risk_spread_samples_{n}"] = next(
                m.end_max - m.end_min for m in p.metrics if m.metric == "risk.mission"
            )
        q.sample_stability.append(row)
    # Surprise blindness and calibration around the scheduled unforeseeable events.
    for st in states:
        for policy_pair in (("known_only", "omniscient"),):
            preds = {
                pol: lens.predict(
                    st,
                    FutureLensRequest.model_validate(
                        {
                            "candidates": [{"label": "noop", "decisions": []}],
                            "include_baseline": False,
                            "horizon_ticks": horizon,
                            "samples": samples,
                            "knowledge_policy": pol,
                            "explain": False,
                        }
                    ),
                )
                for pol in policy_pair
            }
            known, omni = (preds[p].predictions[0] for p in policy_pair)
            truth = {m.metric: m.end for m in omni.metrics}  # sample 0 = the real future
            err = {m.metric: abs(m.end - truth[m.metric]) for m in known.metrics}
            hidden = [
                e
                for e in preds["known_only"].excluded_events
                if any(
                    ev.id == e
                    and getattr(ev.trigger, "at_tick", -1) is not None
                    and st.tick <= getattr(ev.trigger, "at_tick", -1) < st.tick + horizon
                    for ev in engine.scenario.events
                )
            ]
            q.surprise.append(
                {
                    "seed": st.seed,
                    "tick": st.tick,
                    "hidden_events_in_horizon": hidden,
                    "abs_error": {
                        k: err[k]
                        for k in (
                            "crew.max_dose_msv",
                            "comms.data_downlinked_mb",
                            "life_support.water_days",
                            "risk.mission",
                        )
                    },
                }
            )
            if known.confidence is not None:
                q.calibration.append(
                    {
                        "level": known.confidence.level,
                        "score": known.confidence.score,
                        "risk_abs_error": err["risk.mission"],
                        "hidden_event": bool(hidden),
                    }
                )
    st = states[len(states) // 2]
    for h in (6, 24, 72, 144):
        p = lens.predict(
            st,
            FutureLensRequest.model_validate(
                {
                    "candidates": [{"label": "noop", "decisions": []}],
                    "include_baseline": False,
                    "horizon_ticks": h,
                    "samples": samples,
                    "explain": False,
                }
            ),
        ).predictions[0]
        assert p.confidence is not None
        q.confidence_by_horizon.append(
            {
                "horizon": h,
                "ticks_projected": p.ticks_projected,
                "score": p.confidence.score,
                "level": p.confidence.level,
            }
        )
    return q


# ------------------------------------------------------------------------------ Black Box
@dataclass(slots=True)
class FailureCase:
    name: str
    engine: SimulationEngine
    initial: MissionState
    records: list[DecisionRecord]
    final: MissionState


def _record_plan(
    engine: SimulationEngine, seed: int, plan: dict[int, list[dict[str, Any]]], name: str
) -> FailureCase:
    initial = engine.initial_state(seed)
    records: list[DecisionRecord] = []
    state, prev = initial, GENESIS_HASH
    while state.status.value == "active":
        for raw in plan.get(state.tick, []):
            try:
                rec, res = record_decision(
                    engine,
                    state,
                    parse_decision(raw),
                    session_id="q",
                    timeline_id=name,
                    sequence=len(records) + 1,
                    prev_record_hash=prev,
                )
            except DecisionRejectedError:
                continue
            records.append(rec)
            prev, state = rec.record_hash, res.state
        state = engine.step(state).state
    return FailureCase(name, engine, initial, records, state)


def strategy_failures(
    engine: SimulationEngine,
    strategy: str,
    seeds: Sequence[int],
    limit: int,
    *,
    classes: Sequence[str] = ("crew_loss", "failure"),
) -> list[FailureCase]:
    out = []
    for seed in seeds:
        run = run_mission(engine, strategy, seed)
        if run.metrics.outcome_class not in classes:
            continue
        plan: dict[int, list[dict[str, Any]]] = {}
        for d in run.decisions:
            plan.setdefault(d.tick, []).append(dict(d.inputs))
        out.append(_record_plan(engine, seed, plan, f"{strategy}:{seed}"))
        if len(out) >= limit:
            break
    return out


@dataclass(slots=True)
class BlackBoxCaseResult:
    name: str
    outcome: str
    final_tick: int
    traces: int
    failure_trace_roots: list[str]
    decision_roots: int
    decision_verdicts: dict[str, int]
    irrelevant_blame: int
    unexplained: bool
    undeclared_edges: int
    order_violations: int
    cyclic_chains: int
    missing_context: int
    stable: bool
    decisions_in_ledger: int
    analysis_chains: int = 0
    analysis_traced: int = 0
    analysis_omission: int = 0
    analysis_untraced: int = 0
    analysis_blamed_decisions: int = 0
    analysis_on_path_no_effect: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


def _check_trace(engine: SimulationEngine, t: RootCauseTrace) -> tuple[int, int, int, int]:
    declared = {(f"metric:{e.source}", f"metric:{e.target}") for e in engine.graph.edges}
    nodes = {n.id: n for n in t.nodes}
    undeclared = sum(
        1
        for e in t.edges
        if e.source.startswith("metric:") and (e.source, e.target) not in declared
    )
    order = sum(
        1
        for e in t.edges
        if e.source.startswith("metric:")
        and e.evidence.get("source_onset_tick", 0) > e.evidence.get("target_anchor_tick", 10**9)
    )
    cyclic = sum(1 for c in t.chains if len(c) != len(set(c)))
    missing = sum(
        1
        for n in nodes.values()
        if n.kind == "decision" and not {"decision_type", "inputs", "sequence"} <= set(n.details)
    )
    return undeclared, order, cyclic, missing


def assess_black_box(case: FailureCase) -> BlackBoxCaseResult:
    eng = case.engine
    record = reconstruct(eng, case.initial, case.records, case.final.tick)
    cf = counterfactual_factory(eng, case.initial, case.records, case.final.tick)
    report = build_black_box(eng, record, counterfactual=cf)
    again = build_black_box(eng, record, counterfactual=cf)
    verdicts: Counter[str] = Counter()
    irrelevant = undeclared = order = cyclic = missing = 0
    decision_roots = 0
    for t in report.causal_traces:
        u, o, c, m = _check_trace(eng, t)
        undeclared, order, cyclic, missing = undeclared + u, order + o, cyclic + c, missing + m
        for n in t.nodes:
            if n.kind == "decision" and n.id in t.roots:
                decision_roots += 1
                v = n.details.get("counterfactual", {}).get("verdict", "not_checked")
                verdicts[v] += 1
                irrelevant += v in ("no_effect", "decision_improved_target")
    analysis = report.outcome_analysis
    chains = analysis.chains if analysis is not None else []
    tier = analysis.tier if analysis is not None else None
    failing = tier in ("critical_failure", "mission_failed", "partial")
    explained_chains = [
        c
        for c in chains
        if (c.kind == "traced" and (c.root_decisions or c.other_roots or c.on_path_no_effect))
        or (c.kind == "omission" and c.facts)
    ]
    unexplained = failing and not explained_chains
    first = None
    if chains and chains[0].trace_index is not None:
        first = report.causal_traces[chains[0].trace_index]
    elif report.causal_traces:
        first = report.causal_traces[0]
    roots = list(first.roots) if first and failing else []
    return BlackBoxCaseResult(
        name=case.name,
        outcome=report.outcome.code if report.outcome else "in_progress",
        final_tick=report.final_tick,
        traces=len(report.causal_traces),
        failure_trace_roots=roots,
        decision_roots=decision_roots,
        decision_verdicts=dict(sorted(verdicts.items())),
        irrelevant_blame=irrelevant,
        unexplained=unexplained,
        undeclared_edges=undeclared,
        order_violations=order,
        cyclic_chains=cyclic,
        missing_context=missing,
        stable=report.model_dump(mode="json") == again.model_dump(mode="json"),
        decisions_in_ledger=len(case.records),
        analysis_chains=len(chains),
        analysis_traced=sum(1 for c in chains if c.kind == "traced"),
        analysis_omission=sum(1 for c in chains if c.kind == "omission"),
        analysis_untraced=sum(1 for c in chains if c.kind == "untraced"),
        analysis_blamed_decisions=sum(len(c.root_decisions) for c in chains),
        analysis_on_path_no_effect=sum(len(c.on_path_no_effect) for c in chains),
    )


def trace_fingerprint(t: RootCauseTrace) -> dict[str, Any]:
    """Stable, id-free summary of a trace for regression fixtures."""

    def norm(node: str) -> str:
        return "decision" if node.startswith("decision:") else node

    return {
        "target_metric": t.target_metric,
        "target_tick": t.target_tick,
        "roots": sorted({norm(r) for r in t.roots}),
        "chains": sorted({" -> ".join(norm(n) for n in c) for c in t.chains}),
    }


InjectedCase = Callable[[], FailureCase]


def injected_failures() -> list[FailureCase]:
    """Failures with a known cause, built from scenario data + decisions (no engine changes)."""
    from app.simulation.analysis.balancing.overrides import apply_overrides
    from app.simulation.scenarios.loader import get_scenario

    base = get_scenario("luna-01")
    quiet = {"degradation.components.rover.fault_probability_per_tick": 0.0}

    def eng(overrides: dict[str, Any]) -> SimulationEngine:
        return SimulationEngine(apply_overrides(base, {**quiet, **overrides}))

    luna = SimulationEngine(base)
    return [
        _record_plan(
            luna,
            42,
            {5: [{"type": "set_subsystem_mode", "subsystem": "co2_scrubber", "mode": "off"}]},
            "scrubber_off",
        ),
        _record_plan(
            eng({"life_support.initial_water_kg": 12.0, "life_support.initial_oxygen_kg": 4.0}),
            7,
            {1: [{"type": "set_subsystem_mode", "subsystem": "water_recovery", "mode": "off"}]},
            "water_off_low_reserves",
        ),
        _record_plan(
            eng({"life_support.initial_oxygen_kg": 6.0}),
            7,
            {3: [{"type": "set_subsystem_mode", "subsystem": "oxygen_generation", "mode": "off"}]},
            "oxygen_generation_off",
        ),
        _record_plan(
            eng({"events.solar_particle_event.effects.0.value": 400.0}),
            7,
            {},
            "extreme_solar_particle_event",
        ),
        # Cold + half rations alone are survivable over 10 days since LUNA-01 v0.2.0 (health
        # ends near 0.3), so this case limits food (it runs out around day 6.6) and neutralises
        # the solar particle event, keeping it a decision-driven crew loss with an irrelevant
        # decision mixed in.
        _record_plan(
            eng(
                {
                    "food.initial_food_kg": 20.0,
                    "events.solar_particle_event.effects.0.value": 1.0,
                }
            ),
            9,
            {
                2: [
                    {"type": "set_thermal_setpoint", "target_c": 10.0},
                    {"type": "set_ration_level", "level": 0.5},
                ],
                30: [{"type": "set_subsystem_mode", "subsystem": "comms", "mode": "eco"}],
            },
            "cold_and_hungry_with_irrelevant_comms",
        ),
    ]


# ------------------------------------------------------------------------------ profiles
@dataclass(slots=True)
class ProfileSeparation:
    """Engineering Profile dimensions per strategy and how far apart strategies are."""

    seeds: int
    means: dict[str, dict[str, float]]
    spread: dict[str, dict[str, float]]
    distances: dict[str, dict[str, float]]
    nearest: dict[str, tuple[str, float]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "means": self.means,
            "spread": self.spread,
            "distances": self.distances,
            "nearest": {k: {"strategy": v[0], "distance": v[1]} for k, v in self.nearest.items()},
        }


def measure_profiles(
    engine: SimulationEngine, strategies: Sequence[str], seeds: Sequence[int]
) -> ProfileSeparation:
    """Profiles derived from behaviour only (ledger + reconstructed history), never names."""
    from app.simulation.analysis.profile import DIMENSIONS, build_profile

    scores: dict[str, list[dict[str, float]]] = {}
    for strategy in strategies:
        for seed in seeds:
            run = run_mission(engine, strategy, seed)
            plan: dict[int, list[dict[str, Any]]] = {}
            for d in run.decisions:
                plan.setdefault(d.tick, []).append(dict(d.inputs))
            case = _record_plan(engine, seed, plan, f"{strategy}:{seed}")
            record = reconstruct(engine, case.initial, case.records, case.final.tick)
            prof = build_profile(engine, record)
            scores.setdefault(strategy, []).append({d.dimension: d.score for d in prof.dimensions})
    means = {
        s: {d: sum(r[d] for r in rows) / len(rows) for d in DIMENSIONS}
        for s, rows in scores.items()
    }
    spread = {
        s: {d: max(r[d] for r in rows) - min(r[d] for r in rows) for d in DIMENSIONS}
        for s, rows in scores.items()
    }

    def dist(a: str, b: str) -> float:
        return float(sum((means[a][d] - means[b][d]) ** 2 for d in DIMENSIONS) ** 0.5)

    names = sorted(means)
    distances = {a: {b: dist(a, b) for b in names if b != a} for a in names}
    nearest = {a: min(distances[a].items(), key=lambda kv: (kv[1], kv[0])) for a in names}
    return ProfileSeparation(len(seeds), means, spread, distances, nearest)
