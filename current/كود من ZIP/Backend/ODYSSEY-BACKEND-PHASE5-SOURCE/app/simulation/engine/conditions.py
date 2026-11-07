"""Evaluation of the declarative condition language against mission state."""

from __future__ import annotations

from itertools import pairwise

from app.simulation.domain.state import MissionState
from app.simulation.engine.metrics import MetricRegistry
from app.simulation.scenarios.schema import Condition

_EPS = 1e-12


def compare(value: float, op: str, threshold: float) -> bool:
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold + _EPS
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold - _EPS
    if op == "==":
        return abs(value - threshold) <= _EPS
    if op == "!=":
        return abs(value - threshold) > _EPS
    raise ValueError(f"unknown comparison operator {op!r}")


def evaluate(condition: Condition, state: MissionState, metrics: MetricRegistry) -> bool:
    if condition.metric is not None:
        assert condition.op is not None
        assert condition.value is not None
        return compare(metrics.value(condition.metric, state), condition.op, condition.value)
    if condition.all is not None:
        return all(evaluate(c, state, metrics) for c in condition.all)
    if condition.any is not None:
        return any(evaluate(c, state, metrics) for c in condition.any)
    if condition.not_ is not None:
        return not evaluate(condition.not_, state, metrics)
    raise ValueError("empty condition")  # unreachable: schema validator guarantees one form


def interpolate(frames: list[tuple[int, float]], tick: int) -> float:
    """Piecewise-linear interpolation, clamped at the ends (pure + - * /)."""
    if tick <= frames[0][0]:
        return frames[0][1]
    for (t0, v0), (t1, v1) in pairwise(frames):
        if t0 <= tick <= t1:
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * (tick - t0) / (t1 - t0)
    return frames[-1][1]


def step_value(frames: list[tuple[int, float]], tick: int) -> float:
    """Step function: value of the last keyframe at or before ``tick``."""
    current = frames[0][1]
    for t, v in frames:
        if t <= tick:
            current = v
        else:
            break
    return current
