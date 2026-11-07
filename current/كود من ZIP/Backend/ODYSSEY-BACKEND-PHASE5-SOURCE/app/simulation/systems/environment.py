"""Environment system: natural profile + event modifiers.

Equations (tick t):
    base_x(t)   = piecewise-linear interpolation of scenario keyframes (earth_visible: step)
    x(t)        = base_x(t) with every active modifier applied in (start_tick, event_id) order
                  multiply: x *= v   add: x += v   set: x = v
    solar_availability is clamped to [0, 1]; dose rate to >= 0.
"""

from __future__ import annotations

from app.simulation.domain.state import ActiveModifier, MissionState
from app.simulation.engine.conditions import interpolate, step_value
from app.simulation.engine.context import TickContext
from app.simulation.scenarios.schema import Keyframe, ScenarioDefinition


def _frames(frames: list[Keyframe]) -> list[tuple[int, float]]:
    return [(f.tick, f.value) for f in frames]


def active_modifiers(state: MissionState, target: str, tick: int) -> list[ActiveModifier]:
    mods = [m for m in state.modifiers if m.target == target and m.start_tick <= tick < m.end_tick]
    return sorted(mods, key=lambda m: (m.start_tick, m.event_id))


def apply_modifiers(state: MissionState, target: str, base: float, tick: int) -> float:
    value = base
    for mod in active_modifiers(state, target, tick):
        if mod.op == "multiply":
            value *= mod.value
        elif mod.op == "add":
            value += mod.value
        elif mod.op == "set":
            value = mod.value
    return value


def compute_environment(scenario: ScenarioDefinition, state: MissionState, tick: int) -> None:
    env = scenario.environment
    solar = apply_modifiers(
        state, "env.solar_availability", interpolate(_frames(env.solar_availability), tick), tick
    )
    sink = apply_modifiers(
        state, "env.sink_temp_c", interpolate(_frames(env.sink_temp_c), tick), tick
    )
    rad = apply_modifiers(
        state,
        "env.radiation_dose_rate_msv_h",
        interpolate(_frames(env.radiation_dose_rate_msv_h), tick),
        tick,
    )
    vis = apply_modifiers(
        state, "env.earth_visible", step_value(_frames(env.earth_visible), tick), tick
    )
    state.environment.solar_availability = min(1.0, max(0.0, solar))
    state.environment.sink_temp_c = sink
    state.environment.radiation_dose_rate_msv_h = max(0.0, rad)
    state.environment.earth_visible = vis >= 0.5


def expire_modifiers(state: MissionState, tick: int) -> None:
    state.modifiers = [m for m in state.modifiers if m.end_tick > tick]


def update(ctx: TickContext) -> None:
    expire_modifiers(ctx.state, ctx.tick)
    compute_environment(ctx.scenario, ctx.state, ctx.tick)
