"""Balancing Lab CLI.

Examples::

    python -m app.simulation.analysis.balancing --scenario luna01 --strategy balanced --seeds 100
    python -m app.simulation.analysis.balancing sweep --strategy all --seeds 500 --workers 2 \\
        --format json --output reports/sweep.json
    python -m app.simulation.analysis.balancing sweep --strategy balanced \\
        --set power.battery.capacity_kwh=200 --format csv --output reports/missions.csv
    python -m app.simulation.analysis.balancing sensitivity \\
        --parameter power.solar_rated_kw --values 11,13,15,17,20 --seeds 50
    python -m app.simulation.analysis.balancing ablation --seeds 50
    python -m app.simulation.analysis.balancing impact --strategy balanced --seeds 10
    python -m app.simulation.analysis.balancing diagnose --seeds 100 --output-dir reports/
    python -m app.simulation.analysis.balancing quality --output reports/quality.json
    python -m app.simulation.analysis.balancing search --seeds 12 --refine-seeds 100 \
        --param power.battery.capacity_kwh=160,200,240 --output-dir reports/search
    python -m app.simulation.analysis.balancing trajectory --strategy balanced --seed 1 \
        --format csv --output reports/balanced-1.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.reconstruct import reconstruct
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario

from . import diagnostics
from .aggregate import format_summary, summarize
from .impact import decision_impact, summarize_impact
from .overrides import apply_overrides, parse_override
from .report import mission_rows_csv, summary_rows_csv, sweep_json, write
from .sensitivity import DEFAULT_PARAMETERS, run_ablation, run_sensitivity
from .strategies import DIAGNOSTIC_PROBES, PROBE_STRATEGIES
from .sweep import (
    SweepSpec,
    default_workers,
    resolve_scenario_id,
    run_sweep,
    seeds_from,
    strategies_or_all,
)

COMMANDS = (
    "sweep",
    "sensitivity",
    "ablation",
    "impact",
    "diagnose",
    "quality",
    "bench",
    "search",
    "trajectory",
    "audit",
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _indented(msg: str) -> None:
    log(f"  {msg}")


def _strategies(values: Sequence[str] | None) -> tuple[str, ...]:
    names: list[str] = []
    for v in values or ["balanced"]:
        names += [n for n in v.split(",") if n]
    return strategies_or_all(names)


def _common(p: argparse.ArgumentParser, *, strategy_default: str | None = "balanced") -> None:
    p.add_argument("--scenario", default="luna-01", help="scenario id (luna-01 or luna01)")
    p.add_argument(
        "--strategy",
        action="append",
        help=f"strategy name(s), comma-separated or repeated, or 'all' "
        f"(default {strategy_default}); choices: "
        f"{', '.join([*PROBE_STRATEGIES, *DIAGNOSTIC_PROBES])}",
    )
    p.add_argument("--seeds", type=int, default=50, help="number of seeds (default 50)")
    p.add_argument("--start-seed", type=int, default=1, help="first seed (default 1)")
    p.add_argument(
        "--workers",
        type=int,
        default=default_workers(),
        help="worker processes (default: CPU count, max 8)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.simulation.analysis.balancing",
        description="ODYSSEY Balancing Lab (backend-only analysis)",
    )
    sub = parser.add_subparsers(dest="command")

    sw = sub.add_parser("sweep", help="run strategies × seeds and report distributions")
    _common(sw)
    sw.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="scenario parameter override (repeatable)",
    )
    sw.add_argument("--suppress-event", action="append", default=[], metavar="EVENT_ID")
    sw.add_argument("--strict", action="store_true", help="check state invariants every tick")
    sw.add_argument("--format", choices=("text", "json", "csv", "summary-csv"), default="text")
    sw.add_argument("--output", type=Path, help="write the report here instead of stdout")
    sw.add_argument(
        "--no-missions", action="store_true", help="JSON: omit per-mission rows (summaries only)"
    )

    se = sub.add_parser("sensitivity", help="one-at-a-time parameter sensitivity")
    _common(se)
    se.add_argument(
        "--parameter",
        action="append",
        help="dotted parameter path (repeatable); default: the documented set",
    )
    se.add_argument("--values", help="comma-separated values (only with one --parameter)")
    se.add_argument("--output", type=Path)

    ab = sub.add_parser("ablation", help="suppress one scenario event at a time")
    _common(ab)
    ab.add_argument("--event", action="append", help="event id(s); default: all with effects")
    ab.add_argument("--output", type=Path)

    im = sub.add_parser("impact", help="fork each decision (omit it) and measure the change")
    _common(im)
    im.add_argument("--continuation", choices=("replay", "strategy", "both"), default="both")
    im.add_argument("--output", type=Path)

    dg = sub.add_parser("diagnose", help="sweep + ablation + impact (+ sensitivity) + findings")
    _common(dg)
    dg.add_argument("--impact-seeds", type=int, default=10)
    dg.add_argument("--ablation-seeds", type=int, default=50)
    dg.add_argument(
        "--sensitivity-seeds",
        type=int,
        default=0,
        help="seeds per sensitivity point (0 = skip sensitivity)",
    )
    dg.add_argument("--output-dir", type=Path, required=True)

    qu = sub.add_parser("quality", help="Future Lens and Black Box quality measurements")
    qu.add_argument("--scenario", default="luna-01")
    qu.add_argument("--lens-seeds", type=int, default=3, help="missions sampled for lens states")
    qu.add_argument("--failure-seeds", type=int, default=100, help="seeds searched for failures")
    qu.add_argument("--failures-per-strategy", type=int, default=5)
    qu.add_argument(
        "--profile-seeds", type=int, default=10, help="missions per strategy for profiles"
    )
    qu.add_argument("--output", type=Path)

    be = sub.add_parser("bench", help="performance at scale (missions/s, memory, lens, replay)")
    be.add_argument(
        "--missions",
        default="100,1000",
        help="comma-separated mission counts (e.g. 100,1000,10000)",
    )
    be.add_argument("--workers", type=int, default=default_workers())
    be.add_argument("--output", type=Path)

    sr = sub.add_parser(
        "search", help="bounded search over gameplay parameters (never edits the scenario)"
    )
    sr.add_argument(
        "--param",
        action="append",
        required=True,
        metavar="PATH=V1,V2,...",
        help="parameter and candidate values (repeatable); 'PATH*=f1,f2' scales",
    )
    sr.add_argument("--seeds", type=int, default=12, help="screening seeds per candidate")
    sr.add_argument("--refine-seeds", type=int, default=0, help="seeds for the top candidates")
    sr.add_argument("--top", type=int, default=5)
    sr.add_argument("--workers", type=int, default=default_workers())
    sr.add_argument("--output-dir", type=Path, required=True)

    tr = sub.add_parser("trajectory", help="per-tick resource trajectory of one mission")
    tr.add_argument("--scenario", default="luna-01")
    tr.add_argument("--strategy", default="balanced")
    tr.add_argument("--seed", type=int, default=1)
    tr.add_argument(
        "--set", action="append", default=[], metavar="PATH=VALUE", help="override (repeatable)"
    )
    tr.add_argument("--format", choices=("csv", "json"), default="csv")
    tr.add_argument("--output", type=Path)
    tr.add_argument(
        "--representative",
        type=Path,
        metavar="DIR",
        help="write the representative missions (CSV + JSON) into DIR instead",
    )

    au = sub.add_parser("audit", help="classify decision kinds by measured consequences")
    au.add_argument("--scenario", default="luna-01")
    au.add_argument("--reference", default="balanced", help="strategy whose missions are probed")
    au.add_argument("--seeds", type=int, default=5)
    au.add_argument(
        "--set", action="append", default=[], metavar="PATH=VALUE", help="override (repeatable)"
    )
    au.add_argument("--output", type=Path)
    return parser


def _emit(text_or_obj: str | dict[str, Any], output: Path | None) -> None:
    if output is not None:
        write(output, text_or_obj)
        print(f"wrote {output}", file=sys.stderr)
    elif isinstance(text_or_obj, str):
        sys.stdout.write(text_or_obj if text_or_obj.endswith("\n") else text_or_obj + "\n")
    else:
        print(json.dumps(text_or_obj, indent=2, sort_keys=True))


def cmd_sweep(a: argparse.Namespace) -> int:
    overrides = tuple(parse_override(o) for o in a.set)
    spec = SweepSpec(
        scenario_id=resolve_scenario_id(a.scenario),
        strategies=_strategies(a.strategy),
        seeds=seeds_from(a.start_seed, a.seeds),
        overrides=overrides,
        check_invariants=a.strict,
        suppressed_events=tuple(a.suppress_event),
    )
    started = time.perf_counter()
    result = run_sweep(spec, workers=a.workers)
    elapsed = time.perf_counter() - started
    print(
        f"{len(result.rows)} missions in {elapsed:.1f}s "
        f"({elapsed / max(1, len(result.rows)) * 1000:.1f} ms/mission, {a.workers} workers)",
        file=sys.stderr,
    )
    if a.format == "json":
        _emit(sweep_json(result, include_missions=not a.no_missions), a.output)
    elif a.format == "csv":
        _emit(mission_rows_csv(result.rows), a.output)
    elif a.format == "summary-csv":
        _emit(summary_rows_csv(summarize(result.rows)), a.output)
    else:
        header = (
            f"scenario {spec.scenario_id} ({result.scenario_hash[:12]}), seeds "
            f"{spec.seeds[0]}..{spec.seeds[-1]}"
            + (f", overrides {dict(overrides)}" if overrides else "")
        )
        _emit("\n".join([header, *(format_summary(s) for s in summarize(result.rows))]), a.output)
    return 0


def cmd_sensitivity(a: argparse.Namespace) -> int:
    params = a.parameter or list(DEFAULT_PARAMETERS)
    if a.values and len(params) != 1:
        raise SystemExit("--values needs exactly one --parameter")
    strategies = (
        _strategies(a.strategy) if a.strategy else ("balanced", "survival_first", "science_first")
    )
    results = []
    for p in params:
        values = (
            [float(v) for v in a.values.split(",")] if a.values else list(DEFAULT_PARAMETERS[p])
        )
        results.append(
            run_sensitivity(
                p,
                values,
                scenario_id=resolve_scenario_id(a.scenario),
                strategies=strategies,
                seeds=seeds_from(a.start_seed, a.seeds),
                workers=a.workers,
                progress=_indented,
            ).as_dict()
        )
    _emit({"report": "odyssey.balancing.sensitivity", "results": results}, a.output)
    return 0


def cmd_ablation(a: argparse.Namespace) -> int:
    strategies = (
        _strategies(a.strategy)
        if a.strategy
        else ("balanced", "survival_first", "science_first", "passive")
    )
    rows = run_ablation(
        scenario_id=resolve_scenario_id(a.scenario),
        strategies=strategies,
        seeds=seeds_from(a.start_seed, a.seeds),
        events=a.event,
        workers=a.workers,
    )
    _emit(
        {
            "report": "odyssey.balancing.ablation",
            "rows": [r.as_dict() for r in rows],
            "findings": [f.as_dict() for f in diagnostics.events(rows)],
        },
        a.output,
    )
    return 0


def _impact_rows(
    scenario_id: str, strategies: Sequence[str], seeds: Sequence[int], continuation: str
) -> list[Any]:
    engine = SimulationEngine(get_scenario(scenario_id))
    modes = ("replay", "strategy") if continuation == "both" else (continuation,)
    rows = []
    for s in strategies:
        for seed in seeds:
            for mode in modes:
                rows += decision_impact(engine, s, seed, continuation=mode)  # type: ignore[arg-type]
    return rows


def cmd_impact(a: argparse.Namespace) -> int:
    rows = _impact_rows(
        resolve_scenario_id(a.scenario),
        _strategies(a.strategy),
        seeds_from(a.start_seed, a.seeds),
        a.continuation,
    )
    summaries = summarize_impact(rows)
    _emit(
        {
            "report": "odyssey.balancing.impact",
            "summaries": [s.as_dict() for s in summaries],
            "forks": [r.as_dict() for r in rows],
            "findings": [f.as_dict() for f in diagnostics.decisions(summaries)],
        },
        a.output,
    )
    return 0


def cmd_diagnose(a: argparse.Namespace) -> int:
    out: Path = a.output_dir
    scenario_id = resolve_scenario_id(a.scenario)
    scenario = apply_overrides(get_scenario(scenario_id), ())
    player = strategies_or_all(None)
    probes = tuple(DIAGNOSTIC_PROBES)
    seeds = seeds_from(a.start_seed, a.seeds)

    log(f"[1/4] sweep: {len(player) + len(probes)} strategies × {len(seeds)} seeds")
    sweep = run_sweep(
        SweepSpec(scenario_id=scenario_id, strategies=player + probes, seeds=seeds),
        workers=a.workers,
    )
    write(out / "sweep.json", sweep_json(sweep))
    write(out / "missions.csv", mission_rows_csv(sweep.rows))
    summaries = summarize(sweep.rows)
    write(out / "summary.csv", summary_rows_csv(summaries))
    player_summaries = [s for s in summaries if s.strategy in player]

    log(f"[2/4] ablation: {a.ablation_seeds} seeds")
    ablation = run_ablation(
        scenario_id=scenario_id, seeds=seeds_from(1, a.ablation_seeds), workers=a.workers
    )
    write(out / "ablation.json", {"rows": [r.as_dict() for r in ablation]})

    log(f"[3/4] decision impact: {a.impact_seeds} seeds")
    impact_rows = _impact_rows(
        scenario_id,
        ("balanced", "survival_first", "science_first", "power_conservative"),
        seeds_from(1, a.impact_seeds),
        "both",
    )
    impact = summarize_impact(impact_rows)
    write(
        out / "impact.json",
        {"summaries": [s.as_dict() for s in impact], "forks": [r.as_dict() for r in impact_rows]},
    )

    sensitivity: list[dict[str, Any]] = []
    if a.sensitivity_seeds > 0:
        log(
            f"[4/4] sensitivity: {len(DEFAULT_PARAMETERS)} parameters × {a.sensitivity_seeds} seeds"
        )
        for p, values in DEFAULT_PARAMETERS.items():
            sensitivity.append(
                run_sensitivity(
                    p,
                    values,
                    scenario_id=scenario_id,
                    seeds=seeds_from(1, a.sensitivity_seeds),
                    workers=a.workers,
                    progress=_indented,
                ).as_dict()
            )
        write(out / "sensitivity.json", {"results": sensitivity})
    else:
        log("[4/4] sensitivity skipped (--sensitivity-seeds 0)")

    findings = [
        *diagnostics.objectives(player_summaries),
        *diagnostics.outcomes(scenario, [r for r in sweep.rows if r.strategy in player]),
        *diagnostics.alerts(scenario, player_summaries),
        *diagnostics.systems(player_summaries),
        *diagnostics.strategies(player_summaries),
        *diagnostics.events(ablation),
        *diagnostics.decisions(impact),
    ]
    write(out / "findings.json", {"findings": [f.as_dict() for f in findings]})
    for f in findings:
        print(f"- [{f.detector}] {f.subject}: {f.summary}")
    log(f"wrote reports to {out}/")
    return 0


def cmd_quality(a: argparse.Namespace) -> int:
    from .quality import (
        assess_black_box,
        injected_failures,
        measure_future_lens,
        measure_profiles,
        strategy_failures,
        trace_fingerprint,
    )

    engine = SimulationEngine(get_scenario(resolve_scenario_id(a.scenario)))
    log(f"future lens: states from {a.lens_seeds} balanced missions")
    lens = measure_future_lens(engine, seeds=seeds_from(1, a.lens_seeds))
    log("black box: injected failures + failures found by strategies")
    cases = injected_failures()
    for strategy in ("high_risk", "random_valid", "science_first", "naive_beginner", "passive"):
        cases += strategy_failures(
            engine, strategy, seeds_from(1, a.failure_seeds), a.failures_per_strategy
        )
    for strategy in ("balanced", "science_first", "naive_beginner"):
        cases += strategy_failures(
            engine,
            strategy,
            seeds_from(1, a.failure_seeds),
            a.failures_per_strategy,
            classes=("partial",),
        )
    results = []
    for case in cases:
        res = assess_black_box(case).as_dict()
        record = reconstruct(case.engine, case.initial, case.records, case.final.tick)
        traces = build_black_box(case.engine, record).causal_traces
        res["failure_trace"] = trace_fingerprint(traces[0]) if traces else None
        results.append(res)
    totals = {
        k: sum(r[k] for r in results)
        for k in (
            "irrelevant_blame",
            "undeclared_edges",
            "order_violations",
            "cyclic_chains",
            "missing_context",
        )
    }
    totals["unexplained"] = sum(r["unexplained"] for r in results)
    totals["unstable"] = sum(not r["stable"] for r in results)
    for k in (
        "analysis_chains",
        "analysis_traced",
        "analysis_omission",
        "analysis_untraced",
        "analysis_blamed_decisions",
        "analysis_on_path_no_effect",
    ):
        totals[k] = sum(r[k] for r in results)
    log(f"profiles: {len(PROBE_STRATEGIES)} strategies × {a.profile_seeds} seeds")
    profiles = measure_profiles(engine, PROBE_STRATEGIES, seeds_from(1, a.profile_seeds))
    _emit(
        {
            "report": "odyssey.balancing.quality",
            "future_lens": lens.summary(),
            "black_box": {"cases": len(results), "totals": totals, "results": results},
            "profiles": profiles.as_dict(),
        },
        a.output,
    )
    return 0


def cmd_bench(a: argparse.Namespace) -> int:
    from .bench import bench_components, bench_missions

    counts = [int(x) for x in a.missions.split(",") if x]
    log("components…")
    components = bench_components()
    log(f"missions {counts} (1 worker for the first count, {a.workers} for all)")
    single = bench_missions(counts[:1], workers=1)
    multi = bench_missions(counts, workers=a.workers) if a.workers > 1 else []
    _emit(
        {"report": "odyssey.balancing.bench", "components": components, "missions": single + multi},
        a.output,
    )
    return 0


def _parse_param(text: str) -> tuple[str, tuple[Any, ...]]:
    path, value = parse_override(text)
    raw = text.partition("=")[2]
    values = tuple(parse_override(f"x={v}")[1] for v in raw.split(",") if v.strip())
    if not values:
        raise SystemExit(f"--param {text!r}: no values")
    del value
    return path, values


def cmd_search(a: argparse.Namespace) -> int:
    from .search import SearchSpace, report_markdown, run_search

    space = SearchSpace(tuple(_parse_param(p) for p in a.param))
    space.validate()
    n = len(space.candidates())
    log(f"screening {n} candidates × {a.seeds} seeds; refine top {a.top} × {a.refine_seeds}")

    def progress(i: int, total: int, res: Any) -> None:
        ov = " ".join(f"{k}={v}" for k, v in res.overrides)
        log(f"  [{i}/{total}] {len(res.passed)} passed  {ov}")

    screened, refined = run_search(
        space,
        seeds=seeds_from(1, a.seeds),
        refine_seeds=seeds_from(1, a.refine_seeds) if a.refine_seeds else (),
        top=a.top,
        workers=a.workers,
        progress=progress,
    )
    out: Path = a.output_dir
    write(
        out / "search.json",
        {
            "report": "odyssey.balancing.search",
            "space": {p: list(v) for p, v in space.parameters},
            "screened": [r.as_dict() for r in screened],
            "refined": [r.as_dict() for r in refined],
        },
    )
    write(out / "SEARCH_REPORT.md", report_markdown(space, screened, refined))
    log(f"wrote {out}/search.json and {out}/SEARCH_REPORT.md")
    return 0


def cmd_trajectory(a: argparse.Namespace) -> int:
    from .trajectory import play_trajectory, representative_trajectories

    scenario = apply_overrides(
        get_scenario(resolve_scenario_id(a.scenario)), [parse_override(o) for o in a.set]
    )
    if a.representative is not None:
        index = []
        for t in representative_trajectories(SimulationEngine(scenario)):
            name = t.label.split(":")[0]
            write(a.representative / f"{name}.csv", t.to_csv())
            write(a.representative / f"{name}.json", t.as_dict())
            index.append(
                {
                    "file": name,
                    "strategy": t.strategy,
                    "seed": t.seed,
                    "outcome": t.outcome,
                    "outcome_class": t.outcome_class,
                    "ticks": len(t.rows),
                }
            )
            log(f"  {name}: {t.strategy} seed {t.seed} → {t.outcome}")
        write(a.representative / "index.json", {"trajectories": index})
        return 0
    traj = play_trajectory(SimulationEngine(scenario), a.strategy, a.seed)
    _emit(traj.to_csv() if a.format == "csv" else traj.as_dict(), a.output)
    return 0


def cmd_audit(a: argparse.Namespace) -> int:
    from .decision_audit import audit

    scenario = apply_overrides(
        get_scenario(resolve_scenario_id(a.scenario)), [parse_override(o) for o in a.set]
    )
    classes, rows = audit(
        SimulationEngine(scenario), reference=a.reference, seeds=seeds_from(1, a.seeds)
    )
    for c in classes:
        log(
            f"  {c.classification:20} {c.label:28} tier {c.tier_change_rate:.2f} "
            f"core {c.core_objective_rate:.2f} obj {c.objective_rate:.2f} "
            f"material {c.material_rate:.2f} measurable {c.measurable_rate:.2f} (n={c.insertions})"
        )
    _emit(
        {
            "report": "odyssey.balancing.decision_audit",
            "reference": a.reference,
            "seeds": a.seeds,
            "classes": [c.as_dict() for c in classes],
            "insertions": [
                {
                    "label": r.label,
                    "seed": r.seed,
                    "tick": r.tick,
                    "valid": r.valid,
                    "tier_changed": r.tier_changed,
                    "objectives_changed": r.objectives_changed,
                    "deltas": r.deltas,
                }
                for r in rows
            ],
        },
        a.output,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or (args[0] not in COMMANDS and args[0] not in ("-h", "--help")):
        args = ["sweep", *args]
    ns = build_parser().parse_args(args)
    handlers = {
        "sweep": cmd_sweep,
        "sensitivity": cmd_sensitivity,
        "ablation": cmd_ablation,
        "impact": cmd_impact,
        "diagnose": cmd_diagnose,
        "quality": cmd_quality,
        "bench": cmd_bench,
        "search": cmd_search,
        "trajectory": cmd_trajectory,
        "audit": cmd_audit,
    }
    return handlers[ns.command](ns)


if __name__ == "__main__":
    raise SystemExit(main())
