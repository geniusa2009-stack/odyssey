"""Load, validate and index the game content (``app/game/content/data``).

Content is immutable after loading. :func:`default_content` is cached for the process; tests can
load alternative directories with :func:`load_content`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from app.game.content.schema import (
    Capability,
    Certification,
    CrewMember,
    Cue,
    Discovery,
    GameContent,
    Incident,
    InfrastructureType,
    Insight,
    Item,
    Location,
    MissionDef,
    PhaseDef,
    ReadinessProfile,
    VehicleClass,
    World,
    WorldObject,
)
from app.simulation.canonical import sha256_hex
from app.simulation.scenarios.loader import (
    ScenarioNotFoundError,
    get_scenario,
    load_scenario_file,
    load_yaml,
    scenario_content_hash,
)
from app.simulation.scenarios.schema import ScenarioDefinition

DATA_DIR = Path(__file__).parent / "data"
_SECTIONS = (
    "manifest",
    "campaign",
    "progression",
    "catalog",
    "knowledge",
    "narrative",
    "readiness",
)


class ContentError(ValueError):
    """Content failed to load or validate; ``problems`` lists every issue found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("invalid game content:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class ContentIndex:
    worlds: Mapping[str, World]
    locations: Mapping[str, Location]
    location_world: Mapping[str, str]
    objects: Mapping[str, WorldObject]
    object_world: Mapping[str, str]
    incidents: Mapping[str, Incident]
    discoveries: Mapping[str, Discovery]
    phases: Mapping[str, PhaseDef]
    missions: Mapping[str, MissionDef]
    capabilities: Mapping[str, Capability]
    certifications: Mapping[str, Certification]
    evidence: frozenset[str]
    stage_order: Mapping[str, int]
    items: Mapping[str, Item]
    vehicle_classes: Mapping[str, VehicleClass]
    infrastructure_types: Mapping[str, InfrastructureType]
    insights: Mapping[str, Insight]
    crew: Mapping[str, CrewMember]
    cues: Mapping[str, Cue]
    profiles: Mapping[str, ReadinessProfile]


@dataclass(frozen=True)
class LoadedContent:
    content: GameContent
    scenarios: Mapping[str, ScenarioDefinition]
    content_hash: str
    index: ContentIndex = field(repr=False)

    @property
    def version(self) -> str:
        return self.content.manifest.content_version

    def mission_scenario(self, mission_id: str) -> ScenarioDefinition:
        return self.scenarios[self.index.missions[mission_id].scenario.id]

    def world_missions(self, world_id: str) -> list[MissionDef]:
        return [m for m in self.content.campaign.missions if m.world == world_id]

    def capability_stage_rank(self, capability_id: str, stage: str) -> int:
        """Position of ``stage`` in the capability's own ladder (0-based)."""
        return self.index.capabilities[capability_id].stages.index(stage)


def _ro(d: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(d)


def build_index(content: GameContent) -> ContentIndex:
    locations: dict[str, Location] = {}
    location_world: dict[str, str] = {}
    objects: dict[str, WorldObject] = {}
    object_world: dict[str, str] = {}
    incidents: dict[str, Incident] = {}
    discoveries: dict[str, Discovery] = {}
    for world in content.worlds:
        for loc in world.locations:
            locations.setdefault(loc.id, loc)
            location_world.setdefault(loc.id, world.id)
        for obj in world.objects:
            objects.setdefault(obj.id, obj)
            object_world.setdefault(obj.id, world.id)
        for inc in world.incidents:
            incidents.setdefault(inc.id, inc)
        for disc in world.discoveries:
            discoveries.setdefault(disc.id, disc)
    prog, cat = content.progression, content.catalog
    return ContentIndex(
        worlds=_ro({w.id: w for w in content.worlds}),
        locations=_ro(locations),
        location_world=_ro(location_world),
        objects=_ro(objects),
        object_world=_ro(object_world),
        incidents=_ro(incidents),
        discoveries=_ro(discoveries),
        phases=_ro({p.id: p for p in content.campaign.phases}),
        missions=_ro({m.id: m for m in content.campaign.missions}),
        capabilities=_ro({c.id: c for c in prog.capabilities}),
        certifications=_ro({c.id: c for c in prog.certifications}),
        evidence=frozenset(e.id for e in prog.evidence),
        stage_order=_ro({s.id: s.order for s in prog.stages}),
        items=_ro({i.id: i for i in cat.items}),
        vehicle_classes=_ro({v.id: v for v in cat.vehicle_classes}),
        infrastructure_types=_ro({i.id: i for i in cat.infrastructure_types}),
        insights=_ro({i.id: i for i in content.knowledge.insights}),
        crew=_ro({c.id: c for c in content.narrative.crew}),
        cues=_ro({c.id: c for c in content.narrative.cues}),
        profiles=_ro({p.id: p for p in content.readiness.profiles}),
    )


def _read_yaml(path: Path) -> Any:
    try:
        return load_yaml(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError([f"{path.name}: YAML error: {exc}"]) from None


def read_raw(data_dir: Path) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for name in _SECTIONS:
        path = data_dir / f"{name}.yaml"
        if not path.is_file():
            raise ContentError([f"missing content file {name}.yaml"])
        raw[name] = _read_yaml(path)
    raw["worlds"] = [_read_yaml(p) for p in sorted((data_dir / "worlds").glob("*.yaml"))]
    return raw


def resolve_scenarios(
    content: GameContent, data_dir: Path
) -> tuple[dict[str, ScenarioDefinition], list[str]]:
    scenarios: dict[str, ScenarioDefinition] = {}
    problems: list[str] = []
    for mission in content.campaign.missions:
        ref = mission.scenario
        if ref.id in scenarios:
            continue
        try:
            if ref.source == "registry":
                scenarios[ref.id] = get_scenario(ref.id)
                continue
            if not ref.file:
                problems.append(f"mission {mission.id}: game scenario needs a file")
                continue
            path = data_dir / "scenarios" / ref.file
            if not path.is_file() or path.resolve().parent != (data_dir / "scenarios").resolve():
                problems.append(f"mission {mission.id}: scenario file {ref.file} not found")
                continue
            scenario = load_scenario_file(path)
            if scenario.id != ref.id:
                problems.append(f"mission {mission.id}: scenario file id {scenario.id} != {ref.id}")
                continue
            scenarios[ref.id] = scenario
        except ScenarioNotFoundError:
            problems.append(f"mission {mission.id}: unknown registry scenario {ref.id}")
        except ValueError as exc:  # pydantic validation of a scenario file
            problems.append(f"mission {mission.id}: invalid scenario {ref.id}: {exc}")
    return scenarios, problems


def content_hash(content: GameContent, scenarios: Mapping[str, ScenarioDefinition]) -> str:
    return sha256_hex(
        {
            "content": content.model_dump(mode="json", by_alias=True),
            "scenarios": {k: scenario_content_hash(v) for k, v in sorted(scenarios.items())},
        }
    )


def load_content(data_dir: Path = DATA_DIR) -> LoadedContent:
    from pydantic import ValidationError

    from app.game.content.validate import validate_content

    try:
        content = GameContent.model_validate(read_raw(data_dir))
    except ValidationError as exc:
        raise ContentError(
            [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        ) from None
    scenarios, problems = resolve_scenarios(content, data_dir)
    if problems:
        raise ContentError(problems)
    index = build_index(content)
    loaded = LoadedContent(
        content=content,
        scenarios=MappingProxyType(scenarios),
        content_hash=content_hash(content, scenarios),
        index=index,
    )
    problems = validate_content(loaded)
    if problems:
        raise ContentError(problems)
    return loaded


@lru_cache(maxsize=1)
def default_content() -> LoadedContent:
    return load_content(DATA_DIR)
