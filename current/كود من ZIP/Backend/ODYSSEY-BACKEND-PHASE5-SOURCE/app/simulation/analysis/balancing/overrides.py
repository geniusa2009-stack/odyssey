"""Scenario parameter overrides for balancing experiments.

An override is ``"dotted.path=value"`` addressed into the scenario's JSON form:

* mapping keys by name: ``power.battery.capacity_kwh=200``
* list items **by their ``id``**: ``power.consumers.habitat_core.nominal_kw=1.2``,
  ``events.solar_particle_event.trigger.at_tick=100``,
  ``objectives.radiation_safety.fail_when.value=20``
* list items by index as a fallback: ``environment.solar_availability.0.value=0.9``
* every item of a list or mapping with ``*``: ``degradation.components.*.fault_damage=0.2``
* scale instead of set with ``*=``: ``degradation.components.*.wear_per_tick*=5`` multiplies
  each matched number (the override key is then stored with a trailing ``*``)

Values are parsed as JSON (``200``, ``0.5``, ``true``, ``"nominal"``); anything that is not
valid JSON is taken as a string. The result is re-validated by :class:`ScenarioDefinition`,
so an override can never produce a scenario the engine would not accept. Overrides change
*experiments only*; the shipped scenario files are never modified.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.simulation.scenarios.schema import ScenarioDefinition


class OverrideError(ValueError):
    """An override path does not exist or its value is not acceptable."""


def parse_override(text: str) -> tuple[str, Any]:
    """``"a.b=1.5"`` → ``("a.b", 1.5)``; ``"a.b*=2"`` → ``("a.b*", 2)`` (scale)."""
    path, sep, raw = text.partition("=")
    if not sep or not path.strip():
        raise OverrideError(f"override must look like path=value, got {text!r}")
    raw = raw.strip()
    try:
        value: Any = json.loads(raw)
    except ValueError:
        value = raw
    return path.strip(), value


def _child(node: Any, part: str, path: str) -> tuple[Any, Any]:
    """Return (container, key) addressing ``part`` inside ``node``."""
    if isinstance(node, dict):
        if part not in node:
            raise OverrideError(f"{path}: no key {part!r} (have: {sorted(node)[:12]})")
        return node, part
    if isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, dict) and item.get("id") == part:
                return node, index
        if part.isdigit() and int(part) < len(node):
            return node, int(part)
        ids = [i.get("id") for i in node if isinstance(i, dict) and "id" in i]
        raise OverrideError(f"{path}: no list item {part!r} (ids: {ids[:12]})")
    raise OverrideError(f"{path}: cannot descend into a {type(node).__name__} at {part!r}")


def _targets(node: Any, parts: list[str], path: str) -> list[tuple[Any, Any]]:
    """Every (container, key) the path addresses (several when it contains ``*``)."""
    part, rest = parts[0], parts[1:]
    if part == "*":
        if isinstance(node, dict):
            keys: list[Any] = sorted(node)
        elif isinstance(node, list):
            keys = list(range(len(node)))
        else:
            raise OverrideError(f"{path}: '*' needs a list or mapping")
        pairs = [(node, k) for k in keys]
    else:
        pairs = [_child(node, part, path)]
    if not rest:
        return pairs
    out: list[tuple[Any, Any]] = []
    for container, key in pairs:
        out.extend(_targets(container[key], rest, path))
    return out


def set_path(data: dict[str, Any], path: str, value: Any) -> None:
    scale = path.endswith("*") and not path.endswith(".*")
    clean = path[:-1] if scale else path
    for container, key in _targets(data, clean.split("."), clean):
        if scale:
            current = container[key]
            if not isinstance(current, int | float) or isinstance(current, bool):
                raise OverrideError(f"{clean}: can only scale numbers, found {current!r}")
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise OverrideError(f"{clean}: scale factor must be a number, got {value!r}")
            container[key] = current * value
        else:
            container[key] = value


def get_path(data: Mapping[str, Any], path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        container, key = _child(node, part, path)
        node = container[key]
    return node


def apply_overrides(
    scenario: ScenarioDefinition, overrides: Mapping[str, Any] | Sequence[tuple[str, Any]]
) -> ScenarioDefinition:
    """Return a validated copy of ``scenario`` with ``overrides`` applied."""
    items = list(overrides.items()) if isinstance(overrides, Mapping) else list(overrides)
    if not items:
        return scenario
    data = copy.deepcopy(scenario.model_dump(mode="json", by_alias=True))
    for path, value in items:
        set_path(data, path, value)
    try:
        return ScenarioDefinition.model_validate(data)
    except ValueError as exc:
        raise OverrideError(f"overrides produce an invalid scenario: {exc}") from exc
