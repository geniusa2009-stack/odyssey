"""Scenario loading and registry (file-based, no I/O beyond reading packaged YAML)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.simulation.canonical import sha256_hex
from app.simulation.scenarios.schema import ScenarioDefinition

DATA_DIR = Path(__file__).parent / "data"


class ScenarioNotFoundError(KeyError):
    pass


class _Yaml12SafeLoader(yaml.SafeLoader):
    """SafeLoader where only true/false are booleans (YAML 1.2 semantics).

    PyYAML follows YAML 1.1, which silently turns ``off``/``on``/``yes``/``no`` into booleans —
    a trap for scenario authors (``mode_factors: {off: 0.0}``).
    """


_Yaml12SafeLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Yaml12SafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def load_yaml(text: str) -> object:
    return yaml.load(text, Loader=_Yaml12SafeLoader)  # noqa: S506 - SafeLoader subclass


def load_scenario_file(path: Path) -> ScenarioDefinition:
    return ScenarioDefinition.model_validate(load_yaml(path.read_text(encoding="utf-8")))


def scenario_content_hash(scenario: ScenarioDefinition) -> str:
    """Hash pinning the exact scenario content a session was created with."""
    return sha256_hex(scenario.model_dump(mode="json", by_alias=True))


@lru_cache(maxsize=1)
def _registry() -> dict[str, ScenarioDefinition]:
    found: dict[str, ScenarioDefinition] = {}
    for path in sorted(DATA_DIR.glob("*.yaml")):
        scenario = load_scenario_file(path)
        if scenario.id in found:
            raise ValueError(f"duplicate scenario id {scenario.id}")
        found[scenario.id] = scenario
    return found


def list_scenarios() -> list[ScenarioDefinition]:
    return list(_registry().values())


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    try:
        return _registry()[scenario_id]
    except KeyError as exc:
        raise ScenarioNotFoundError(scenario_id) from exc
