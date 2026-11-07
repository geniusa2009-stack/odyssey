"""Server-authoritative mission clock.

Design (docs/GAME_BACKEND_ARCHITECTURE.md, "Mission clock"):

* The client never decides simulation time. The clock state lives in the timeline document:
  ``mode``, ``realtime_ticks_per_second``, ``accelerated_multiplier``, an *anchor*
  (``anchor_wall_ms``, ``anchor_tick``) and ``max_catchup_ticks``.
* **Lazy catch-up.** Whenever the session is processed (any command, or ``POST .../sync``) under
  the session row lock, the number of due ticks is
  ``floor(elapsed_s * rate) - (sim_tick - anchor_tick)`` with ``elapsed_s`` measured from the
  anchor by the injected server :class:`Clock`. Because the target is computed from the anchor
  and the *current* simulation tick, processing twice at the same instant advances nothing: no
  double advancement, and no background task is needed (nothing can leak).
* **Caps.** At most ``max_catchup_ticks`` are applied in one catch-up; if more were due (the
  player left the game running unattended) the clock pauses (``unattended_limit``).
* **Decision pauses.** Advancement stops at the first tick where a pausing incident starts and
  the clock enters ``DECISION_PAUSED``; it stays there until the player resumes it.
* **Determinism.** Given the same recorded command times the result is identical; tests inject a
  :class:`FakeClock`.
* Every mode change re-anchors at (now, current tick).
"""

from __future__ import annotations

import math
import time
from typing import Protocol

from app.game.world.state import ClockState

RUNNING = ("REALTIME", "ACCELERATED")


class Clock(Protocol):
    def now_ms(self) -> int: ...


class SystemClock:
    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000


class FakeClock:
    """Deterministic test clock."""

    def __init__(self, start_ms: int = 1_800_000_000_000) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += round(seconds * 1000)


def rate(clock: ClockState) -> float:
    if clock.mode == "REALTIME":
        return clock.realtime_ticks_per_second
    if clock.mode == "ACCELERATED":
        return clock.realtime_ticks_per_second * clock.accelerated_multiplier
    return 0.0


def due_ticks(clock: ClockState, now_ms: int, sim_tick: int) -> int:
    """Ticks owed by the clock right now (uncapped, never negative)."""
    r = rate(clock)
    if r <= 0.0:
        return 0
    elapsed_s = max(0, now_ms - clock.anchor_wall_ms) / 1000.0
    target = math.floor(elapsed_s * r + 1e-9)
    return max(0, target - (sim_tick - clock.anchor_tick))


def anchor(clock: ClockState, now_ms: int, sim_tick: int) -> None:
    clock.anchor_wall_ms = now_ms
    clock.anchor_tick = sim_tick


def set_mode(
    clock: ClockState, mode: str, now_ms: int, sim_tick: int, *, reason: str | None = None
) -> None:
    clock.mode = mode  # type: ignore[assignment]
    clock.pause_reason = None if mode in RUNNING else (reason or "player")
    anchor(clock, now_ms, sim_tick)


def start(clock: ClockState, now_ms: int, sim_tick: int) -> None:
    clock.started = True
    set_mode(clock, "REALTIME", now_ms, sim_tick)


def seconds_per_tick(clock: ClockState) -> float | None:
    r = rate(clock)
    return None if r <= 0 else 1.0 / r
