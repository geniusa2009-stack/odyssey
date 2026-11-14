"""Unreal Editor Python: generate the ODYSSEY palette materials, the Engineering proxy meshes and the
Engineering finish-kit meshes from Tools/Editor/odyssey_kit_geometry.py.

Called by build_earth_command_greybox.py; can also run on its own:
    py "<project>/Tools/Editor/odyssey_slice_assets.py"

EXACT TARGETS (only these assets are created or replaced):
    /Game/Earth/EarthCommand/Materials/M_ODY_HardSurface, MI_ODY_<slot>
    /Game/Earth/EarthCommand/Engineering/Proxies/SM_PROXY_*
    /Game/Earth/EarthCommand/Engineering/Kit/SM_KIT_ENG_*

Proxies are hard-surface blockouts that follow the approved reference images and the Replit
mounting contract. They are NOT production meshes; the reference PNGs are not used as geometry or
textures. Each proxy carries asset metadata (OdysseyProxy=true, Reference=<png>, AwaitingProductionMesh=true).
"""
from __future__ import annotations

import json
import os
import sys

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(
    unreal.Paths.project_dir(), "Tools", "Editor")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import odyssey_kit_geometry as geo  # noqa: E402

MAT_DIR = "/Game/Earth/EarthCommand/Materials"
PROXY_DIR = "/Game/Earth/EarthCommand/Engineering/Proxies"
KIT_DIR = "/Game/Earth/EarthCommand/Engineering/Kit"
MASTER = f"{MAT_DIR}/M_ODY_HardSurface"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


def _log(msg):
    unreal.log(f"[Odyssey] {msg}")


# --------------------------------------------------------------------------------------------- materials
def _param(mat, cls, name, x, y, default):
    e = mel.create_material_expression(mat, cls, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", default)
    return e


def ensure_master_material():
    if eal.does_asset_exist(MASTER):
        return unreal.load_asset(MASTER)  # deterministic graph; never recompiled in place
    mat = asset_tools.create_asset("M_ODY_HardSurface", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    base = _param(mat, unreal.MaterialExpressionVectorParameter, "BaseColor", -700, -300, unreal.LinearColor(0.7, 0.7, 0.7, 1))
    metal = _param(mat, unreal.MaterialExpressionScalarParameter, "Metallic", -700, -100, 0.0)
    rough = _param(mat, unreal.MaterialExpressionScalarParameter, "Roughness", -700, 0, 0.5)
    ecol = _param(mat, unreal.MaterialExpressionVectorParameter, "EmissiveColor", -900, 200, unreal.LinearColor(0, 0, 0, 1))
    estr = _param(mat, unreal.MaterialExpressionScalarParameter, "EmissiveStrength", -900, 400, 0.0)
    escl = _param(mat, unreal.MaterialExpressionScalarParameter, "EmissiveScale", -900, 500, 1.0)
    m1 = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -500, 300)
    m2 = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -300, 300)
    mel.connect_material_expressions(ecol, "", m1, "A")
    mel.connect_material_expressions(estr, "", m1, "B")
    mel.connect_material_expressions(m1, "", m2, "A")
    mel.connect_material_expressions(escl, "", m2, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(m2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    return mat


def ensure_instances(master):
    out = {}
    for key in geo.MATERIAL_ORDER:
        spec = geo.PALETTE[key]
        name = f"MI_ODY_{key.capitalize()}"
        path = f"{MAT_DIR}/{name}"
        mi = unreal.load_asset(path) if eal.does_asset_exist(path) else asset_tools.create_asset(
            name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, master)
        r, g, b = geo.srgb_to_linear(spec["hex"])
        mel.set_material_instance_vector_parameter_value(mi, "BaseColor", unreal.LinearColor(r, g, b, 1))
        mel.set_material_instance_scalar_parameter_value(mi, "Metallic", float(spec["metallic"]))
        mel.set_material_instance_scalar_parameter_value(mi, "Roughness", float(spec["roughness"]))
        if "emissive" in spec:
            er, eg, eb = geo.srgb_to_linear(spec["emissive"])
            mel.set_material_instance_vector_parameter_value(mi, "EmissiveColor", unreal.LinearColor(er, eg, eb, 1))
            mel.set_material_instance_scalar_parameter_value(mi, "EmissiveStrength", float(spec["strength"]))
        eal.save_loaded_asset(mi)
        out[key] = mi
    return out


# --------------------------------------------------------------------------------------------- meshes
def _ret0(r):
    return r[0] if isinstance(r, tuple) else r


def build_mesh(path, parts, materials, collision, metadata=None):
    """parts → StaticMesh asset at `path`. One polygon group per palette slot (stable order), flat
    faces (no shared vertices across faces), smooth cylinder sides, 1 UV unit = 1 m box projection,
    lightmap UVs generated into channel 1, collision per `collision` ("box" | "complex" | "none")."""
    pkg, name = path.rsplit("/", 1)
    if eal.does_asset_exist(path):
        sm = unreal.load_asset(path)  # rebuilt in place: references from the map stay valid
    else:
        sm = asset_tools.duplicate_asset(name, pkg, unreal.load_asset("/Engine/BasicShapes/Cube.Cube"))
    used = [k for k in geo.MATERIAL_ORDER if any(p.mat == k for p in parts)]
    # AddMaterial sets slot + imported slot name (= the MI's name); the build maps polygon groups
    # to sections by that imported name (Python cannot set ImportedMaterialSlotName directly).
    sm.set_editor_property("static_materials", [])
    slot = {k: str(sm.add_material(materials[k])) for k in used}

    desc = unreal.StaticMesh.create_static_mesh_description(sm)
    groups = {}
    for k in used:
        g = desc.create_polygon_group()
        desc.set_polygon_group_material_slot_name(g, slot[k])
        groups[k] = g

    tris = 0
    for part in parts:
        side_cache = {}
        for mat, pts, normal, tag in geo.faces(part):
            # planar UV projection along the face's dominant axis (1 UV = 100 cm)
            ax = max(range(3), key=lambda i: abs(normal[i]))
            ua, va = [(1, 2), (0, 2), (0, 1)][ax]
            vis = []
            for p in pts:
                key = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
                if tag == "side" and key in side_cache:   # smooth cylinder sides share vertices
                    vid = side_cache[key]
                else:
                    vid = desc.create_vertex()
                    desc.set_vertex_position(vid, unreal.Vector(*p))
                    if tag == "side":
                        side_cache[key] = vid
                vi = desc.create_vertex_instance(vid)
                desc.set_vertex_instance_uv(vi, unreal.Vector2D(p[ua] / 100.0, -p[va] / 100.0), 0)
                vis.append(vi)
            vis.reverse()  # Unreal front-face winding (matches UStaticMeshDescription::CreateCube)
            for i in range(1, len(vis) - 1):  # convex faces → triangle fan
                _ret0(desc.create_triangle(groups[mat], [vis[0], vis[i], vis[i + 1]]))
                tris += 1

    sm.build_from_static_mesh_descriptions([desc], False, False)
    bs = sme.get_lod_build_settings(sm, 0)
    bs.set_editor_property("recompute_normals", True)
    bs.set_editor_property("recompute_tangents", True)
    bs.set_editor_property("generate_lightmap_u_vs", True)
    bs.set_editor_property("src_lightmap_index", 0)
    bs.set_editor_property("dst_lightmap_index", 1)
    sm.set_editor_property("light_map_coordinate_index", 1)
    sme.set_lod_build_settings(sm, 0, bs)  # rebuilds with these settings

    sme.remove_collisions(sm)
    body = sm.get_editor_property("body_setup")
    if collision == "box":
        sme.add_simple_collisions(sm, unreal.ScriptCollisionShapeType.BOX)
        body = sm.get_editor_property("body_setup")
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
    elif collision == "complex":
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    else:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    for k, v in (metadata or {}).items():
        eal.set_metadata_tag(sm, k, str(v))
    eal.save_loaded_asset(sm)
    return sm, tris


def _nanite(sm):
    try:
        return bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
    except Exception:
        return None


def validate_mesh(sm):
    """Read back what Unreal built: bounds, triangles, UV channels, sections/materials, collision."""
    bb = sm.get_bounding_box()
    lo, hi = bb.min, bb.max
    return {
        "bounds_min": [round(lo.x, 1), round(lo.y, 1), round(lo.z, 1)],
        "bounds_max": [round(hi.x, 1), round(hi.y, 1), round(hi.z, 1)],
        "triangles": sm.get_num_triangles(0),
        "vertices": sme.get_number_verts(sm, 0),
        "uv_channels": sme.get_num_uv_channels(sm, 0),
        "material_slots": [str(m.material_slot_name) for m in sm.get_editor_property("static_materials")],
        "sections": sm.get_num_sections(0),
        "simple_collision_primitives": sme.get_simple_collision_count(sm),
        "collision_trace": str(sm.get_editor_property("body_setup").get_editor_property("collision_trace_flag")),
        "nanite": _nanite(sm),
    }


# --------------------------------------------------------------------------------------------- entry points
def build_proxies(materials):
    report = {}
    meshes = {}
    for key, fn in geo.PROXY_BUILDERS.items():
        p = fn()
        problems, _ = geo.check_proxy(p)
        if problems:
            raise RuntimeError(f"{p.asset}: geometry contract failed: {problems}")
        sm, tris = build_mesh(f"{PROXY_DIR}/{p.asset}", p.parts, materials, p.collision, {
            "OdysseyProxy": "true", "AwaitingProductionMesh": "true", "Reference": p.reference,
            "Envelope_WxHxD_cm": "x".join(str(v) for v in p.envelope), "Pivot": p.pivot,
            "MovablePartsInProduction": "; ".join(p.movable_parts)})
        info = validate_mesh(sm)
        elo, ehi = geo.expected_bounds(p)
        info.update({"envelope_W_H_D_cm": list(p.envelope), "pivot": p.pivot, "expected_min": list(elo),
                     "expected_max": list(ehi), "reference": p.reference, "movable_parts": p.movable_parts,
                     "collision": p.collision})
        report[p.asset] = info
        meshes[key] = sm
        _log(f"proxy {p.asset}: {info}")
    return meshes, report


def build_engineering_kit(materials, layout, placements):
    eng = next(a for a in layout["areas"] if a["id"] == "engineering")
    cor = next(a for a in layout["areas"] if a["id"] == eng["kit"]["corridor_transition"]["area"])
    kit = geo.engineering_kit(eng, cor, exclusions=placements.get("exclusions"))
    services = geo.engineering_services(kit, placements)
    door_x, door_w = eng["kit"]["corridor_transition"]["door"]
    transition = geo.corridor_transition(door_x, eng["bounds"][3], cor["height"], door_w=door_w)
    specs = [
        ("SM_KIT_ENG_Floor", kit["floor"], "complex", (kit["cx"], kit["cy"], 0)),
        ("SM_KIT_ENG_Walls", kit["walls"], "complex", (kit["cx"], kit["cy"], 0)),
        ("SM_KIT_ENG_DoorFrame", kit["door"], "complex", (kit["cx"], kit["cy"], 0)),
        ("SM_KIT_ENG_Ceiling", kit["ceiling"], "none", (kit["cx"], kit["cy"], 0)),
        ("SM_KIT_ENG_Services", services, "none", (kit["cx"], kit["cy"], 0)),
        ("SM_KIT_ENG_CorridorTransition", transition, "complex", (door_x, eng["bounds"][3], 0)),
    ]
    out, report = [], {}
    for name, parts, coll, pivot in specs:
        sm, tris = build_mesh(f"{KIT_DIR}/{name}", parts, materials, coll, {"OdysseyKit": "engineering", "Pivot": "room floor centre" if name != "SM_KIT_ENG_CorridorTransition" else "door centre on wall line"})
        info = validate_mesh(sm)
        report[name] = info
        out.append((name, sm, pivot))
        _log(f"kit {name}: {info}")
    return out, report


def build_all(layout, placements):
    master = ensure_master_material()
    materials = ensure_instances(master)
    proxies, preport = build_proxies(materials)
    kit, kreport = build_engineering_kit(materials, layout, placements)
    report_path = os.path.join(unreal.Paths.project_saved_dir(), "Odyssey", "engineering_assets_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"proxies": preport, "kit": kreport}, f, indent=1)
    _log(f"asset report written to {report_path}")
    return materials, proxies, kit
