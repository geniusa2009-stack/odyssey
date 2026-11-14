"""Unreal Editor Python: final environment pass for Mission Control and Training, the functional station
sliding doors and the Mission Control holographic table, placed in L_EarthCommand_Slice.

    py "<project>/Tools/Editor/Production/build_room_finish.py"

Everything placed here is Unreal-only presentation (tag OdysseyRoomFinish); semantic actors, bindings
and the gameplay collision of systems are untouched (a system whose look is replaced keeps its hidden
proxy collision). Re-running rebuilds the assets in place and re-places every tagged actor.

  * room kits       odyssey_kit_geometry.engineering_kit() for MissionControl / Training (walls with
                    kick / trim / panels / ribs / vents, 1 m floor plates, 2 m ceiling bays + beams)
  * Mission Control holo table (AOdysseyHoloTable) on the projector, floor inlay, light halo, console
                    row (pack OD_MCC_MainConsole + chairs), wall displays, server racks, ORION
                    terminal, utility panel / ventilation, ceiling fixtures, signage
  * Training        safety zone + floor marking around the simulator, instructor station, monitoring
                    desk with displays, storage, utility panel, ceiling fixtures, signage
  * doors           SM_ODY_StationSlidingDoor split into frame / leaf L / leaf R (offline glTF split),
                    AOdysseySlidingDoor on the Mission Control and Training corridor doorways
Report: Saved/Odyssey/room_finish_report.json
"""
import json
import math
import os
import struct
import sys

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR = os.path.dirname(HERE)
for p in (HERE, EDITOR):
    if p not in sys.path:
        sys.path.insert(0, p)
import odyssey_kit_geometry as kg  # noqa: E402
import odyssey_slice_assets as asl  # noqa: E402
import odyssey_space_geometry as sg  # noqa: E402
import build_space_experience as bse  # noqa: E402
import import_station_glbs as isg  # noqa: E402

PROJECT = os.path.abspath(unreal.Paths.project_dir())
LAYOUT = os.path.join(PROJECT, "Content", "Systems", "Greybox", "L_EarthCommand_Slice.layout.json")
MAP = "/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice"
ROOMS = "/Game/Earth/EarthCommand/Rooms"
TEX_DIR, MAT_DIR, MESH_DIR = ROOMS + "/Textures", ROOMS + "/Materials", ROOMS + "/Meshes"
HOLO_DIR, DOOR_DIR, PACK_DIR = ROOMS + "/Hologram", ROOMS + "/Door", "/Game/Earth/EarthCommand/Imported/Pack"
EQUIP = "/Game/Earth/EarthCommand/Engineering/Production/Equipment"
TAG = "OdysseyRoomFinish"
STATION_TEX = os.path.join(PROJECT, "ArtSource", "OdysseyStation", "Textures")
PACK_GLB = os.path.join(PROJECT, "ArtSource", "OdysseyAssetPack", "GLB")
SPLIT_DIR = os.path.join(PROJECT, "ArtSource", "OdysseyImports", "Split")

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
report = {"meshes": {}, "imports": {}, "placed": [], "doors": []}


def log(m):
    unreal.log(f"[OdysseyRooms] {m}")


# ------------------------------------------------------------------------------------------ door split
def split_door():
    """SM_ODY_StationSlidingDoor.glb -> frame / leaf L / leaf R GLBs (same binary buffer, the root's
    children partitioned). Leaves keep their closed-position transforms."""
    src = os.path.join(PROJECT, "ArtSource", "OdysseyImports", "SM_ODY_StationSlidingDoor.glb")
    data = open(src, "rb").read()
    jlen = struct.unpack("<I", data[12:16])[0]
    j = json.loads(data[20:20 + jlen])
    rest = data[20 + jlen:]  # BIN chunk header + data, unchanged
    nodes = j["nodes"]
    root = j["scenes"][j.get("scene", 0)]["nodes"][0]
    kids = nodes[root]["children"]
    by = {nodes[k].get("name"): k for k in kids}
    groups = {"Frame": [by[n] for n in ("Frame_Outer", "Threshold", "Rail_Housing_Top", "Access_Panel") if n in by],
              "LeafL": [by["Door_Leaf_L"]], "LeafR": [by["Door_Leaf_R"]]}
    os.makedirs(SPLIT_DIR, exist_ok=True)
    out = {}
    for name, children in groups.items():
        jj = json.loads(json.dumps(j))
        jj["nodes"][root]["children"] = children
        body = json.dumps(jj, separators=(",", ":")).encode("utf-8")
        body += b" " * ((4 - len(body) % 4) % 4)
        glb = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(body) + len(rest)) + struct.pack("<II", len(body), 0x4E4F534A) + body + rest
        path = os.path.join(SPLIT_DIR, f"SM_ODY_StationSlidingDoor_{name}.glb")
        open(path, "wb").write(glb)
        out[name] = path
    return out


def import_combined(path, dest):
    ms = isg.meshes_in(dest)
    if len(ms) != 1:
        if ms:
            eal.delete_directory(dest)
        isg.interchange_import(path, dest, True)
        for a in eal.list_assets(dest, recursive=True, include_folder=False):
            eal.save_asset(a, only_if_is_dirty=True)
        ms = isg.meshes_in(dest)
    sm = max(ms, key=lambda m: m.get_num_triangles(0))
    bb = sm.get_bounding_box()
    report["imports"][os.path.basename(path)] = {"mesh": sm.get_path_name(), "min": [round(v, 1) for v in (bb.min.x, bb.min.y, bb.min.z)],
                                                 "max": [round(v, 1) for v in (bb.max.x, bb.max.y, bb.max.z)], "meshes": len(ms)}
    return sm


def collision(sm, mode):
    sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    body = sm.get_editor_property("body_setup")
    if mode == "complex":
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    elif mode == "box" and sme.get_simple_collision_count(sm) == 0:
        sme.add_simple_collisions(sm, unreal.ScriptCollisionShapeType.BOX)
    eal.save_loaded_asset(sm)


# ------------------------------------------------------------------------------------------ textures / materials
STATION_TEXTURES = ["T_MCC_MainDisplay", "T_MCC_SystemsDisplay", "T_MCC_CommsDisplay", "T_TRN_SessionDisplay", "T_TRN_MonitorDisplay",
                    "T_Sign_MissionControl", "T_Sign_Training", "T_Floor_KeepClear"]


def import_textures():
    tasks = []
    for n in STATION_TEXTURES:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", os.path.join(STATION_TEX, n + ".png"))
        t.set_editor_property("destination_path", TEX_DIR)
        t.set_editor_property("destination_name", n)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    return {n: unreal.load_asset(f"{TEX_DIR}/{n}") for n in STATION_TEXTURES}


def build_materials(tex):
    F1, F3 = bse.F1, bse.F3
    bse.MAT_DIR = MAT_DIR  # create the room materials next to the room content
    color = unreal.MaterialSamplerType.SAMPLERTYPE_COLOR

    # diegetic screen: emissive texture with a faint scan pattern and a soft dark floor
    m = bse.material("M_ODY_StationScreen", None, unreal.MaterialShadingModel.MSM_UNLIT)
    t = bse.texparam(m, "Screen", tex["T_MCC_MainDisplay"].get_path_name(), color, -900, 0)
    uv = bse.expr(m, unreal.MaterialExpressionTextureCoordinate, -900, 300)
    tm = bse.expr(m, unreal.MaterialExpressionTime, -900, 400)
    inten = bse.scalar(m, "Intensity", 2.2, -900, 500)
    c = bse.custom(m, "float scan = 0.94 + 0.06 * sin(UV.y * 900.0 - T * 4.0);\nreturn (Tex * 0.97 + 0.012) * scan * I;", ["Tex", "UV", "T", "I"], F3, -500, 0, "Screen")
    bse.link(t, c, "Tex", "RGB"); bse.link(uv, c, "UV"); bse.link(tm, c, "T"); bse.link(inten, c, "I")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    screen = bse.finish(m)

    # printed sign / floor marking (lit)
    m = bse.material("M_ODY_StationSign", None, None)
    t = bse.texparam(m, "Print", tex["T_Sign_MissionControl"].get_path_name(), color, -700, 0)
    rough = bse.scalar(m, "Roughness", 0.55, -700, 300)
    mel.connect_material_property(t, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    sign = bse.finish(m)

    # hologram: additive, two-sided, fresnel rim + texture luminance + scanlines + flicker in the actor
    m = bse.material("M_ODY_Hologram", unreal.BlendMode.BLEND_ADDITIVE, unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True)
    t = bse.texparam(m, "Source", "/Game/Space/Textures/T_Earth_Albedo", color, -1100, 0)
    uv = bse.expr(m, unreal.MaterialExpressionTextureCoordinate, -1100, 300)
    nws = bse.expr(m, unreal.MaterialExpressionVertexNormalWS, -1100, 400)
    cam = bse.expr(m, unreal.MaterialExpressionCameraVectorWS, -1100, 500)
    tm = bse.expr(m, unreal.MaterialExpressionTime, -1100, 600)
    col = bse.vector(m, "Color", unreal.LinearColor(0.1, 0.52, 0.66, 1), -1100, 700)
    inten = bse.scalar(m, "Intensity", 1.0, -1100, 800)
    use = bse.scalar(m, "UseTexture", 0.0, -1100, 900)
    c = bse.custom(m, """
float ndv = abs(dot(normalize(N), normalize(V)));
float rim = pow(1.0 - ndv, 2.2);
float lum = dot(Tex, float3(0.3, 0.59, 0.11));
float body = Use > 0.5 ? (0.03 + pow(lum, 0.8) * 3.4) : 0.55;
float scan = 0.78 + 0.22 * saturate(sin(UV.y * 260.0 - T * 2.6) * 0.5 + 0.5);
return Color * (body * 0.75 + rim * 1.1) * scan * I;""", ["Tex", "UV", "N", "V", "T", "Color", "I", "Use"], F3, -600, 300, "Hologram")
    for src, pin, out in ((t, "Tex", "RGB"), (uv, "UV", ""), (nws, "N", ""), (cam, "V", ""), (tm, "T", ""), (col, "Color", ""), (inten, "I", ""), (use, "Use", "")):
        bse.link(src, c, pin, out)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    holo = bse.finish(m)

    mi = {"screen": screen, "sign": sign, "holo": holo}
    for n in ("T_MCC_MainDisplay", "T_MCC_SystemsDisplay", "T_MCC_CommsDisplay", "T_TRN_SessionDisplay", "T_TRN_MonitorDisplay"):
        mi[n] = bse.instance("MI_Screen_" + n[2:], screen, {"Intensity": 5.5}, {}, {"Screen": tex[n]})
    for n in ("T_Sign_MissionControl", "T_Sign_Training", "T_Floor_KeepClear"):
        mi[n] = bse.instance("MI_Print_" + n[2:], sign, {"Roughness": 0.6 if "Floor" in n else 0.45}, {}, {"Print": tex[n]})
    return mi


# ------------------------------------------------------------------------------------------ meshes
def slot_materials(mesh, kit_mi, extra):
    out = {}
    for slot in mesh.sections:
        key = slot.lower()
        out[slot] = extra.get(slot) or kit_mi.get(key) or kit_mi["gunmetal"]
    return out


def build_meshes(kit_mi, mi):
    def tri(name, mesh, folder, extra=None):
        sm = bse.build_tri_mesh(name, mesh, slot_materials(mesh, kit_mi, extra or {}), folder)
        report["meshes"][name] = bse.report["meshes"].get(name)
        return sm
    holo = {"Holo": mi["holo"]}
    return {
        "HoloSphere": tri("SM_HOLO_Sphere", sg.sphere(100.0, 64, 32, slot="Holo"), HOLO_DIR, holo),
        "HoloRing": tri("SM_HOLO_Ring", sg.holo_torus(), HOLO_DIR, holo),
        "HoloDisc": tri("SM_HOLO_Disc", sg.holo_disc(), HOLO_DIR, holo),
        "HoloBeam": tri("SM_HOLO_Beam", sg.holo_beam(), HOLO_DIR, holo),
        "HoloMarker": tri("SM_HOLO_Marker", sg.holo_marker(), HOLO_DIR, holo),
        "HoloBead": tri("SM_HOLO_Bead", sg.sphere(100.0, 12, 6, slot="Holo"), HOLO_DIR, holo),
        "Inlay": tri("SM_MCC_FloorInlay", sg.mcc_floor_inlay(), MESH_DIR),
        "Halo": tri("SM_MCC_LightHalo", sg.mcc_halo(420.0, 330.0, 210.0), MESH_DIR),
        "DisplayWide": tri("SM_ROOM_DisplayWide", sg.display_frame(560.0, 210.0), MESH_DIR, {"Screen": mi["T_MCC_MainDisplay"]}),
        "DisplaySmall": tri("SM_ROOM_DisplaySmall", sg.display_frame(200.0, 125.0), MESH_DIR, {"Screen": mi["T_MCC_SystemsDisplay"]}),
        "Sign": tri("SM_ROOM_SignPanel", sg.display_frame(300.0, 75.0, depth=4.0, bezel=3.0), MESH_DIR, {"Screen": mi["T_Sign_MissionControl"]}),
        "SafetyBorder": tri("SM_TRN_SafetyBorder", sg.safety_border(400.0, 430.0), MESH_DIR),
        "FloorText": tri("SM_ROOM_FloorMarking", sg.floor_decal_plane(300.0, 75.0), MESH_DIR, {"Decal": mi["T_Floor_KeepClear"]}),
        "StatusStrip": tri("SM_DOOR_StatusStrip", _strip(), DOOR_DIR),
        "Desk": tri("SM_ROOM_MonitoringDesk", _desk(), MESH_DIR),
    }


def _strip():
    m = sg.Mesh()
    m.box("Ion", (0.0, 0.0, 0.0), (5.0, 2.0, 70.0))
    sg._fix_winding(m)
    return m


def _desk():
    m = sg.Mesh()
    m.box("White", (0.0, 0.0, 73.0), (70.0, 200.0, 4.0))
    m.box("Alu", (32.0, 0.0, 70.5), (6.0, 200.0, 2.0))
    for y in (-92.0, 92.0):
        m.box("Gunmetal", (0.0, y, 36.0), (64.0, 6.0, 72.0))
    m.box("Graphite", (-28.0, 0.0, 40.0), (6.0, 178.0, 60.0))
    sg._fix_winding(m)
    return m


def build_kits(kit_mi, layout):
    areas = {a["name"]: a for a in layout["areas"]}
    cor = areas["MainCorridor"]
    out = {}
    for name, short in (("MissionControl", "MCC"), ("Training", "TRN"), ("MainCorridor", "COR")):
        area = areas[name]
        k = kg.engineering_kit(area, cor)
        k["walls"] = k["walls"] + finish_extras(area, k)
        for part, coll in (("floor", "complex"), ("walls", "complex"), ("ceiling", "none")):
            path = f"{ROOMS}/{name}/Kit/SM_KIT_{short}_{part.capitalize()}"
            sm, tris = asl.build_mesh(path, k[part], kit_mi, coll, {"OdysseyKit": name, "Pivot": "room floor centre"})
            out[(name, part)] = (sm, (k["cx"], k["cy"], 0.0))
            report["meshes"][path.rsplit("/", 1)[1]] = asl.validate_mesh(sm)
    return out


def finish_extras(area, k):
    """Close the shell above the wall system: a graphite cornice under the ceiling on every wall and a
    white header panel above every door opening (room side)."""
    ix0, ix1, iy0, iy1 = k["interior"]
    cx, cy, H = k["cx"], k["cy"], k["H"]
    top = H - 36.0
    P = [kg.box("graphite", ix0 - cx, ix1 - cx, iy1 - 12 - cy, iy1 - cy, top, H - 4),
         kg.box("graphite", ix0 - cx, ix1 - cx, iy0 - cy, iy0 + 12 - cy, top, H - 4),
         kg.box("graphite", ix0 - cx, ix0 + 12 - cx, iy0 - cy, iy1 - cy, top, H - 4),
         kg.box("graphite", ix1 - 12 - cx, ix1 - cx, iy0 - cy, iy1 - cy, top, H - 4)]
    for side, lst in area["doors"].items():
        for c, w in lst:
            s0, s1, z0 = c - w / 2 - 24, c + w / 2 + 24, 266.0
            if top <= z0:
                continue
            if side == "N":
                P.append(kg.box("white", s0 - cx, s1 - cx, iy1 - 10 - cy, iy1 - cy, z0, top))
            elif side == "S":
                P.append(kg.box("white", s0 - cx, s1 - cx, iy0 - cy, iy0 + 10 - cy, z0, top))
            elif side == "E":
                P.append(kg.box("white", ix1 - 10 - cx, ix1 - cx, s0 - cy, s1 - cy, z0, top))
            else:
                P.append(kg.box("white", ix0 - cx, ix0 + 10 - cx, s0 - cy, s1 - cy, z0, top))
    return P


# ------------------------------------------------------------------------------------------ placement
def spawn(sm, label, loc, yaw=0.0, scale=1.0, folder="Rooms", coll="NoCollision", mats=None, visible=True):
    a = eas.spawn_actor_from_object(sm, unreal.Vector(*loc), unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    a.set_actor_label(label)
    a.set_folder_path(f"Greybox/{folder}")
    a.tags = [unreal.Name(TAG), unreal.Name("UnrealOnly")]
    c = a.static_mesh_component
    c.set_collision_profile_name(coll)
    for i, m in (mats or {}).items():
        c.set_material(i, m)
    report["placed"].append({"label": label, "loc": [round(v, 1) for v in loc], "yaw": yaw, "scale": scale})
    return a


def screen_slot(sm):
    names = [str(m.material_slot_name) for m in sm.get_editor_property("static_materials")]
    return next(i for i, n in enumerate(names) if "Graphite" not in n)  # the face slot (housing is graphite)


def fixture(mesh, label, loc, yaw, intensity, folder):
    a = eas.spawn_actor_from_class(unreal.OdysseyLightFixture, unreal.Vector(*loc), unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw))
    a.set_actor_label(label)
    a.set_folder_path(f"Greybox/{folder}")
    a.tags = [unreal.Name(TAG), unreal.Name("UnrealOnly")]
    a.get_editor_property("fixture").set_static_mesh(mesh)
    lc = a.get_editor_property("light")
    lc.set_editor_property("intensity", intensity)
    lc.set_editor_property("use_temperature", True)
    lc.set_editor_property("temperature", 5200.0)
    report["placed"].append({"label": label, "loc": list(loc), "light": intensity})
    return a


def find(label):
    return next((a for a in eas.get_all_level_actors() if a.get_actor_label() == label), None)


def hide_mesh(label):
    a = find(label)
    if a:
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            c.set_editor_property("visible", False)
    return a is not None


def place_door(parts, label, x, y, folder):
    frame, leaf_l, leaf_r, strip = parts
    # the "left" panel is whichever leaf sits on -X after import (it slides toward -X)
    cx = lambda m: (m.get_bounding_box().min.x + m.get_bounding_box().max.x) * 0.5
    if cx(leaf_l) > cx(leaf_r):
        leaf_l, leaf_r = leaf_r, leaf_l
    fb, lb = frame.get_bounding_box(), leaf_l.get_bounding_box()
    frame_h = fb.max.z - fb.min.z
    s = 264.0 / frame_h  # cover the 260 cm shell opening
    d = eas.spawn_actor_from_class(unreal.OdysseySlidingDoor, unreal.Vector(x, y, -fb.min.z * s), unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0))
    d.set_actor_scale3d(unreal.Vector(s, s, s))
    d.set_actor_label(label)
    d.set_folder_path(f"Greybox/{folder}")
    d.tags = [unreal.Name(TAG), unreal.Name("UnrealOnly")]
    d.get_editor_property("frame").set_static_mesh(frame)
    d.get_editor_property("panel_left").set_static_mesh(leaf_l)
    d.get_editor_property("panel_right").set_static_mesh(leaf_r)
    for comp, sx, sy in (("status_left", -1, -1), ("status_right", 1, 1)):
        c = d.get_editor_property(comp)
        c.set_static_mesh(strip)
        c.set_editor_property("relative_location", unreal.Vector(sx * (fb.max.x - 14.0), sy * (fb.max.y + 1.5), 120.0))
    leaf_w = lb.max.x - lb.min.x
    d.set_editor_property("open_distance", leaf_w * 0.96)
    report["doors"].append({"label": label, "scale": round(s, 3), "frame_cm": [round((fb.max.x - fb.min.x) * s, 1), round((fb.max.y - fb.min.y) * s, 1), round(frame_h * s, 1)],
                            "leaf_width_cm": round(leaf_w * s, 1), "open_distance_local": round(leaf_w * 0.96, 1)})
    return d


def place_all(kits, meshes, mi, door_parts, pack):
    les.load_level(MAP)
    for a in eas.get_all_level_actors():
        if unreal.Name(TAG) in a.tags:
            eas.destroy_actor(a)
    light_mesh = unreal.load_asset(f"{EQUIP}/OD_ENV_CeilingLight/OD_ENV_CeilingLight")
    rack = unreal.load_asset(f"{EQUIP}/OD_SYS_ServerRack/OD_SYS_ServerRack")
    orion = unreal.load_asset(f"{EQUIP}/OD_SYS_ORIONTerminal/OD_SYS_ORIONTerminal")
    utility = unreal.load_asset(f"{EQUIP}/OD_ENV_WallUtilityPanel/OD_ENV_WallUtilityPanel")
    vent = unreal.load_asset(f"{EQUIP}/OD_ENV_VentilationModule/OD_ENV_VentilationModule")
    crate = unreal.load_asset(f"{EQUIP}/OD_PROP_SupplyCrate/OD_PROP_SupplyCrate")

    # ---------------- room kits
    for (room, part), (sm, pivot) in kits.items():
        spawn(sm, f"Kit_{room}_{part.capitalize()}", pivot, folder=f"{room}/Kit", coll="BlockAll" if part != "ceiling" else "NoCollision")

    # ---------------- Mission Control (x 800..2000, y 200..1400, h 420); table at (1400, 790)
    F = "MissionControl"
    TX, TY = 1400.0, 790.0
    spawn(meshes["Inlay"], "MCC_FloorInlay", (TX, TY, 0.0), folder=F)
    spawn(meshes["Halo"], "MCC_LightHalo", (TX, TY, 0.0), folder=F)
    holo = eas.spawn_actor_from_class(unreal.OdysseyHoloTable, unreal.Vector(TX, TY, 96.0), unreal.Rotator(0, 0, 0))
    holo.set_editor_property("volume_radius", 120.0)
    holo.set_editor_property("volume_height", 88.0)
    holo.set_actor_label("MCC_HoloMissionTable")
    holo.set_folder_path(f"Greybox/{F}")
    holo.tags = [unreal.Name(TAG), unreal.Name("UnrealOnly")]
    for prop, val in (("sphere_mesh", meshes["HoloSphere"]), ("ring_mesh", meshes["HoloRing"]), ("bead_mesh", meshes["HoloBead"]),
                      ("disc_mesh", meshes["HoloDisc"]), ("beam_mesh", meshes["HoloBeam"]), ("marker_mesh", meshes["HoloMarker"]),
                      ("holo_material", mi["holo"]), ("earth_texture", unreal.load_asset("/Game/Space/Textures/T_Earth_Albedo")),
                      ("moon_texture", unreal.load_asset("/Game/Space/Textures/T_Moon_Albedo")), ("mars_texture", unreal.load_asset("/Game/Space/Textures/T_Mars_Albedo"))):
        holo.set_editor_property(prop, val)
    report["placed"].append({"label": "MCC_HoloMissionTable", "loc": [TX, TY, 96.0]})
    # console row on the north wall: one three-segment console, operators face north
    report["hidden_proxies"] = {"Sys_Consoles": hide_mesh("Sys_Consoles")}
    spawn(pack["console"], "MCC_MainConsole", (1400.0, 1215.0, 0.0), yaw=-90.0, folder=F, coll="BlockAll")
    for i, x in enumerate((1180.0, 1400.0, 1620.0)):
        spawn(pack["chair"], f"MCC_OperatorChair_{i + 1}", (x, 1055.0 if i != 1 else 1040.0, 0.0), yaw=90.0 + (-12, 0, 12)[i], folder=F, coll="BlockAll")
    wide = meshes["DisplayWide"]
    spawn(wide, "MCC_Display_Main", (1400.0, 1378.0, 262.0), yaw=-90.0, folder=F)
    small = meshes["DisplaySmall"]
    ss = screen_slot(small)
    spawn(small, "MCC_Display_Systems", (1010.0, 1378.0, 250.0), yaw=-90.0, folder=F, mats={ss: mi["T_MCC_SystemsDisplay"]})
    spawn(small, "MCC_Display_Comms", (1790.0, 1378.0, 250.0), yaw=-90.0, folder=F, mats={ss: mi["T_MCC_CommsDisplay"]})
    for i, y in enumerate((560.0, 622.0, 684.0)):
        spawn(rack, f"MCC_ServerRack_{i + 1}", (872.0, y, 0.0), yaw=0.0, folder=F, coll="BlockAll")
    spawn(orion, "MCC_ORION_Terminal", (1932.0, 470.0, 0.0), yaw=180.0, folder=F, coll="BlockAll")
    spawn(utility, "MCC_WallUtilityPanel", (822.0, 960.0, 150.0), yaw=0.0, folder=F)
    spawn(vent, "MCC_VentModule", (1988.0, 980.0, 330.0), yaw=180.0, folder=F)
    for i, (x, y) in enumerate(((1050.0, 430.0), (1750.0, 430.0), (1050.0, 1150.0), (1750.0, 1150.0))):
        fixture(light_mesh, f"MCC_CeilingLight_{i + 1}", (x, y, 414.0), 90.0, 2600.0, F)
    sign = meshes["Sign"]
    sgs = screen_slot(sign)
    spawn(sign, "MCC_Sign_Corridor", (1740.0, 189.0, 200.0), yaw=-90.0, folder=F, mats={sgs: mi["T_Sign_MissionControl"]})
    spot = eas.spawn_actor_from_class(unreal.SpotLight, unreal.Vector(TX, TY, 400.0), unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0))
    spot.set_actor_label("MCC_TableKeyLight")
    spot.set_folder_path(f"Greybox/{F}")
    spot.tags = [unreal.Name(TAG), unreal.Name("UnrealOnly")]
    sc = spot.get_component_by_class(unreal.SpotLightComponent)
    sc.set_editor_property("intensity", 9000.0)
    sc.set_editor_property("outer_cone_angle", 30.0)
    sc.set_editor_property("inner_cone_angle", 12.0)
    sc.set_editor_property("source_radius", 30.0)
    sc.set_editor_property("use_temperature", True)
    sc.set_editor_property("temperature", 5600.0)
    sc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

    # ---------------- Training (x 2200..3200, y 200..1200, h 380); simulator at (2700, 1000)
    F = "Training"
    spawn(meshes["SafetyBorder"], "TRN_SafetyZone", (2700.0, 985.0, 0.0), folder=F)
    spawn(meshes["FloorText"], "TRN_FloorMarking_KeepClear", (2700.0, 740.0, 0.0), yaw=-90.0, folder=F)  # reads for someone approaching from the south
    toward = math.degrees(math.atan2(1000.0 - 600.0, 2700.0 - 2380.0))
    spawn(pack["console"], "TRN_InstructorStation", (2380.0, 600.0, 0.0), yaw=toward + 180.0, scale=0.55, folder=F, coll="BlockAll")
    back = math.radians(toward + 180.0)
    spawn(pack["chair"], "TRN_InstructorChair", (2380.0 + 105 * math.cos(back), 600.0 + 105 * math.sin(back), 0.0), yaw=toward, folder=F, coll="BlockAll")
    spawn(meshes["Desk"], "TRN_MonitoringDesk", (3140.0, 760.0, 0.0), yaw=0.0, folder=F, coll="BlockAll")
    spawn(pack["chair"], "TRN_MonitoringChair", (3060.0, 760.0, 0.0), yaw=0.0, folder=F, coll="BlockAll")
    spawn(small, "TRN_Display_Session", (3188.0, 650.0, 190.0), yaw=180.0, folder=F, mats={ss: mi["T_TRN_SessionDisplay"]})
    spawn(small, "TRN_Display_Monitor", (3188.0, 870.0, 190.0), yaw=180.0, folder=F, mats={ss: mi["T_TRN_MonitorDisplay"]})
    for i, (x, y, z, yaw) in enumerate(((2262.0, 1110.0, 0.0, 0.0), (2262.0, 1110.0, 62.0, 8.0), (2340.0, 1120.0, 0.0, -4.0))):
        spawn(crate, f"TRN_SupplyCrate_{i + 1}", (x, y, z), yaw=yaw, folder=F, coll="BlockAll")
    spawn(utility, "TRN_WallUtilityPanel", (2222.0, 820.0, 150.0), yaw=0.0, folder=F)
    for i, (x, y) in enumerate(((2450.0, 430.0), (2950.0, 430.0), (2450.0, 960.0), (2950.0, 960.0))):
        fixture(light_mesh, f"TRN_CeilingLight_{i + 1}", (x, y, 374.0), 90.0, 2400.0, F)
    spawn(sign, "TRN_Sign_Corridor", (3040.0, 189.0, 200.0), yaw=-90.0, folder=F, mats={sgs: mi["T_Sign_Training"]})

    # ---------------- corridor fixtures (finished corridor kit is placed with the room kits)
    for i, x in enumerate((300.0, 900.0, 1700.0, 2100.0, 3100.0, 3700.0)):
        fixture(light_mesh, f"COR_CeilingLight_{i + 1}", (x, 0.0, 314.0), 0.0, 1800.0, "MainCorridor")

    # ---------------- doors on the corridor doorways (rooms' south walls at y = 200)
    place_door(door_parts, "DOOR_MissionControl", 1400.0, 200.0, "Doors")
    place_door(door_parts, "DOOR_Training", 2700.0, 200.0, "Doors")
    les.save_current_level()


def main():
    layout = json.load(open(LAYOUT, encoding="utf-8"))
    for d in (TEX_DIR, MAT_DIR, MESH_DIR, HOLO_DIR, DOOR_DIR, PACK_DIR):
        eal.make_directory(d)
    kit_mi = asl.ensure_instances(asl.ensure_master_material())
    tex = import_textures()
    mi = build_materials(tex)
    meshes = build_meshes(kit_mi, mi)
    kits = build_kits(kit_mi, layout)
    split = split_door()
    frame = import_combined(split["Frame"], f"{DOOR_DIR}/Frame")
    leaf_l = import_combined(split["LeafL"], f"{DOOR_DIR}/LeafL")
    leaf_r = import_combined(split["LeafR"], f"{DOOR_DIR}/LeafR")
    collision(frame, "complex")
    collision(leaf_l, "box")
    collision(leaf_r, "box")
    pack = {"console": import_combined(os.path.join(PACK_GLB, "OD_MCC_MainConsole.glb"), f"{PACK_DIR}/OD_MCC_MainConsole"),
            "chair": import_combined(os.path.join(PACK_GLB, "OD_MCC_MissionControlChair.glb"), f"{PACK_DIR}/OD_MCC_MissionControlChair")}
    collision(pack["console"], "box")
    collision(pack["chair"], "box")
    place_all(kits, meshes, mi, (frame, leaf_l, leaf_r, meshes["StatusStrip"]), pack)
    out = os.path.join(PROJECT, "Saved", "Odyssey")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "room_finish_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    log(f"done: {len(report['placed'])} placements, {len(report['doors'])} doors")


if __name__ == "__main__":
    main()
