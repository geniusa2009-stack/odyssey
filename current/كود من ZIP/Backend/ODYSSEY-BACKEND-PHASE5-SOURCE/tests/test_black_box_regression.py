"""Black Box regression fixtures for representative failures.

Each fixture stores an id-free fingerprint (target, roots, chains) of the failure trace. A
change to the engine, dependency graph or tracer that alters any of them fails here, so causal
explanations cannot drift silently. After an *intentional* change, regenerate with:

    ODYSSEY_REGEN_FIXTURES=1 uv run pytest tests/test_black_box_regression.py

and review the fixture diff like code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.simulation.analysis.balancing.quality import (
    FailureCase,
    assess_black_box,
    injected_failures,
    strategy_failures,
    trace_fingerprint,
)
from app.simulation.analysis.black_box import build_black_box
from app.simulation.analysis.reconstruct import counterfactual_factory, reconstruct
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario

FIXTURES = Path(__file__).parent / "fixtures" / "black_box"
REGEN = os.environ.get("ODYSSEY_REGEN_FIXTURES") == "1"


def _cases() -> dict[str, FailureCase]:
    engine = SimulationEngine(get_scenario("luna-01"))
    cases = {c.name: c for c in injected_failures()}
    cases.update({c.name: c for c in strategy_failures(engine, "high_risk", range(1, 5), 1)})
    cases.update({c.name: c for c in strategy_failures(engine, "random_valid", range(1, 5), 1)})
    return cases


CASES = _cases()


def _fingerprint(case: FailureCase) -> dict[str, object]:
    record = reconstruct(case.engine, case.initial, case.records, case.final.tick)
    cf = counterfactual_factory(case.engine, case.initial, case.records, case.final.tick)
    report = build_black_box(case.engine, record, counterfactual=cf)
    first = report.causal_traces[0]
    verdicts = sorted(
        n.details["counterfactual"]["verdict"]
        for n in first.nodes
        if n.kind == "decision" and "counterfactual" in n.details
    )
    return {
        "case": case.name,
        "outcome": report.outcome.code if report.outcome else None,
        "final_tick": report.final_tick,
        "failure_trace": trace_fingerprint(first),
        "decision_verdicts": verdicts,
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_failure_trace_matches_fixture(name: str) -> None:
    path = FIXTURES / f"{name.replace(':', '_')}.json"
    actual = _fingerprint(CASES[name])
    if REGEN or not path.exists():
        if not REGEN:
            pytest.fail(f"missing fixture {path}; run with ODYSSEY_REGEN_FIXTURES=1")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    assert actual == json.loads(path.read_text())


@pytest.mark.parametrize("name", sorted(CASES))
def test_failure_trace_quality(name: str) -> None:
    result = assess_black_box(CASES[name])
    assert result.outcome.startswith("mission_failed")
    assert result.stable and not result.unexplained
    assert result.undeclared_edges == result.order_violations == result.cyclic_chains == 0
    assert result.missing_context == 0


def test_irrelevant_decision_is_not_blamed() -> None:
    """The comms-eco decision in 'cold_and_hungry' must not appear as a cause of crew loss."""
    case = CASES["cold_and_hungry_with_irrelevant_comms"]
    comms = next(r.decision_id for r in case.records if r.inputs.get("subsystem") == "comms")
    record = reconstruct(case.engine, case.initial, case.records, case.final.tick)
    for trace in build_black_box(case.engine, record).causal_traces:
        assert f"decision:{comms}" not in {n.id for n in trace.nodes}
