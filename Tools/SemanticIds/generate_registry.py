#!/usr/bin/env python3
"""Generate the semantic id registry from the backend's versioned content.

Reads the backend world/narrative content (app/game/content/data/) and writes
Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json in Unreal's DataTable JSON format
(row struct FOdysseySemanticIdRow). The same file is loaded by the engine-independent tests, so
the registry the Unreal level is validated against is exactly the backend's id set.

RequiredInSlice and Binding come from the verification map definition
(Content/Systems/Greybox/L_EarthCommand_Slice.layout.json): an id is required exactly when the
map binds an actor to it, and Binding is that actor's label. A map binding for an id the backend
content does not define is an error.

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
LAYOUT = ROOT / "Content" / "Systems" / "Greybox" / "L_EarthCommand_Slice.layout.json"


def slice_bindings() -> dict[str, str]:
    """Semantic id -> actor label for every id the verification map binds."""
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for area in layout["areas"]:
        if area.get("location"):
            out[area["location"]] = area["anchor"]["label"]
        for s in area.get("systems", []):
            out[s["id"]] = s["label"]
    for c in layout.get("crew", []):
        out[c["id"]] = c["label"]
    return out


def rows(backend: Path) -> list[dict[str, object]]:
    data = backend / "app" / "game" / "content" / "data"
    world = yaml.safe_load((data / "worlds" / "earth_command.yaml").read_text(encoding="utf-8"))
    narrative = yaml.safe_load((data / "narrative.yaml").read_text(encoding="utf-8"))
    bindings = slice_bindings()
    out: list[dict[str, object]] = []

    def add(eid: str, kind: str, name: str, location: str) -> None:
        out.append(
            {
                "Name": eid,
                "Id": eid,
                "Kind": kind,
                "World": world["id"] if kind != "crew" else "",
                "DisplayName": name,
                "Location": location,
                "Binding": bindings.get(eid, ""),
                "RequiredInSlice": eid in bindings,
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
    generated = rows(args.backend.resolve())
    unknown = set(slice_bindings()) - {r["Id"] for r in generated}
    if unknown:
        print(f"map definition binds ids the backend content does not define: {sorted(unknown)}")
        return 1
    text = json.dumps(generated, indent=1, ensure_ascii=False) + "\n"
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        required = sum(1 for r in generated if r["RequiredInSlice"])
        print(f"wrote {OUT.relative_to(ROOT)} ({len(generated)} rows, {required} required in slice)")
        return 0
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        print(f"{OUT.relative_to(ROOT)} is out of date with the backend content or map definition; run --write")
        return 1
    print("semantic id registry matches the backend content and the map definition")
    return 0


if __name__ == "__main__":
    sys.exit(main())
