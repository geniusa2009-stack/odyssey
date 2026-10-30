#!/usr/bin/env python3
"""Generate the semantic id registry from the backend's versioned content.

Reads the backend world/narrative content (app/game/content/data/) and writes
Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json in Unreal's DataTable JSON format
(row struct FOdysseySemanticIdRow). The same file is loaded by the engine-independent tests, so
the registry the Unreal level is validated against is exactly the backend's id set.

    <backend>/.venv/bin/python Tools/SemanticIds/generate_registry.py --backend ../odyssey --write
    <backend>/.venv/bin/python Tools/SemanticIds/generate_registry.py --backend ../odyssey --check

Needs PyYAML (the backend's virtualenv has it). Hidden content (incidents) is never exported:
incident ids reach the client only through events once they have happened.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Content" / "Systems" / "SemanticIds" / "DT_SemanticIds_EarthCommand.json"

# The Phase 6 vertical slice places these in the greybox (Docs/SEMANTIC_IDS.md).
SLICE_REQUIRED = {
    "earth.command.observation_deck",
    "earth.command.mission_control",
    "earth.command.engineering",
    "earth.command.hangar",
    "earth.command.engineering.power_bus_b",
    "earth.command.engineering.station_battery",
    "earth.command.engineering.thermal_plant",
    "earth.command.engineering.air_handling",
    "earth.command.engineering.water_systems",
    "earth.command.engineering.spares_locker",
    "earth.command.mission_control.consoles",
    "earth.command.observation_deck.lunar_telescope",
    "earth.command.hangar.luna01",
    "earth.command.player_kit",
    "maya",
    "omar",
    "sofia",
    "jay",
}


def binding_for(entry_id: str, kind: str) -> str:
    """Recommended greybox actor/anchor name (informational; actors reference ids, not names)."""
    tail = entry_id.split(".")[-1]
    prefix = {"location": "Anchor", "object": "Sys", "container": "Store", "crew": "Crew"}[kind]
    return f"{prefix}_{''.join(part.capitalize() for part in tail.split('_'))}"


def rows(backend: Path) -> list[dict[str, object]]:
    data = backend / "app" / "game" / "content" / "data"
    world = yaml.safe_load((data / "worlds" / "earth_command.yaml").read_text(encoding="utf-8"))
    narrative = yaml.safe_load((data / "narrative.yaml").read_text(encoding="utf-8"))
    out: list[dict[str, object]] = []

    def add(eid: str, kind: str, name: str, location: str) -> None:
        required = eid in SLICE_REQUIRED
        out.append(
            {
                "Name": eid,
                "Id": eid,
                "Kind": kind,
                "World": world["id"] if kind != "crew" else "",
                "DisplayName": name,
                "Location": location,
                "Binding": binding_for(eid, kind) if required else "",
                "RequiredInSlice": required,
            }
        )

    for loc in world["locations"]:
        add(loc["id"], "location", loc["name"], "")
    for obj in world["objects"]:
        kind = "container" if obj.get("container") is not None else "object"
        add(obj["id"], kind, obj["name"], obj["location"])
    for crew in narrative["crew"]:
        add(crew["id"], "crew", f"{crew['name']} — {crew['role']}", "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(rows(args.backend.resolve()), indent=1, ensure_ascii=False) + "\n"
    missing = SLICE_REQUIRED - {r["Id"] for r in json.loads(text)}
    if missing:
        print(f"slice ids missing from backend content: {sorted(missing)}")
        return 1
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} ({len(json.loads(text))} rows)")
        return 0
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        print(f"{OUT.relative_to(ROOT)} is out of date with the backend content; run --write")
        return 1
    print("semantic id registry matches the backend content")
    return 0


if __name__ == "__main__":
    sys.exit(main())
