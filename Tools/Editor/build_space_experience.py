"""Unreal Editor Python: builds the ODYSSEY space experience content and map end to end.

    UnrealEditor Odyssey.uproject -ExecCmds="py <project>/Tools/Editor/build_space_experience.py"
    (or from the editor's Python console: py "<project>/Tools/Editor/build_space_experience.py")

  /Game/Space/Textures   T_Earth_* / T_Moon_* / T_Mars_* / T_Space_Starfield  (from ArtSource/OdysseySpace/Textures)
  /Game/Space/Materials  M_ODY_PlanetSurface, M_ODY_PlanetAtmosphere, M_ODY_Starfield, M_ODY_SunDisc,
                         M_ODY_EnginePlume, M_ODY_NavLight + instances (MI_Earth_*, MI_Moon_*, MI_Mars_*, MI_OTV_*)
  /Game/Space/Meshes     SM_ODY_PlanetSphere, SM_ODY_AtmosphereSphere, SM_ODY_SkySphere, SM_ODY_SunDisc,
                         SM_OTV_Meridian_Hull, SM_OTV_Meridian_Plume, SM_OTV_Meridian_RCS
  /Game/Space/Maps       L_Odyssey_SolarTransit (game mode AOdysseySpaceGameMode)

Geometry comes from odyssey_space_geometry.py, textures from generate_space_textures.py. Re-running
rebuilds assets in place (map references stay valid) and regenerates the map. The report is written to
Saved/Odyssey/space_assets_report.json.
"""
import json
import math
import os
import sys

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(unreal.Paths.project_dir(), "Tools", "Editor")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import odyssey_space_geometry as geo  # noqa: E402

PROJECT = os.path.abspath(unreal.Paths.project_dir())
TEX_SRC = os.path.join(PROJECT, "ArtSource", "OdysseySpace", "Textures")
ROOT = "/Game/Space"
TEX_DIR, MAT_DIR, MESH_DIR, MAP_DIR = ROOT + "/Textures", ROOT + "/Materials", ROOT + "/Meshes", ROOT + "/Maps"
MAP = MAP_DIR + "/L_Odyssey_SolarTransit"
HARD_SURFACE = "/Game/Earth/EarthCommand/Materials/M_ODY_HardSurface"

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
report = {"textures": {}, "materials": [], "meshes": {}, "actors": []}


def log(msg):
    unreal.log(f"[OdysseySpace] {msg}")


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def lc(rgb, a=1.0):
    return unreal.LinearColor(rgb[0], rgb[1], rgb[2], a)


# ------------------------------------------------------------------------------------------ textures
TEXTURES = {
    "T_Earth_Albedo": ("color", None), "T_Earth_Normal": ("normal", None), "T_Earth_Masks": ("masks", None),
    "T_Earth_Clouds": ("gray", None), "T_Moon_Albedo": ("color", None), "T_Moon_Normal": ("normal", None),
    "T_Mars_Albedo": ("color", None), "T_Mars_Normal": ("normal", None), "T_Space_Starfield": ("color", "bc7"),
    "T_Space_BlackLinear": ("masks", None),
}


def import_textures():
    tasks = []
    for name in TEXTURES:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", os.path.join(TEX_SRC, name + ".png"))
        t.set_editor_property("destination_path", TEX_DIR)
        t.set_editor_property("destination_name", name)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        tasks.append(t)
    asset_tools.import_asset_tasks(tasks)
    out = {}
    for name, (kind, comp) in TEXTURES.items():
        tex = unreal.load_asset(f"{TEX_DIR}/{name}")
        if kind == "normal":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("srgb", False)
        elif kind == "masks":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tex.set_editor_property("srgb", False)
        elif kind == "gray":  # linear single-channel data sampled as Linear Color
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tex.set_editor_property("srgb", False)
        else:
            tex.set_editor_property("srgb", True)
            if comp == "bc7":
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        eal.save_loaded_asset(tex)
        out[name] = tex
        report["textures"][name] = {"size": [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()], "kind": kind}
    log(f"{len(out)} textures imported")
    return out


# ------------------------------------------------------------------------------------------ materials
def material(name, blend=None, shading=None, two_sided=False, is_sky=False):
    path = f"{MAT_DIR}/{name}"
    if eal.does_asset_exist(path):
        mat = unreal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = asset_tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if blend is not None:
        mat.set_editor_property("blend_mode", blend)
    if shading is not None:
        mat.set_editor_property("shading_model", shading)
    mat.set_editor_property("two_sided", two_sided)
    try:
        mat.set_editor_property("is_sky", is_sky)
    except Exception:
        pass
    return mat


def expr(mat, cls, x, y):
    return mel.create_material_expression(mat, cls, x, y)


def scalar(mat, name, value, x, y):
    e = expr(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", value)
    return e


def vector(mat, name, value, x, y):
    e = expr(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", value)
    return e


def texparam(mat, name, default, sampler, x, y):
    e = expr(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("texture", unreal.load_asset(default))
    e.set_editor_property("sampler_type", sampler)
    return e


def custom(mat, code, inputs, out_type, x, y, desc="Custom"):
    e = expr(mat, unreal.MaterialExpressionCustom, x, y)
    e.set_editor_property("code", code)
    e.set_editor_property("description", desc)
    e.set_editor_property("output_type", out_type)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    e.set_editor_property("inputs", ins)
    return e


def link(src, dst, inp, out=""):
    ok = mel.connect_material_expressions(src, out, dst, inp)
    if not ok:
        raise RuntimeError(f"material link failed: {src.get_name()}.{out} -> {dst.get_name()}.{inp}")


def finish(mat):
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    report["materials"].append(mat.get_name())
    return mat


F1, F2, F3 = (unreal.CustomMaterialOutputType.CMOT_FLOAT1, unreal.CustomMaterialOutputType.CMOT_FLOAT2,
              unreal.CustomMaterialOutputType.CMOT_FLOAT3)
WHITE_TEX, BLACK_TEX, NORMAL_TEX = "/Engine/EngineResources/WhiteSquareTexture", TEX_DIR + "/T_Space_BlackLinear", "/Engine/EngineMaterials/DefaultNormal"


def build_planet_surface():
    m = material("M_ODY_PlanetSurface")
    color = unreal.MaterialSamplerType.SAMPLERTYPE_COLOR
    lin = unreal.MaterialSamplerType.SAMPLERTYPE_MASKS  # TC_Masks textures (linear data)
    albedo = texparam(m, "Albedo", WHITE_TEX, color, -1400, -400)
    normal = texparam(m, "Normal", NORMAL_TEX, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, -1400, 600)
    masks = texparam(m, "Masks", BLACK_TEX, lin, -1400, 0)
    clouds = texparam(m, "Clouds", BLACK_TEX, lin, -1400, 300)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -2000, 300)
    time = expr(m, unreal.MaterialExpressionTime, -2000, 400)
    cspeed = scalar(m, "CloudSpeed", 0.0012, -2000, 500)
    cuv = custom(m, "return UV + float2(T * Speed, 0.0);", ["UV", "T", "Speed"], F2, -1700, 300, "CloudUV")
    link(uv, cuv, "UV"); link(time, cuv, "T"); link(cspeed, cuv, "Speed"); link(cuv, clouds, "UVs")
    nws = expr(m, unreal.MaterialExpressionVertexNormalWS, -1100, -700)
    cam = expr(m, unreal.MaterialExpressionCameraVectorWS, -1100, -600)
    sun = vector(m, "SunDirection", unreal.LinearColor(0.1, -0.45, 0.9, 0), -1100, -500)
    atmo = vector(m, "AtmosphereColor", unreal.LinearColor(0.3, 0.55, 1.0, 1), -1100, -400)
    cstr = scalar(m, "CloudStrength", 0.0, -1100, -300)
    haze = scalar(m, "Haze", 0.5, -1100, -250)
    city = vector(m, "CityColor", unreal.LinearColor(1.0, 0.68, 0.36, 1), -1100, -150)
    cityi = scalar(m, "CityIntensity", 0.0, -1100, -100)
    namb = scalar(m, "NightAmbient", 0.01, -1100, -50)
    lrough = scalar(m, "LandRoughness", 0.85, -1100, 0)
    orough = scalar(m, "OceanRoughness", 0.35, -1100, 50)
    nstr = scalar(m, "NormalStrength", 1.0, -1100, 100)

    base = custom(m, """
float c = saturate(Cloud * CloudStrength);
float3 b = lerp(Albedo, float3(0.80, 0.82, 0.85), c);
float ndv = saturate(dot(normalize(N), normalize(V)));
float day = saturate(dot(normalize(N), normalize(L)) * 1.5 + 0.35);
float rim = pow(1.0 - ndv, 4.0);
return lerp(b, Atmo, saturate(rim * Haze * day));""", ["Albedo", "Cloud", "N", "V", "L", "Atmo", "CloudStrength", "Haze"], F3, -600, -500, "PlanetBase")
    emis = custom(m, """
float c = saturate(Cloud * CloudStrength);
float night = saturate(-dot(normalize(N), normalize(L)) * 4.0 + 0.12);
float lights = Masks.g * (1.0 - c * 0.85) * night;
return City * lights * CityIntensity + Albedo * NightAmbient * night;""", ["Albedo", "Masks", "Cloud", "N", "L", "City", "CityIntensity", "NightAmbient", "CloudStrength"], F3, -600, -200, "PlanetNight")
    rough = custom(m, """
float c = saturate(Cloud * CloudStrength);
return lerp(lerp(Land, Ocean, Masks.r), 0.92, c);""", ["Masks", "Cloud", "CloudStrength", "Land", "Ocean"], F1, -600, 100, "PlanetRoughness")
    nrm = custom(m, """
float c = saturate(Cloud * CloudStrength);
float3 n = float3(Nrm.xy * Strength, Nrm.z);
return normalize(lerp(n, float3(0, 0, 1), c));""", ["Nrm", "Cloud", "CloudStrength", "Strength"], F3, -600, 400, "PlanetNormal")
    for c, pins in ((base, [(albedo, "Albedo", "RGB"), (clouds, "Cloud", "R"), (nws, "N", ""), (cam, "V", ""), (sun, "L", ""), (atmo, "Atmo", ""), (cstr, "CloudStrength", ""), (haze, "Haze", "")]),
                    (emis, [(albedo, "Albedo", "RGB"), (masks, "Masks", "RGB"), (clouds, "Cloud", "R"), (nws, "N", ""), (sun, "L", ""), (city, "City", ""), (cityi, "CityIntensity", ""), (namb, "NightAmbient", ""), (cstr, "CloudStrength", "")]),
                    (rough, [(masks, "Masks", "RGB"), (clouds, "Cloud", "R"), (cstr, "CloudStrength", ""), (lrough, "Land", ""), (orough, "Ocean", "")]),
                    (nrm, [(normal, "Nrm", "RGB"), (clouds, "Cloud", "R"), (cstr, "CloudStrength", ""), (nstr, "Strength", "")])):
        for src, pin, out in pins:
            link(src, c, pin, out)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(emis, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    return finish(m)


def build_atmosphere():
    m = material("M_ODY_PlanetAtmosphere", unreal.BlendMode.BLEND_ADDITIVE, unreal.MaterialShadingModel.MSM_UNLIT)
    # Analytic limb: for each view ray, the closest approach d to the planet centre decides between
    # the glow band (R < d < Ra, thin and bright) and a faint haze over the planet's edge (d < R).
    nws = expr(m, unreal.MaterialExpressionVertexNormalWS, -900, -300)
    cam = expr(m, unreal.MaterialExpressionCameraVectorWS, -900, -200)
    oc = expr(m, unreal.MaterialExpressionObjectPositionWS, -900, -400)
    try:
        oc.set_editor_property("origin_type", unreal.PositionOrigin.CAMERA_RELATIVE)
    except Exception as e:
        raise RuntimeError(f"ObjectPositionWS has no camera-relative origin in this engine: {e}")
    sun = vector(m, "SunDirection", unreal.LinearColor(0.1, -0.45, 0.9, 0), -900, -100)
    col = vector(m, "AtmosphereColor", unreal.LinearColor(0.28, 0.55, 1.0, 1), -900, 0)
    sunset = vector(m, "SunsetColor", unreal.LinearColor(1.0, 0.45, 0.2, 1), -900, 100)
    inten = scalar(m, "Intensity", 3.0, -900, 200)
    power = scalar(m, "Power", 1.6, -900, 300)
    pr = scalar(m, "PlanetRadius", 1.0e6, -900, 400)
    ar = scalar(m, "AtmosphereRadius", 1.022e6, -900, 500)
    c = custom(m, """
float3 n = normalize(N); float3 l = normalize(L);
float3 rd = -normalize(V);
float d = length(cross(OC, rd));
float shell = max(Ra - R, 1.0);
float glow = pow(saturate((Ra - d) / shell), Power) * step(R, d);
float haze = exp(-max(R - d, 0.0) / (shell * 1.6)) * 0.22 * step(d, R);
float day = saturate(dot(n, l) * 1.1 + 0.18);
float term = saturate(1.0 - abs(dot(n, l)) * 3.0);
return (Color * day + Sunset * term * 0.5) * (glow + haze) * Intensity;""", ["N", "V", "L", "OC", "Color", "Sunset", "Intensity", "Power", "R", "Ra"], F3, -400, 0, "AtmosphereLimb")
    for src, pin in ((nws, "N"), (cam, "V"), (sun, "L"), (oc, "OC"), (col, "Color"), (sunset, "Sunset"), (inten, "Intensity"), (power, "Power"), (pr, "R"), (ar, "Ra")):
        link(src, c, pin)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return finish(m)


def build_starfield(tex):
    m = material("M_ODY_Starfield", None, unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True)
    t = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -600, 0)
    t.set_editor_property("parameter_name", "Stars")
    t.set_editor_property("texture", tex)
    i = scalar(m, "Intensity", 1.0, -600, 250)
    mul = expr(m, unreal.MaterialExpressionMultiply, -300, 0)
    link(t, mul, "A", "RGB"); link(i, mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return finish(m)


def build_emissive(name, color, intensity, param_extra=None):
    m = material(name, None, unreal.MaterialShadingModel.MSM_UNLIT)
    c = vector(m, "Color", lc(color), -600, 0)
    i = scalar(m, "Intensity", intensity, -600, 200)
    if param_extra:  # nav light: base glow + blink
        blink = scalar(m, "NavBlink", 0.0, -600, 300)
        f = custom(m, "return Color * (0.06 + Blink * Intensity);", ["Color", "Blink", "Intensity"], F3, -300, 0, "NavLight")
        link(c, f, "Color"); link(blink, f, "Blink"); link(i, f, "Intensity")
        out = f
    else:
        out = expr(m, unreal.MaterialExpressionMultiply, -300, 0)
        link(c, out, "A"); link(i, out, "B")
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return finish(m)


def build_plume():
    m = material("M_ODY_EnginePlume", unreal.BlendMode.BLEND_ADDITIVE, unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True)
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -900, -300)
    nws = expr(m, unreal.MaterialExpressionVertexNormalWS, -900, -200)
    cam = expr(m, unreal.MaterialExpressionCameraVectorWS, -900, -100)
    thrust = scalar(m, "Thrust", 1.0, -900, 0)
    core = vector(m, "CoreColor", unreal.LinearColor(0.85, 0.95, 1.0, 1), -900, 100)
    edge = vector(m, "EdgeColor", unreal.LinearColor(0.12, 0.45, 1.0, 1), -900, 200)
    inten = scalar(m, "Intensity", 18.0, -900, 300)
    c = custom(m, """
float u = saturate(UV.x);
float ndv = abs(dot(normalize(N), normalize(V)));
float soft = pow(ndv, 1.6);
float fall = pow(1.0 - u, 2.2) * saturate(u * 12.0 + 0.25);
float3 col = lerp(Core, Edge, saturate(u * 1.8));
return col * fall * soft * Thrust * Intensity;""", ["UV", "N", "V", "Thrust", "Core", "Edge", "Intensity"], F3, -400, 0, "Plume")
    for src, pin in ((uv, "UV"), (nws, "N"), (cam, "V"), (thrust, "Thrust"), (core, "Core"), (edge, "Edge"), (inten, "Intensity")):
        link(src, c, pin)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return finish(m)


def instance(name, parent, scalars=None, vectors=None, textures=None):
    path = f"{MAT_DIR}/{name}"
    mi = unreal.load_asset(path) if eal.does_asset_exist(path) else asset_tools.create_asset(
        name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, float(v))
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, v)
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(mi, k, v)
    eal.save_loaded_asset(mi)
    report["materials"].append(name)
    return mi


def build_materials(tex):
    surf = build_planet_surface()
    atmo = build_atmosphere()
    stars = build_starfield(tex["T_Space_Starfield"])
    sun = build_emissive("M_ODY_SunDisc", (1.0, 0.95, 0.88), 120.0)
    nav = build_emissive("M_ODY_NavLight", (1.0, 1.0, 1.0), 60.0, param_extra=True)
    plume = build_plume()
    hs = unreal.load_asset(HARD_SURFACE)
    mi = {
        "Earth": instance("MI_Earth_Surface", surf, {"CloudStrength": 1.0, "Haze": 0.45, "CityIntensity": 4.0, "NightAmbient": 0.006,
                                                     "LandRoughness": 0.82, "OceanRoughness": 0.24, "NormalStrength": 1.0},
                          {"AtmosphereColor": unreal.LinearColor(0.3, 0.55, 1.0, 1)},
                          {"Albedo": tex["T_Earth_Albedo"], "Normal": tex["T_Earth_Normal"], "Masks": tex["T_Earth_Masks"], "Clouds": tex["T_Earth_Clouds"]}),
        "Moon": instance("MI_Moon_Surface", surf, {"CloudStrength": 0.0, "Haze": 0.0, "CityIntensity": 0.0, "NightAmbient": 0.02,
                                                   "LandRoughness": 0.95, "OceanRoughness": 0.95, "NormalStrength": 1.6},
                         {}, {"Albedo": tex["T_Moon_Albedo"], "Normal": tex["T_Moon_Normal"], "Masks": tex["T_Space_BlackLinear"], "Clouds": tex["T_Space_BlackLinear"]}),
        "Mars": instance("MI_Mars_Surface", surf, {"CloudStrength": 0.0, "Haze": 0.3, "CityIntensity": 0.0, "NightAmbient": 0.008,
                                                   "LandRoughness": 0.9, "OceanRoughness": 0.9, "NormalStrength": 1.3},
                         {"AtmosphereColor": unreal.LinearColor(0.85, 0.55, 0.38, 1)},
                         {"Albedo": tex["T_Mars_Albedo"], "Normal": tex["T_Mars_Normal"], "Masks": tex["T_Space_BlackLinear"], "Clouds": tex["T_Space_BlackLinear"]}),
        "EarthAtmo": instance("MI_Earth_Atmosphere", atmo, {"Intensity": 2.6, "Power": 1.5, "PlanetRadius": 1.0e6, "AtmosphereRadius": 1.022e6},
                              {"AtmosphereColor": unreal.LinearColor(0.26, 0.55, 1.0, 1), "SunsetColor": unreal.LinearColor(1.0, 0.42, 0.18, 1)}),
        "MarsAtmo": instance("MI_Mars_Atmosphere", atmo, {"Intensity": 1.2, "Power": 2.2, "PlanetRadius": 5.32e5, "AtmosphereRadius": 5.32e5 * 1.03},
                             {"AtmosphereColor": unreal.LinearColor(0.9, 0.55, 0.36, 1), "SunsetColor": unreal.LinearColor(0.12, 0.2, 0.32, 1)}),
        "Stars": stars, "Sun": sun, "Plume": plume,
        "RcsPlume": instance("MI_OTV_RCSPlume", plume, {"Intensity": 10.0}, {"CoreColor": unreal.LinearColor(1, 1, 1, 1), "EdgeColor": unreal.LinearColor(0.7, 0.8, 1.0, 1)}),
        "NavRed": instance("MI_OTV_NavRed", nav, {"Intensity": 60.0}, {"Color": lc(srgb("#B84743"))}),
        "NavIon": instance("MI_OTV_NavIon", nav, {"Intensity": 60.0}, {"Color": lc(srgb("#61BED2"))}),
    }
    hull = {
        "White": ("#D8D9D5", 0.0, 0.42, None), "Graphite": ("#1C2025", 0.0, 0.6, None), "Gunmetal": ("#454B52", 0.85, 0.36, None),
        "Alu": ("#92989E", 1.0, 0.28, None), "Window": ("#09131C", 0.0, 0.08, ("#61BED2", 0.35)), "Ion": ("#61BED2", 0.0, 0.4, ("#61BED2", 4.0)),
    }
    for key, (hexs, metal, rough, em) in hull.items():
        vec = {"BaseColor": lc(srgb(hexs))}
        sc = {"Metallic": metal, "Roughness": rough}
        if em:
            vec["EmissiveColor"] = lc(srgb(em[0]))
            sc["EmissiveStrength"] = em[1]
        mi[key] = instance(f"MI_OTV_{key}", hs, sc, vec)
    log(f"{len(report['materials'])} materials")
    return mi


# ------------------------------------------------------------------------------------------ meshes
def _ret0(r):
    return r[0] if isinstance(r, tuple) else r


def build_tri_mesh(name, mesh, materials):
    path = f"{MESH_DIR}/{name}"
    if eal.does_asset_exist(path):
        sm = unreal.load_asset(path)
    else:
        sm = asset_tools.duplicate_asset(name, MESH_DIR, unreal.load_asset("/Engine/BasicShapes/Cube.Cube"))
    slots = sorted(mesh.sections)
    sm.set_editor_property("static_materials", [])
    slot_name = {k: str(sm.add_material(materials[k])) for k in slots}
    desc = unreal.StaticMesh.create_static_mesh_description(sm)
    tris = 0
    for k in slots:
        sec = mesh.sections[k]
        g = desc.create_polygon_group()
        desc.set_polygon_group_material_slot_name(g, slot_name[k])
        vis = []
        for p, n, uv in zip(sec.positions, sec.normals, sec.uvs):
            v = desc.create_vertex()
            desc.set_vertex_position(v, unreal.Vector(*p))
            vi = desc.create_vertex_instance(v)
            desc.set_vertex_instance_uv(vi, unreal.Vector2D(uv[0], uv[1]), 0)
            vis.append(vi)
        for a, b, c in sec.triangles:
            _ret0(desc.create_triangle(g, [vis[c], vis[b], vis[a]]))  # reversed: Unreal front-face winding
            tris += 1
    sm.build_from_static_mesh_descriptions([desc], False, False)
    bs = sme.get_lod_build_settings(sm, 0)
    bs.set_editor_property("recompute_normals", True)  # Python cannot set instance normals; vertices are shared on smooth surfaces and split at creases
    bs.set_editor_property("recompute_tangents", True)
    bs.set_editor_property("use_mikk_t_space", True)
    bs.set_editor_property("generate_lightmap_u_vs", False)
    bs.set_editor_property("remove_degenerates", True)
    sme.set_lod_build_settings(sm, 0, bs)
    sme.remove_collisions(sm)
    body = sm.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    eal.set_metadata_tag(sm, "OdysseyGenerated", "odyssey_space_geometry.py")
    eal.save_loaded_asset(sm)
    bb = sm.get_bounding_box()
    report["meshes"][name] = {"triangles": sm.get_num_triangles(0), "built_triangles": tris, "sections": sm.get_num_sections(0),
                              "bounds_min": [round(bb.min.x, 1), round(bb.min.y, 1), round(bb.min.z, 1)],
                              "bounds_max": [round(bb.max.x, 1), round(bb.max.y, 1), round(bb.max.z, 1)]}
    log(f"mesh {name}: {tris} tris, {len(slots)} sections")
    return sm


def build_meshes(mi):
    surf_default = unreal.load_asset(f"{MAT_DIR}/M_ODY_PlanetSurface")
    return {
        "Planet": build_tri_mesh("SM_ODY_PlanetSphere", geo.sphere(100.0, 384, 192), {"Surface": surf_default}),
        "Atmo": build_tri_mesh("SM_ODY_AtmosphereSphere", geo.sphere(100.0, 192, 96), {"Surface": mi["EarthAtmo"]}),
        "Sky": build_tri_mesh("SM_ODY_SkySphere", geo.sphere(100.0, 128, 64, inward=True), {"Surface": mi["Stars"]}),
        "Sun": build_tri_mesh("SM_ODY_SunDisc", geo.sphere(100.0, 48, 24), {"Surface": mi["Sun"]}),
        "Hull": build_tri_mesh("SM_OTV_Meridian_Hull", geo.transit_vehicle(), mi),
        "Plume": build_tri_mesh("SM_OTV_Meridian_Plume", geo.vehicle_plume(), {"Plume": mi["Plume"]}),
        "RCS": build_tri_mesh("SM_OTV_Meridian_RCS", geo.vehicle_rcs(), {"Plume": mi["RcsPlume"]}),
    }


# ------------------------------------------------------------------------------------------ map
SUN_DIR = (0.1, -0.45, 0.9)  # direction toward the sun

BODIES = [
    dict(id="earth", name="Earth", designation="Sol III  /  Earth Command", radius=1.0e6, loc=(0.0, 0.0, 0.0),
         orbit=1.12, incl=12.0, period=150.0, spin=0.35, real_r=6371.0, real_d=0.0, mi="Earth", atmo="EarthAtmo", atmo_scale=1.022,
         accent=(0.38, 0.75, 0.82),
         summary="Home world. ODYSSEY mission control, crew training and launch operations."),
    dict(id="moon", name="Moon", designation="Luna  /  Gateway Orbit", radius=2.73e5, loc=(7.2e6, 9.0e6, 6.0e5),
         orbit=1.35, incl=8.0, period=110.0, spin=0.12, real_r=1737.4, real_d=384400.0, mi="Moon", atmo=None, atmo_scale=1.0,
         accent=(0.75, 0.77, 0.8),
         summary="Earth's natural satellite. Gateway station and in-situ resource staging."),
    dict(id="mars", name="Mars", designation="Sol IV  /  Ares Base", radius=5.32e5, loc=(-2.6e7, 3.0e7, 1.2e6),
         orbit=1.22, incl=18.0, period=130.0, spin=0.3, real_r=3389.5, real_d=225.0e6, mi="Mars", atmo="MarsAtmo", atmo_scale=1.03,
         accent=(0.84, 0.47, 0.29),
         summary="The red planet. Destination of the ODYSSEY deep space program."),
]


def rot_from_dir(d):
    x, y, z = d
    l = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / l, y / l, z / l
    return unreal.Rotator(roll=0.0, pitch=math.degrees(math.asin(z)), yaw=math.degrees(math.atan2(y, x)))


def build_map(meshes, mi):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if eal.does_asset_exist(MAP):
        les.load_level(MAP)
        for a in eas.get_all_level_actors():
            if a.get_class().get_name() not in ("WorldSettings", "Brush", "DefaultPhysicsVolume", "GameplayDebuggerPlayerManager"):
                eas.destroy_actor(a)
    else:
        les.new_level(MAP)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    ws = world.get_world_settings()
    ws.set_editor_property("default_game_mode", unreal.OdysseySpaceGameMode.static_class())
    ws.set_editor_property("kill_z", -1.0e12)
    ws.set_editor_property("enable_world_bounds_checks", False)

    def spawn(cls, label, loc=(0, 0, 0), rot=None):
        a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc), rot or unreal.Rotator(0, 0, 0))
        a.set_actor_label(label)
        a.set_folder_path("Space")
        report["actors"].append(label)
        return a

    # sun light (travels opposite to the sun direction)
    sun = spawn(unreal.DirectionalLight, "Sun", rot=rot_from_dir(tuple(-v for v in SUN_DIR)))
    lc_ = sun.get_component_by_class(unreal.DirectionalLightComponent)
    lc_.set_editor_property("intensity", 6.0)
    lc_.set_editor_property("light_source_angle", 0.53)
    lc_.set_editor_property("use_temperature", True)
    lc_.set_editor_property("temperature", 5900.0)
    lc_.set_editor_property("dynamic_shadow_distance_movable_light", 60000.0)
    lc_.set_editor_property("cast_shadows", True)
    lc_.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

    bodies = []
    for b in BODIES:
        a = spawn(unreal.OdysseyCelestialBody, f"Body_{b['name']}", b["loc"])
        a.set_editor_property("body_id", b["id"])
        a.set_editor_property("display_name", b["name"])
        a.set_editor_property("designation", b["designation"])
        a.set_editor_property("summary", b["summary"])
        a.set_editor_property("radius", b["radius"])
        a.set_editor_property("orbit_factor", b["orbit"])
        a.set_editor_property("orbit_inclination", b["incl"])
        a.set_editor_property("orbit_period_seconds", b["period"])
        a.set_editor_property("spin_degrees_per_second", b["spin"])
        a.set_editor_property("real_radius_km", b["real_r"])
        a.set_editor_property("real_distance_from_earth_km", b["real_d"])
        a.set_editor_property("atmosphere_scale", b["atmo_scale"])
        a.set_editor_property("accent_color", unreal.LinearColor(*b["accent"], 1))
        surf = a.get_editor_property("surface")
        surf.set_static_mesh(meshes["Planet"])
        surf.set_material(0, mi[b["mi"]])
        atm = a.get_editor_property("atmosphere")
        if b["atmo"]:
            atm.set_static_mesh(meshes["Atmo"])
            atm.set_material(0, mi[b["atmo"]])
        k = b["radius"] / 100.0
        surf.set_editor_property("relative_scale3d", unreal.Vector(k, k, k))
        atm.set_editor_property("relative_scale3d", unreal.Vector(k * b["atmo_scale"], k * b["atmo_scale"], k * b["atmo_scale"]))
        bodies.append(a)

    veh = spawn(unreal.OdysseyTransitVehicle, "OTV1_Meridian", (0, 0, 1.2e6))
    veh.set_editor_property("length", geo.VEHICLE_LENGTH)
    veh.get_editor_property("hull").set_static_mesh(meshes["Hull"])
    plume = veh.get_editor_property("plume")
    plume.set_static_mesh(meshes["Plume"])
    plume.set_editor_property("relative_location", unreal.Vector(geo.NOZZLE_EXIT_X, 0, 0))
    veh.get_editor_property("rcs").set_static_mesh(meshes["RCS"])
    veh.get_editor_property("engine_light").set_editor_property("relative_location", unreal.Vector(geo.NOZZLE_EXIT_X - 600, 0, 0))

    sky = spawn(unreal.StaticMeshActor, "Sky_Starfield")
    smc = sky.static_mesh_component
    smc.set_static_mesh(meshes["Sky"])
    smc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    smc.set_editor_property("cast_shadow", False)
    smc.set_editor_property("never_distance_cull", True)
    smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    sky.set_actor_scale3d(unreal.Vector(1.0e6, 1.0e6, 1.0e6))

    disc = spawn(unreal.StaticMeshActor, "Sun_Disc")
    dmc = disc.static_mesh_component
    dmc.set_static_mesh(meshes["Sun"])
    dmc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
    dmc.set_editor_property("cast_shadow", False)
    dmc.set_editor_property("never_distance_cull", True)
    dmc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    disc.set_actor_scale3d(unreal.Vector(4000.0, 4000.0, 4000.0))

    director = spawn(unreal.OdysseyTransitDirector, "TransitDirector", (0, 0, 0))
    director.set_editor_property("bodies", bodies)
    director.set_editor_property("vehicle", veh)
    director.set_editor_property("sky_actor", sky)
    director.set_editor_property("sun_disc_actor", disc)

    ppv = spawn(unreal.PostProcessVolume, "PP_Space")
    ppv.set_editor_property("unbound", True)
    s = ppv.get_editor_property("settings")
    for prop, val in (("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL), ("auto_exposure_bias", 0.0),
                      ("auto_exposure_apply_physical_camera_exposure", False),
                      ("bloom_intensity", 0.75), ("bloom_threshold", 1.2),
                      ("lens_flare_intensity", 0.08), ("lens_flare_threshold", 12.0),
                      ("vignette_intensity", 0.38), ("film_grain_intensity", 0.025),
                      ("motion_blur_amount", 0.0), ("scene_fringe_intensity", 0.0),
                      ("color_saturation", unreal.Vector4(1.0, 1.0, 1.0, 1.04)),
                      ("color_gain_shadows", unreal.Vector4(0.97, 1.0, 1.04, 1.0))):
        try:
            s.set_editor_property("override_" + prop, True)
        except Exception:
            pass
        s.set_editor_property(prop, val)
    ppv.set_editor_property("settings", s)

    les.save_current_level()
    log(f"map {MAP} written: {len(report['actors'])} actors")


def load_existing():
    names = {"Earth": "MI_Earth_Surface", "Moon": "MI_Moon_Surface", "Mars": "MI_Mars_Surface", "EarthAtmo": "MI_Earth_Atmosphere",
             "MarsAtmo": "MI_Mars_Atmosphere"}
    mi = {k: unreal.load_asset(f"{MAT_DIR}/{v}") for k, v in names.items()}
    meshes = {k: unreal.load_asset(f"{MESH_DIR}/{v}") for k, v in {
        "Planet": "SM_ODY_PlanetSphere", "Atmo": "SM_ODY_AtmosphereSphere", "Sky": "SM_ODY_SkySphere", "Sun": "SM_ODY_SunDisc",
        "Hull": "SM_OTV_Meridian_Hull", "Plume": "SM_OTV_Meridian_Plume", "RCS": "SM_OTV_Meridian_RCS"}.items()}
    return meshes, mi


def main():
    # ODY_STEPS (optional global from the caller): "all" (default), "materials+map", "map"
    steps = globals().get("ODY_STEPS", "all")
    for d in (TEX_DIR, MAT_DIR, MESH_DIR, MAP_DIR):
        eal.make_directory(d)
    if steps == "all":
        tex = import_textures()
        mi = build_materials(tex)
        meshes = build_meshes(mi)
    elif steps == "materials+map":
        tex = {n: unreal.load_asset(f"{TEX_DIR}/{n}") for n in TEXTURES}
        build_materials(tex)
        meshes, mi = load_existing()
    else:
        meshes, mi = load_existing()
    build_map(meshes, mi)
    out = os.path.join(PROJECT, "Saved", "Odyssey")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "space_assets_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    log("build_space_experience: done")


main()
