"""Unreal Editor Python: build the Earth Command verification greybox from its map definition.

UNREAL_EDITOR_VERIFICATION_REQUIRED — written for UE 5.8 editor scripting; NOT yet run. Nothing
produced by this script is part of the repository until a human has reviewed it in the editor
(Phase 6 §33: AI-generated editor work is experimental until reviewed).

DATA-DRIVEN: every area, anchor, zone, system, light (and which backend object it follows) comes
from Content/Systems/Greybox/L_EarthCommand_Slice.layout.json — the same file the native tests
validate (allowed areas, semantic ids, strategy targets) and the registry generator derives
RequiredInSlice/Binding from. This script contains no layout of its own.

EXACT TARGET (§33) — the only asset this script creates or modifies:
    /Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice   (from the definition's "map")
All actors it spawns live in that map under the Outliner folder "EarthCommandGreybox/…".
It refuses to touch an existing map unless REBUILD = True, and then deletes only actors inside
that folder. It refuses to run if the definition contains an area outside "allowed_areas".

Verification map areas (7): Observation Deck, Main Corridor, Mission Control, Engineering,
Hangar Entrance, Training, Laboratory.

Run inside the editor (after compiling the C++ modules and importing the registry):
    py "<project>/Tools/Editor/build_earth_command_greybox.py"
"""

import json
import math
import os
import sys

import unreal

REBUILD = False
LAYOUT_PATH = os.path.join(unreal.Paths.project_content_dir(), "Systems", "Greybox", "L_EarthCommand_Slice.layout.json")
MESHES = {"cube": "/Engine/BasicShapes/Cube.Cube", "cylinder": "/Engine/BasicShapes/Cylinder.Cylinder"}
WALL = 20.0     # cm
DOOR_H = 260.0  # cm

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Engineering slice art pass: areas may carry "kit", "dressing", "shell_material", systems a "proxy" or
# "material", lights a "fixture". Their assets come from odyssey_slice_assets.py (proxies are NOT
# production meshes; see Tools/Editor/odyssey_kit_geometry.py). Areas without those keys build exactly
# as before.
_EDITOR_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(
    unreal.Paths.project_dir(), "Tools", "Editor")
if _EDITOR_DIR not in sys.path:
    sys.path.insert(0, _EDITOR_DIR)


def v(p):
    return unreal.Vector(float(p[0]), float(p[1]), float(p[2]))


class Builder:
    def __init__(self, layout):
        self.layout = layout
        self.root = layout["outliner_root"]
        self.bound = {}  # semantic id -> actor (for light wiring)
        self.assets = None  # (materials, proxies, kit) once generated

    # ---------------------------------------------------------------- primitives
    def place(self, cls, label, folder, loc, yaw=0.0):
        actor = eas.spawn_actor_from_class(cls, v(loc), unreal.Rotator(0.0, 0.0, float(yaw)))
        actor.set_actor_label(label)
        actor.set_folder_path(f"{self.root}/{folder}")
        return actor

    def block(self, label, folder, center, size, mesh="cube"):
        a = self.place(unreal.StaticMeshActor, label, folder, center)
        a.static_mesh_component.set_static_mesh(unreal.load_asset(MESHES[mesh]))
        a.set_actor_scale3d(unreal.Vector(size[0] / 100.0, size[1] / 100.0, size[2] / 100.0))
        return a

    @staticmethod
    def bind(actor, semantic_id):
        actor.get_component_by_class(unreal.OdysseySemanticBindingComponent).set_editor_property("semantic_id", semantic_id)
        return actor

    # ---------------------------------------------------------------- room shell
    def shell(self, area):
        name = area["name"]
        x0, x1, y0, y1 = area["bounds"]
        h = float(area["height"])
        folder = f"{name}/Shell"
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        shell_mat = self.material(area.get("shell_material"))
        made = [self.block(f"{name}_Floor", folder, (cx, cy, -WALL / 2), (x1 - x0, y1 - y0, WALL)),
                self.block(f"{name}_Ceiling", folder, (cx, cy, h + WALL / 2), (x1 - x0, y1 - y0, WALL))]
        sides = {"N": (x0, x1, y1), "S": (x0, x1, y0), "E": (y0, y1, x1), "W": (y0, y1, x0)}
        for side, (a0, a1, fixed) in sides.items():
            cuts = sorted(tuple(d) for d in area["doors"].get(side, []))
            start, segments = a0, []
            for centre, width in cuts:
                segments.append((start, centre - width / 2))
                start = centre + width / 2
            segments.append((start, a1))
            for i, (s, e) in enumerate(segments):
                if e - s < 1:
                    continue
                if side in ("N", "S"):
                    made.append(self.block(f"{name}_Wall{side}{i}", folder, ((s + e) / 2, fixed, h / 2), (e - s, WALL, h)))
                else:
                    made.append(self.block(f"{name}_Wall{side}{i}", folder, (fixed, (s + e) / 2, h / 2), (WALL, e - s, h)))
            for j, (centre, width) in enumerate(cuts):
                if h - DOOR_H <= 1:
                    continue
                if side in ("N", "S"):
                    made.append(self.block(f"{name}_Lintel{side}{j}", folder, (centre, fixed, (h + DOOR_H) / 2), (width, WALL, h - DOOR_H)))
                else:
                    made.append(self.block(f"{name}_Lintel{side}{j}", folder, (fixed, centre, (h + DOOR_H) / 2), (WALL, width, h - DOOR_H)))
        if shell_mat is not None:
            for a in made:
                a.static_mesh_component.set_material(0, shell_mat)

    # ---------------------------------------------------------------- Engineering art pass (proxies, kit)
    def material(self, key):
        return self.assets[0][key] if (key and self.assets) else None

    def needs_assets(self):
        return any(a.get("kit") or a.get("dressing") for a in self.layout["areas"])

    def placements(self):
        """World placements the finish kit routes services around (Engineering only)."""
        import odyssey_kit_geometry as geo
        eng = next(a for a in self.layout["areas"] if a["id"] == "engineering")
        out, excl, racks = {}, [], []
        for s in eng.get("systems", []):
            x, y, z = s["at"]
            if s.get("proxy"):
                p = geo.PROXY_BUILDERS[s["proxy"]]()
                excl.append(self.envelope_aabb(geo.expected_bounds(p), s["at"], s.get("yaw", 0)))
            else:
                sx, sy, sz = s["size"]
                excl.append((x - sx / 2, x + sx / 2, y - sy / 2, y + sy / 2, z - sz / 2, z + sz / 2))
            key = s["label"].replace("Sys_", "").replace("Store_", "")
            out[{"ThermalPlant": "thermal_plant", "AirHandling": "air_handling"}.get(key, key)] = s["at"]
        for d in eng.get("dressing", []):
            p = geo.PROXY_BUILDERS[d["proxy"]]()
            excl.append(self.envelope_aabb(geo.expected_bounds(p), d["at"], d.get("yaw", 0)))
            if d["proxy"] == "bus_b_cabinet":
                out["bus_b_cabinet"] = d["at"]
            if d["proxy"] == "server_rack":
                racks.append(d["at"])
        xs = sorted(r[0] for r in racks)
        out["server_racks_span"] = (xs[0] - 30, xs[-1] + 30, racks[0][1])
        x0, x1 = eng["bounds"][0] + 10, eng["bounds"][1] - 10
        pitch = (x1 - x0) / round((x1 - x0) / 200)
        out["tray_b_x"] = max((x0 + pitch * (i + 0.5) for i in range(round((x1 - x0) / 200))
                               if x0 + pitch * (i + 0.5) < xs[0] - 60), key=lambda v: v)
        out["exclusions"] = excl
        return out

    @staticmethod
    def envelope_aabb(local_bounds, at, yaw):
        (lx0, ly0, lz0), (lx1, ly1, lz1) = local_bounds
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        pts = [(at[0] + x * c - y * s, at[1] + x * s + y * c) for x in (lx0, lx1) for y in (ly0, ly1)]
        return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts),
                at[2] + lz0, at[2] + lz1)

    def ensure_assets(self):
        if self.assets is None and self.needs_assets():
            import odyssey_slice_assets
            self.assets = odyssey_slice_assets.build_all(self.layout, self.placements())

    def proxy_mesh(self, key):
        return self.assets[1][key]

    @staticmethod
    def tag(actor, *tags):
        actor.set_editor_property("tags", [unreal.Name(t) for t in tags])

    def dressing(self, area):
        """Unreal-only environment actors (no semantic binding, no backend id)."""
        name = area["name"]
        import odyssey_kit_geometry as geo
        for d in area.get("dressing", []):
            a = self.place(unreal.StaticMeshActor, d["label"], f"{name}/Proxies", d["at"], d.get("yaw", 0))
            smc = a.static_mesh_component
            smc.set_static_mesh(self.proxy_mesh(d["proxy"]))
            box_collision = geo.PROXY_BUILDERS[d["proxy"]]().collision == "box"
            smc.set_collision_profile_name("BlockAll" if box_collision else "NoCollision")
            self.tag(a, "OdysseyProxy", "UnrealOnly", "AwaitingProductionMesh")

    def kit(self, area):
        if not area.get("kit") or not self.assets:
            return
        for mesh_name, sm, pivot in self.assets[2]:
            a = self.place(unreal.StaticMeshActor, mesh_name.replace("SM_KIT_", "Kit_"), f"{area['name']}/Kit", pivot)
            smc = a.static_mesh_component
            smc.set_static_mesh(sm)
            smc.set_collision_profile_name("BlockAll" if mesh_name in ("SM_KIT_ENG_Floor", "SM_KIT_ENG_Walls", "SM_KIT_ENG_DoorFrame", "SM_KIT_ENG_CorridorTransition") else "NoCollision")
            self.tag(a, "OdysseyKit", "UnrealOnly")

    # ---------------------------------------------------------------- semantic actors
    def area_actors(self, area):
        name, loc_id = area["name"], area.get("location")
        if loc_id:
            an = area["anchor"]
            self.bind(self.place(unreal.OdysseySemanticAnchor, an["label"], name, an["at"], an["yaw"]), loc_id)
            z = area["zone"]
            zone = self.bind(self.place(unreal.OdysseySemanticZone, z["label"], name, z["center"]), loc_id)
            zone.get_component_by_class(unreal.BoxComponent).set_box_extent(v(z["extent"]), False)
        for s in area.get("systems", []):
            console = s["class"] == "console"
            cls = unreal.OdysseyPowerConsole if console else unreal.OdysseySystemActor
            a = self.bind(self.place(cls, s["label"], name, s["at"], s.get("yaw", 0)), s["id"])
            body = a.get_component_by_class(unreal.StaticMeshComponent)
            if s.get("proxy"):
                # proxy mesh at true scale (pivot bottom-centre); the actor itself is never scaled
                body.set_static_mesh(self.proxy_mesh(s["proxy"]))
                body.set_collision_profile_name("BlockAll")
                self.tag(a, "OdysseyProxy", "AwaitingProductionMesh")
                if console:
                    # diegetic display sits on the main screen of the console proxy
                    disp = a.get_component_by_class(unreal.WidgetComponent)
                    disp.set_editor_property("relative_location", unreal.Vector(-8.0, 0.0, 103.0))
                    disp.set_editor_property("relative_rotation", unreal.Rotator(pitch=12.0, yaw=0.0, roll=0.0))
                    disp.set_editor_property("relative_scale3d", unreal.Vector(0.15, 0.15, 0.15))
            else:
                body.set_static_mesh(unreal.load_asset(MESHES[s.get("mesh", "cube")]))
                a.set_actor_scale3d(unreal.Vector(s["size"][0] / 100.0, s["size"][1] / 100.0, s["size"][2] / 100.0))
                if self.material(s.get("material")) is not None:
                    body.set_material(0, self.material(s.get("material")))
            if console:
                a.set_editor_property("controls", [self.control(c) for c in s.get("controls", [])])
            elif s.get("presented"):
                a.get_component_by_class(unreal.OdysseyInteractableComponent).set_editor_property(
                    "presented_actions", [unreal.Name(p) for p in s["presented"]])
            self.bound[s["id"]] = a
        for b in area.get("blocks", []):
            self.block(b["label"], f"{name}/Shell", b["center"], b["size"])

    @staticmethod
    def control(spec):
        """One physical console control (FOdysseyConsoleControl): action + params from the definition;
        whether it is available is always the backend's answer at runtime."""
        c = unreal.OdysseyConsoleControl()
        c.set_editor_property("action", unreal.Name(spec["action"]))
        c.set_editor_property("label", unreal.Text(spec["label"]))
        params = []
        for k, val in spec.get("params", {}).items():
            p = unreal.OdysseyIntentParam()
            p.set_editor_property("name", unreal.Name(k))
            p.set_editor_property("string_value", str(val))
            params.append(p)
        c.set_editor_property("params", params)
        return c

    def light(self, folder, spec):
        if spec.get("fixture"):
            # ceiling light module: fixture mesh + rect light; its emissive follows the light intensity
            l = self.place(unreal.OdysseyLightFixture, spec["label"], folder, spec["at"], spec.get("fixture_yaw", 0))
            l.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(self.proxy_mesh(spec["fixture"]))
            self.tag(l, "OdysseyProxy", "AwaitingProductionMesh")
            c = l.get_component_by_class(unreal.RectLightComponent)
        else:
            l = self.place(unreal.PointLight, spec["label"], folder, spec["at"])
            c = l.get_component_by_class(unreal.PointLightComponent)
        c.set_editor_property("intensity", float(spec["intensity"]))
        c.set_editor_property("attenuation_radius", float(spec["radius"]))
        r, g, b = spec["color"]
        c.set_editor_property("light_color", unreal.Color(r=int(r * 255), g=int(g * 255), b=int(b * 255), a=255))
        return l

    def lights(self, area):
        """Static lights stay as placed; following lights join a light group on the followed
        object's presentation component, with the rule from the definition."""
        groups = {}  # (object id, rule) -> [light actors]
        for spec in area.get("lights", []):
            l = self.light(f"{area['name']}/Lights", spec)
            if spec.get("follows"):
                groups.setdefault((spec["follows"], spec["rule"]), []).append(l)
        return groups

    def wire(self, groups):
        rules = self.layout["light_rules"]
        per_object = {}
        for (obj, rule_name), actors in groups.items():
            per_object.setdefault(obj, []).append((rule_name, actors))
        for obj, entries in per_object.items():
            target = self.bound.get(obj)
            if target is None:
                raise RuntimeError(f"lights follow {obj}, which has no actor in the map definition")
            pres = target.get_component_by_class(unreal.OdysseyObjectPresentationComponent)
            out = []
            for rule_name, actors in entries:
                r = rules[rule_name]
                rule = unreal.OdysseyLightRule()
                rule.set_editor_property("power_scale", {unreal.Name(k): float(x) for k, x in r.get("power", {}).items()})
                rule.set_editor_property("mode_scale", {unreal.Name(k): float(x) for k, x in r.get("mode", {}).items()})
                rule.set_editor_property("status_scale", {unreal.Name(k): float(x) for k, x in r.get("status", {}).items()})
                rule.set_editor_property("warning", bool(r.get("warning", False)))
                group = unreal.OdysseyLightGroup()
                group.set_editor_property("name", unreal.Name(rule_name))
                group.set_editor_property("rule", rule)
                group.set_editor_property("light_actors", actors)
                out.append(group)
            pres.set_editor_property("light_groups", out)

    # ---------------------------------------------------------------- whole map
    def build(self):
        allowed = set(self.layout["allowed_areas"])
        extra = [a["id"] for a in self.layout["areas"] if a["id"] not in allowed]
        if extra:
            raise RuntimeError(f"map definition contains areas outside the vertical slice: {extra}")
        self.ensure_assets()
        self.prepare_map()
        groups = {}
        for area in self.layout["areas"]:
            self.shell(area)
            self.area_actors(area)
            self.dressing(area)
            self.kit(area)
            for key, actors in self.lights(area).items():
                groups.setdefault(key, []).extend(actors)
        self.wire(groups)
        for c in self.layout["crew"]:
            self.bind(self.place(unreal.OdysseyCrewPlaceholder, c["label"], "Crew", c["at"], c["yaw"]), c["id"])
        ps = self.layout["player_start"]
        self.place(unreal.PlayerStart, ps["label"], "MainCorridor", ps["at"])
        sky = self.place(unreal.SkyLight, "SkyLight", "Lighting", (0, 0, 2000))
        sky.get_component_by_class(unreal.SkyLightComponent).set_editor_property("intensity", 0.3)
        les.save_current_level()
        unreal.log(f"[Odyssey] greybox written to {self.layout['map']} ({len(self.layout['areas'])} areas) — review before committing (§33)")

    def prepare_map(self):
        path = self.layout["map"]
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            if not REBUILD:
                raise RuntimeError(f"{path} exists; set REBUILD = True to rebuild its greybox folder only")
            les.load_level(path)
            for a in eas.get_all_level_actors():
                if str(a.get_folder_path()).startswith(self.root):
                    eas.destroy_actor(a)
        else:
            les.new_level(path)


with open(LAYOUT_PATH, encoding="utf-8") as f:
    Builder(json.load(f)).build()
