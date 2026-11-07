"""Rendering of interaction templates into concrete simulation decisions and effects.

Shared by content validation (every parameter combination is rendered and type-checked at load
time) and the domain (rendering the one combination a command asks for).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Mapping
from typing import Any

from app.game.content.schema import Effects, EngineStep, Interaction


def render_value(value: Any, params: Mapping[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return params[value[1:]]
    if isinstance(value, dict):
        return {k: render_value(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(v, params) for v in value]
    return value


def engine_steps(interaction: Interaction, params: Mapping[str, str]) -> list[EngineStep]:
    """The engine steps for one parameter assignment (static steps first, then per-param)."""
    steps = list(interaction.engine)
    for name, by_value in interaction.engine_by_param.items():
        steps.extend(by_value.get(params.get(name, ""), []))
    return steps


def rendered_decisions(interaction: Interaction, params: Mapping[str, str]) -> list[dict[str, Any]]:
    return [render_value(step.decision, params) for step in engine_steps(interaction, params)]


def param_effects(interaction: Interaction, params: Mapping[str, str]) -> list[Effects]:
    found = [interaction.effects]
    for name, by_value in interaction.effects_by_param.items():
        chosen = by_value.get(params.get(name, ""))
        if chosen is not None:
            found.append(chosen)
    return found


def all_param_assignments(interaction: Interaction) -> Iterator[dict[str, str]]:
    names = sorted(interaction.params)
    for values in itertools.product(*(interaction.params[n].enum for n in names)):
        yield dict(zip(names, values, strict=True))
