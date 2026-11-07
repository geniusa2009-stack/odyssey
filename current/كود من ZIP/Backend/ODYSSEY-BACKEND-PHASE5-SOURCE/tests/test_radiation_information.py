"""Radiation information sufficiency (Phase 3, brief §13).

Phase 2 found 9 of 500 seeds where sheltering players still failed the radiation objective:
the warning alert came too late (a ×5 flare reads 0.285 mSv/h, below the 0.5 mSv/h alert) and
nothing told the player how much of the dose budget was left. v0.2.0 does not lower the
difficulty; it exposes what a dosimeter and the mission plan already know:

* ``crew.dose_margin_msv``: dose left before the mission limit;
* ``crew.projected_dose_msv`` / ``crew.projected_dose_margin_msv``: end-of-mission dose if the crew
  stays in the habitat at the *baseline* rate (no knowledge of future space weather);
* a ``radiation_above_background`` caution, and ``dose_budget_low`` / ``dose_budget_exceeded``.
"""

from __future__ import annotations

import pytest

from app.simulation.analysis.balancing.overrides import apply_overrides
from app.simulation.analysis.balancing.runner import run_mission
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.loader import get_scenario

SC = get_scenario("luna-01")
_limit = SC.radiation.dose_limit_msv
assert _limit is not None
LIMIT: float = _limit
# Seeds whose sheltering players failed the radiation objective in Phase 2 (v0.1.0).
PHASE2_RADIATION_FAILURES = (2, 12, 39, 63, 259, 291, 297, 449, 482)


def test_dose_limit_matches_the_radiation_objective() -> None:
    objective = SC.objective("radiation_safety")
    assert objective.fail_when is not None
    assert LIMIT == objective.fail_when.value == 15.0


def test_projection_uses_no_knowledge_of_future_events() -> None:
    """The same state gives the same projection whether or not space weather is scheduled."""
    engine = SimulationEngine(SC)
    calm = SimulationEngine(
        apply_overrides(
            SC,
            {
                "events.solar_particle_event.effects.0.value": 1.0,
                "events.minor_flare.trigger.probability_per_tick": 0.0,
            },
        )
    )
    state = engine.advance(engine.initial_state(2), 100).state  # before the SPE at tick 122
    for metric in ("crew.projected_dose_msv", "crew.projected_dose_margin_msv"):
        assert engine.metrics.value(metric, state) == pytest.approx(
            calm.metrics.value(metric, state)
        )


def test_projection_equals_dose_plus_remaining_background() -> None:
    engine = SimulationEngine(SC)
    state = engine.advance(engine.initial_state(1), 60).state
    remaining_h = SC.time.max_ticks - state.tick
    expected = max(
        c.dose_msv for c in state.crew
    ) + 0.057 * SC.radiation.habitat_shielding_factor * (remaining_h * SC.time.tick_hours)
    assert engine.metrics.value("crew.projected_dose_msv", state) == pytest.approx(expected)
    assert engine.metrics.value("crew.projected_dose_margin_msv", state) == pytest.approx(
        LIMIT - expected
    )


def test_a_minor_flare_raises_a_caution_before_the_warning() -> None:
    """A ×5 flare (0.285 mSv/h) is visible as a caution although it is below the warning."""
    alerts = {r.id: r for r in SC.alerts}
    caution, warning = alerts["radiation_above_background"], alerts["radiation_elevated"]
    assert caution.threshold < 0.057 * 5 < warning.threshold
    assert caution.severity == "caution"


@pytest.mark.parametrize("seed", PHASE2_RADIATION_FAILURES)
def test_phase2_failures_are_avoidable_with_the_new_information(seed: int) -> None:
    """A budget-aware sheltering player (balanced probe) now keeps every one under the limit."""
    run = run_mission(SimulationEngine(SC), "balanced", seed, keep_events=True)
    assert run.metrics.objectives["radiation_safety"] == "achieved"
    assert run.metrics.crew_dose_max_msv < LIMIT
    raised = {
        e.key for e in run.events if e.key in ("radiation_above_background", "dose_budget_low")
    }
    assert raised, "the player had a warning sign before the limit"
