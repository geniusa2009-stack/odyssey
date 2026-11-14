"""Unreal Editor Python: import the canonical station GLBs (ArtSource/OdysseyImports) and place them in
L_EarthCommand_Slice as Unreal-only dressing. Semantic actors, bindings and collision of gameplay
systems are not changed; a system whose visual is replaced keeps its own (hidden) mesh and collision.

    py "<project>/Tools/Editor/Production/import_station_glbs.py"

Placements (world cm, from Content/Systems/Greybox/L_EarthCommand_Slice.layout.json):
  * Mission Control  - holo projector table, room centre between the anchor and the console row
  * Training         - training simulator hero mesh on Sys_TrainingSimulator (its cube is hidden)
  * Engineering      - drone docking station + inspection drone against the north wall, west of the door
Every placed actor is tagged OdysseyImportedDressing / UnrealOnly so re-running replaces them.
Report: Saved/Odyssey/station_imports_report.json
"""
import json
import os

import unreal

PROJECT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT, "ArtSource", "OdysseyImports")
DST = "/Game/Earth/EarthCommand/Imported"
MAP = "/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice"
TAG = "OdysseyImportedDressing"
REIMPORT = globals().get("ODY_REIMPORT", False)

eal = unreal.EditorAssetLibrary
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
report = {"imports": {}, "placed": []}

# file, folder, combine meshes
ITEMS = [
    ("OD_MCC_HoloProjectorCore", "HoloProjectorCore", True),
    ("OD_TRN_TrainingSimulatorHero", "TrainingSimulator", True),
    ("OD_ENG_DroneDockingStation", "DroneDock", True),
    ("OD_DRONE_InspectionAID03", "InspectionDrone", True),
    ("SM_ODY_StationSlidingDoor", "SlidingDoor", True),
]


def log(m):
    unreal.log(f"[OdysseyImports] {m}")


def combine_value(combine):
    """UE 5.8: InterchangeGenericMeshPipeline.CombineStaticMeshesBehavior replaces bCombineStaticMeshes."""
    enum = unreal.InterchangeCombineStaticMeshesBehavior
    names = [n for n in dir(enum) if n.isupper()]
    log(f"CombineStaticMeshesBehavior members: {names}")
    if combine:
        pick = [n for n in names if "ALL" in n] or [n for n in names if "COMBINE" in n and "NOT" not in n]
    else:
        pick = [n for n in names if "NOT" in n or "SEPARATE" in n or "NONE" in n]
    return getattr(enum, pick[0])


PIPE_DIR = DST + "/Pipelines"


def pipeline_asset(combine):
    """Project copy of the engine's default assets pipeline with the combine behaviour set.
    Interchange override pipelines are referenced by soft path, so they must be assets."""
    name = "PL_ODY_CombinedStaticMesh" if combine else "PL_ODY_SeparateStaticMeshes"
    path = f"{PIPE_DIR}/{name}"
    if not eal.does_asset_exist(path):
        eal.make_directory(PIPE_DIR)
        src = next(p for p in ("/Interchange/Pipelines/DefaultAssetsPipeline", "/Interchange/Pipelines/DefaultGLTFAssetsPipeline")
                   if eal.does_asset_exist(p))
        tools.duplicate_asset(name, PIPE_DIR, unreal.load_asset(src))
    pipe = unreal.load_asset(path)
    pipe.get_editor_property("mesh_pipeline").set_editor_property("combine_static_meshes_behavior", combine_value(combine))
    eal.save_loaded_asset(pipe)
    return path


def interchange_import(filename, dest, combine):
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    src = unreal.InterchangeManager.create_source_data(filename)
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    pipes = [unreal.SoftObjectPath(pipeline_asset(combine))]
    gltf = "/Interchange/Pipelines/DefaultGLTFPipeline"
    if eal.does_asset_exist(gltf):  # keeps glTF PBR material conversion in the stack
        pipes.append(unreal.SoftObjectPath(gltf))
    params.set_editor_property("override_pipelines", pipes)
    ok = mgr.import_asset(dest, src, params)
    log(f"interchange import {os.path.basename(filename)} -> {dest}: {ok} (pipelines {[str(p) for p in pipes]})")


def meshes_in(folder):
    out = []
    for path in eal.list_assets(folder, recursive=True, include_folder=False):
        a = eal.load_asset(path)
        if isinstance(a, unreal.StaticMesh):
            out.append(a)
    return out


def import_all():
    result = {}
    for file, folder, combine in ITEMS:
        dest = f"{DST}/{folder}"
        existing = meshes_in(dest)
        if existing and (REIMPORT or (combine and len(existing) > 1)):
            log(f"clearing {dest} ({len(existing)} meshes) for a combined re-import")
            eal.delete_directory(dest)
            existing = []
        if not existing:
            interchange_import(os.path.join(SRC, file + ".glb"), dest, combine)
            for a in eal.list_assets(dest, recursive=True, include_folder=False):
                eal.save_asset(a, only_if_is_dirty=True)
        ms = meshes_in(dest)
        if not ms:
            raise RuntimeError(f"no static mesh imported for {file}")
        sm = max(ms, key=lambda m: m.get_num_triangles(0))
        if sme.get_simple_collision_count(sm) == 0:
            sme.add_simple_collisions(sm, unreal.ScriptCollisionShapeType.BOX)
            eal.save_loaded_asset(sm)
        bb = sm.get_bounding_box()
        size = [round(bb.max.x - bb.min.x, 1), round(bb.max.y - bb.min.y, 1), round(bb.max.z - bb.min.z, 1)]
        report["imports"][file] = {"mesh": sm.get_path_name(), "static_meshes": len(ms), "triangles": sm.get_num_triangles(0),
                                   "size_cm": size, "min": [round(bb.min.x, 1), round(bb.min.y, 1), round(bb.min.z, 1)],
                                   "materials": len(sm.get_editor_property("static_materials")),
                                   "assets": len(eal.list_assets(dest, recursive=True, include_folder=False))}
        log(f"{file}: {report['imports'][file]}")
        result[folder] = sm
    return result


def place(sm, label, center_xy, target_width, yaw, width_axis="auto", z_floor=0.0, folder="Imported"):
    """Uniformly scale `sm` so its larger horizontal extent equals target_width (cm, None = keep),
    centre it on center_xy with its bottom on z_floor, rotated by yaw."""
    bb = sm.get_bounding_box()
    sx, sy = bb.max.x - bb.min.x, bb.max.y - bb.min.y
    s = 1.0 if target_width is None else target_width / max(sx, sy)
    a = eas.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(s, s, s))
    # offset so the mesh bounds centre (XY) lands on center_xy and the bottom on the floor
    cx, cy = (bb.min.x + bb.max.x) * 0.5 * s, (bb.min.y + bb.max.y) * 0.5 * s
    rot = unreal.MathLibrary.rotate_angle_axis(unreal.Vector(cx, cy, 0), yaw, unreal.Vector(0, 0, 1))
    a.set_actor_location(unreal.Vector(center_xy[0] - rot.x, center_xy[1] - rot.y, z_floor - bb.min.z * s), False, False)
    a.set_actor_label(label)
    a.set_folder_path(f"Greybox/{folder}")
    a.tags = [unreal.Name(TAG), unreal.Name("UnrealOnly")]
    a.static_mesh_component.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    report["placed"].append({"label": label, "scale": round(s, 4), "location": [round(v, 1) for v in (a.get_actor_location().x, a.get_actor_location().y, a.get_actor_location().z)],
                             "yaw": yaw, "footprint_cm": [round(sx * s, 1), round(sy * s, 1)], "height_cm": round((bb.max.z - bb.min.z) * s, 1)})
    return a


def find(label):
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def place_all(sm):
    les.load_level(MAP)
    for a in eas.get_all_level_actors():
        if unreal.Name(TAG) in a.tags:
            eas.destroy_actor(a)
    # Mission Control: holo table, 2.6 m across, between the anchor (1400, 450) and the console row (y 1150)
    place(sm["HoloProjectorCore"], "PROD_MCC_HoloProjectorTable", (1400, 790), 260.0, 0.0, folder="MissionControl")
    # Training: hero simulator over Sys_TrainingSimulator (300 x 150 x 200 at 2700, 1000); console keeps its collision
    # the image-to-3D mesh faces +Y after import; turn it to face the room (the player enters from -Y)
    sim = place(sm["TrainingSimulator"], "PROD_TRN_TrainingSimulator", (2700, 1000), 300.0, 180.0, folder="Training")
    sys_actor = find("Sys_TrainingSimulator")
    if sys_actor:
        for c in sys_actor.get_components_by_class(unreal.StaticMeshComponent):
            c.set_editor_property("visible", False)
        report["hidden_proxy"] = "Sys_TrainingSimulator (mesh hidden; collision and interaction unchanged)"
    # Engineering: drone dock on the north wall west of the door (door spans x 2380-2620 at y -200)
    dock = sm["DroneDock"]
    bb = dock.get_bounding_box()
    depth = min(bb.max.x - bb.min.x, bb.max.y - bb.min.y)
    yaw = globals().get("ODY_DOCK_YAW", 180.0)  # dock window faces into the room (checked in STATION_03)
    place(dock, "PROD_ENG_DroneDockingStation", (2130, -200 - 40 - depth * 0.5), None, yaw, folder="Engineering")
    drone = place(sm["InspectionDrone"], "PROD_ENG_InspectionDrone_AID03", (2420, -560), None, yaw + 25.0, z_floor=230.0, folder="Engineering")
    drone.static_mesh_component.set_collision_profile_name("NoCollision")  # hovering above head height
    les.save_current_level()


def main():
    eal.make_directory(DST)
    sm = import_all()
    place_all(sm)
    out = os.path.join(PROJECT, "Saved", "Odyssey")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "station_imports_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    log("done")


if __name__ == "__main__":
    main()
