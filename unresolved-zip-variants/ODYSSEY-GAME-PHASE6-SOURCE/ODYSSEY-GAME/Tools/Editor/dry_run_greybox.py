#!/usr/bin/env python3
"""Dry-run build_earth_command_greybox.py WITHOUT Unreal, against a recording stub of `unreal`.

What this proves: the script consumes the map definition completely and correctly — the seven
areas are built, every semantic id is bound to an actor, every following light lands in the right
light group on the right object with the right rule, everything is spawned under the Outliner root,
and the scope guard rejects areas outside the vertical slice.
What it does NOT prove: that the UE 5.8 Python API names/signatures are right (stubbed here) —
that remains UNREAL_EDITOR_VERIFICATION_REQUIRED.

    python3 Tools/Editor/dry_run_greybox.py
"""

from __future__ import annotations

import json
import runpy
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Tools" / "Editor" / "build_earth_command_greybox.py"
LAYOUT = ROOT / "Content" / "Systems" / "Greybox" / "L_EarthCommand_Slice.layout.json"


class Rec:
    """Records editor properties; any component lookup returns a per-class child Rec."""

    def __init__(self, kind: str):
        self.kind, self.props, self.components = kind, {}, {}
        self.label, self.folder, self.location = "", "", None
        self.static_mesh_component = self

    def set_editor_property(self, k, v):
        self.props[k] = v

    def get_editor_property(self, k):
        return self.props.get(k)

    def get_component_by_class(self, cls):
        return self.components.setdefault(cls.__name__, Rec(cls.__name__))

    def set_actor_label(self, l):
        self.label = l

    def set_folder_path(self, f):
        self.folder = f

    def get_folder_path(self):
        return self.folder

    def set_actor_scale3d(self, v):
        self.props["scale"] = v

    def set_static_mesh(self, m):
        self.props["mesh"] = m

    def set_box_extent(self, e, update):
        self.props["extent"] = e


def make_stub(spawned: list[Rec], saved: list[str]) -> types.ModuleType:
    u = types.ModuleType("unreal")
    for n in ["StaticMeshActor", "OdysseySemanticAnchor", "OdysseySemanticZone", "OdysseySystemActor",
              "OdysseyPowerConsole", "OdysseyCrewPlaceholder", "PlayerStart", "SkyLight", "PointLight",
              "OdysseySemanticBindingComponent", "BoxComponent", "StaticMeshComponent", "OdysseyInteractableComponent",
              "OdysseyObjectPresentationComponent", "PointLightComponent", "SkyLightComponent"]:
        setattr(u, n, type(n, (), {}))
    u.OdysseyLightRule = lambda: Rec("OdysseyLightRule")
    u.OdysseyConsoleControl = lambda: Rec("OdysseyConsoleControl")
    u.OdysseyIntentParam = lambda: Rec("OdysseyIntentParam")
    u.Text = str
    u.OdysseyLightGroup = lambda: Rec("OdysseyLightGroup")
    u.Vector = lambda *a: tuple(a)
    u.Rotator = lambda *a: tuple(a)
    u.Color = lambda *a: tuple(a)
    u.Name = str
    u.load_asset = lambda p: p
    u.log = lambda m: print(m)
    u.Paths = types.SimpleNamespace(project_content_dir=lambda: str(ROOT / "Content"))
    u.EditorAssetLibrary = types.SimpleNamespace(does_asset_exist=lambda p: False)

    class EAS:
        def spawn_actor_from_class(self, cls, loc, rot):
            r = Rec(cls.__name__)
            r.location = loc
            spawned.append(r)
            return r

        def get_all_level_actors(self):
            return list(spawned)

    class LES:
        def new_level(self, p):
            saved.append("new:" + p)

        def save_current_level(self):
            saved.append("save")

    subs = {"EditorActorSubsystem": EAS(), "LevelEditorSubsystem": LES()}
    u.EditorActorSubsystem, u.LevelEditorSubsystem = type("EditorActorSubsystem", (), {}), type("LevelEditorSubsystem", (), {})
    u.get_editor_subsystem = lambda cls: subs[cls.__name__]
    return u


def run(layout_override: dict | None = None) -> tuple[list[Rec], list[str]]:
    spawned: list[Rec] = []
    saved: list[str] = []
    sys.modules["unreal"] = make_stub(spawned, saved)
    if layout_override is not None:
        tmp = ROOT / "Tools" / "Editor" / ".dry_run_layout.json"
        tmp.write_text(json.dumps(layout_override))
        src = SCRIPT.read_text().replace(
            'os.path.join(unreal.Paths.project_content_dir(), "Systems", "Greybox", "L_EarthCommand_Slice.layout.json")', repr(str(tmp)))
        try:
            exec(compile(src, str(SCRIPT), "exec"), {"__name__": "__main__"})
        finally:
            tmp.unlink()
    else:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    return spawned, saved


def main() -> int:
    layout = json.loads(LAYOUT.read_text())
    spawned, saved = run()
    problems: list[str] = []
    by_label = {a.label: a for a in spawned}
    if saved != ["new:" + layout["map"], "save"]:
        problems.append(f"map lifecycle {saved}")
    outside = [a.label for a in spawned if not a.folder.startswith(layout["outliner_root"] + "/")]
    if outside:
        problems.append(f"spawned outside the Outliner root: {outside}")
    bound = {}
    for a in spawned:
        b = a.components.get("OdysseySemanticBindingComponent")
        if b and "semantic_id" in b.props:
            bound.setdefault(b.props["semantic_id"], []).append(a.label)
    expected = {}
    for area in layout["areas"]:
        if area.get("location"):
            expected[area["location"]] = {area["anchor"]["label"], area["zone"]["label"]}
        for s in area["systems"]:
            expected[s["id"]] = {s["label"]}
    for c in layout["crew"]:
        expected[c["id"]] = {c["label"]}
    for sid, labels in expected.items():
        if set(bound.get(sid, [])) != labels:
            problems.append(f"{sid}: bound to {bound.get(sid)} expected {sorted(labels)}")
    # light groups
    for area in layout["areas"]:
        want: dict[tuple[str, str], set[str]] = {}
        for l in area["lights"]:
            if l.get("follows"):
                want.setdefault((l["follows"], l["rule"]), set()).add(l["label"])
        for (obj, rule), labels in want.items():
            owner = next(a for a in spawned if a.components.get("OdysseySemanticBindingComponent", Rec("x")).props.get("semantic_id") == obj
                         and a.kind in ("OdysseySystemActor", "OdysseyPowerConsole"))
            groups = owner.components["OdysseyObjectPresentationComponent"].props.get("light_groups", [])
            match = [g for g in groups if g.props["name"] == rule]
            if len(match) != 1 or {x.label for x in match[0].props["light_actors"]} != labels:
                problems.append(f"light group {rule} on {obj}: wrong wiring")
                continue
            r = match[0].props["rule"].props
            spec = layout["light_rules"][rule]
            if r["power_scale"] != spec.get("power", {}) or r["mode_scale"] != spec.get("mode", {}) or \
               r["status_scale"] != spec.get("status", {}) or r["warning"] != bool(spec.get("warning", False)):
                problems.append(f"light rule {rule} on {obj}: values differ from the definition")
    # console controls: exactly the definition's action/params per console
    for area in layout["areas"]:
        for sdef in area["systems"]:
            if sdef["class"] != "console":
                continue
            actor = by_label[sdef["label"]]
            if actor.kind != "OdysseyPowerConsole":
                problems.append(f"{sdef['label']} is not a console actor")
                continue
            got = [(c.props["action"], {p.props["name"]: p.props["string_value"] for p in c.props["params"]}) for c in actor.props.get("controls", [])]
            want = [(c["action"], {k: str(x) for k, x in c.get("params", {}).items()}) for c in sdef["controls"]]
            if got != want:
                problems.append(f"{sdef['label']} controls {got} != {want}")
    for need in ("Zone_Training", "Zone_Laboratory", "Sys_TrainingSimulator", "Sys_SampleAnalyzer", "Training_Light0", "Laboratory_Light0"):
        if need not in by_label:
            problems.append(f"missing {need}")
    # scope guard
    bad = json.loads(LAYOUT.read_text())
    bad["areas"].append(dict(bad["areas"][1], id="medical"))
    try:
        run(bad)
        problems.append("scope guard did not reject an area outside the slice")
    except RuntimeError as e:
        if "outside the vertical slice" not in str(e):
            problems.append(f"unexpected error {e}")
    areas = len(layout["areas"])
    if problems:
        print("\n".join("FAIL " + p for p in problems))
        return 1
    print(f"greybox dry run ok: {areas} areas, {len(spawned)} actors, {len(expected)} semantic ids bound, light groups wired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
