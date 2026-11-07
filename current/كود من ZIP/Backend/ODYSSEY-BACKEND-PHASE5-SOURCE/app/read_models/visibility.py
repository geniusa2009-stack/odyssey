"""What a player may know in advance: the information-visibility rules of the frontend contract.

The simulation keeps some scenario content secret until it happens: events marked
``foreseeable: false`` (unforeseeable events). Phases are designed mission chapters on a
schedule, and a chapter built around an unforeseeable event (e.g. a phase that narrates a
solar storm) would reveal that event if its name were shown before the chapter begins. These
rules are derived from the scenario definition only — never from event or phase names — so they
hold for any scenario.

**Phase rule.** The name of a future simulated phase is *announced* (shown as ``next_phase``, in
the bootstrap phase list and as a Future Lens projected phase) only when the mission plan
announces it, i.e. all of:

1. **scheduled start**: the transition into it is reached by a chain of pure clock conditions
   (``time.tick >= N`` / ``> N`` / ``== N``) from the first phase, so the player knows when
   it begins;
2. **announced by the plan**: at least one *foreseeable* scheduled event (a planned milestone)
   lies in its window ``[start, end)``;
3. **not bound to an unforeseeable event** (safety net): no event marked ``foreseeable: false``
   can only fire inside its window (scheduled event: its tick; random event: its
   ``from_tick``…``to_tick``; state- and decision-triggered events: earliest tick to mission
   end). Background events that can fire in several phases are attributed to none.

Every other future phase is *withheld until entered*: its name is replaced by ``null``.
Condition 2 is what makes withholding safe: the decision to withhold does not depend on
whether hidden events exist (a chapter without a planned milestone is withheld whether or not
something unforeseeable happens in it), so ``null`` itself reveals nothing; condition 3 only
matters for a chapter that mixes planned and hidden events. The first phase, the current phase
and phases already entered are always visible (present or past facts); phases of kind
``conclusion`` / ``analysis`` are structural (the mission always ends) and always visible.

**Event rule.** Identifiers of unforeseeable events never appear in static, session-independent
content (science claims); events that have happened appear in mission history as usual.
"""

from __future__ import annotations

import math
import weakref
from collections.abc import Iterable
from dataclasses import dataclass

from app.simulation.domain.state import MissionState
from app.simulation.engine.engine import SimulationEngine
from app.simulation.scenarios.schema import (
    Condition,
    DecisionTrigger,
    RandomTrigger,
    ScenarioDefinition,
    ScheduledTrigger,
    StateTrigger,
)

STRUCTURAL_PHASE_KINDS = frozenset({"conclusion", "analysis"})
WITHHELD_EVENT_USAGE = "events.unforeseeable"


@dataclass(frozen=True, slots=True)
class PhaseVisibility:
    """Static visibility facts of one scenario."""

    windows: dict[str, tuple[int, int]]  # scheduled phases: [start, end) (end = mission end)
    withheld_until_entered: frozenset[str]
    bound_events: dict[str, tuple[str, ...]]  # phase → unforeseeable events bound to it
    announced: frozenset[str]  # future phases whose names the mission plan announces


def _clock_tick(c: Condition | None, start: int) -> int | None:
    """Tick at which a pure clock condition first holds after ``start``; None otherwise."""
    if c is None or c.metric != "time.tick" or c.value is None:
        return None
    v = float(c.value)
    if c.op == ">=":
        tick = math.ceil(v)
    elif c.op == ">":
        tick = math.floor(v) + 1
    elif c.op == "==" and v.is_integer():
        tick = int(v)
    else:
        return None
    return tick if tick > start else None


def _event_span(trigger: object, max_ticks: int) -> tuple[int, int]:
    if isinstance(trigger, ScheduledTrigger):
        return trigger.at_tick, trigger.at_tick
    if isinstance(trigger, RandomTrigger):
        hi = trigger.to_tick if trigger.to_tick is not None else max_ticks
        return trigger.from_tick, min(hi, max_ticks)
    if isinstance(trigger, StateTrigger):
        return trigger.after_tick, max_ticks
    if isinstance(trigger, DecisionTrigger):
        return 0, max_ticks
    return 0, max_ticks  # unknown trigger type: attributable to no single phase window


def compute_phase_visibility(sc: ScenarioDefinition) -> PhaseVisibility:
    max_ticks = sc.time.max_ticks
    simulated = [p for p in sc.phases if p.kind not in STRUCTURAL_PHASE_KINDS]
    windows: dict[str, tuple[int, int]] = {}
    unscheduled: set[str] = set()
    start: int | None = 0
    for i, phase in enumerate(simulated):
        if start is None:
            unscheduled.add(phase.id)
            continue
        if phase.advance_when is None:
            windows[phase.id] = (start, max_ticks + 1)
            start = None  # nothing after it is reached by the clock
            continue
        end = _clock_tick(phase.advance_when, start)
        if end is None:
            # leaving this phase is not on the clock: it is still a known current phase, but
            # every later phase has no known start
            windows[phase.id] = (start, max_ticks + 1)
            start = None
            continue
        windows[phase.id] = (start, end)
        start = end if i + 1 < len(simulated) else None
    bound: dict[str, list[str]] = {}
    planned: set[str] = set()
    for event in sc.events:
        lo, hi = _event_span(event.trigger, max_ticks)
        if lo > hi:
            continue  # can never fire (e.g. a random window that closes before it opens)
        for pid, (s, e) in windows.items():
            if event.foreseeable:
                if isinstance(event.trigger, ScheduledTrigger) and s <= lo < e:
                    planned.add(pid)
            elif s <= lo and hi < e:
                bound.setdefault(pid, []).append(event.id)
    announced = {pid for pid in windows if pid in planned and pid not in bound}
    first = simulated[0].id if simulated else None
    withheld = {p.id for p in simulated} - announced - ({first} if first else set())
    return PhaseVisibility(
        windows=windows,
        withheld_until_entered=frozenset(withheld),
        bound_events={k: tuple(v) for k, v in bound.items()},
        announced=frozenset(announced),
    )


_CACHE: weakref.WeakKeyDictionary[SimulationEngine, PhaseVisibility] = weakref.WeakKeyDictionary()


def phase_visibility(engine: SimulationEngine) -> PhaseVisibility:
    cached = _CACHE.get(engine)
    if cached is None:
        cached = compute_phase_visibility(engine.scenario)
        _CACHE[engine] = cached
    return cached


def entered_phases(state: MissionState | None) -> frozenset[str]:
    if state is None:
        return frozenset()
    return frozenset({h.phase for h in state.phase_history} | {state.phase})


def phase_is_visible(engine: SimulationEngine, phase_id: str, entered: Iterable[str]) -> bool:
    """May the client see this phase's identity now?"""
    if phase_id in set(entered):
        return True
    return phase_id not in phase_visibility(engine).withheld_until_entered


def unforeseeable_event_ids(scenarios: Iterable[ScenarioDefinition]) -> frozenset[str]:
    return frozenset(e.id for sc in scenarios for e in sc.events if not e.foreseeable)


def redact_usage(usage: Iterable[str], hidden_events: frozenset[str]) -> list[str]:
    """Replace references to unforeseeable events (``events.<id>[...]``) by a generic marker."""
    out: list[str] = []
    for u in usage:
        parts = u.split(".")
        if len(parts) >= 2 and parts[0] == "events" and parts[1] in hidden_events:
            u = WITHHELD_EVENT_USAGE
        if u not in out:
            out.append(u)
    return out
