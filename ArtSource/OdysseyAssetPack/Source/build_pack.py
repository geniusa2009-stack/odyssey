"""Build, check, export and re-validate the ODYSSEY Earth Command asset pack.

    python3 -I Source/build_pack.py            # all assets
    python3 -I Source/build_pack.py a01 a05    # selected (module prefix)

Writes GLB/<name>.glb, Specs/<name>.json + .md and Specs/ValidationReport.{json,md}.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "assets"))

from od_check import check_assembly, assembly_bounds, envelope_problems, expected_bounds  # noqa: E402
from od_gltf import write_glb, validate_glb, MATERIALS, EMISSIVE  # noqa: E402

PACK = os.path.dirname(HERE)
GLB_DIR = os.path.join(PACK, "GLB")
SPEC_DIR = os.path.join(PACK, "Specs")

MODULES = ["a01_power_console", "a02_power_bus_b", "a03_training_simulator", "a04_sample_analyzer",
           "a05_mcc_main_console", "a06_sliding_door", "a07_emergency_bulkhead", "a08_orion_terminal",
           "a09_server_rack", "a10_observation_window", "a11_ceiling_light", "a12_wall_utility_panel",
           "a13_ventilation_module", "a14_supply_crate", "a15_mcc_chair"]


def spec_for(asset, check, glb_report, problems):
    W, H, D = asset.envelope
    lo, hi = expected_bounds(asset.envelope, asset.pivot)
    nodes = []
    mats_used = {}
    emissive = []
    for n in asset.root.walk():
        tris = sum(s.tri_count() for s in n.solids)
        nm = sorted({(f.mat or s.mat) for s in n.solids for f in s.faces})
        for s in n.solids:
            for f in s.faces:
                m = f.mat or s.mat
                mats_used[m] = mats_used.get(m, 0) + len(f.pts) - 2
        if any(m in EMISSIVE for m in nm):
            emissive.append({"node": n.name, "materials": [m for m in nm if m in EMISSIVE]})
        nodes.append({"name": n.name, "role": n.role, "pivot_cm_ue": [round(c, 3) for c in n.pivot],
                      "triangles": tris, "materials": nm, "motion": n.motion, "note": n.note,
                      "children": [c.name for c in n.children]})
    return {
        "name": asset.name,
        "title": asset.title,
        "reference_image": asset.reference,
        "description": asset.description,
        "units": "metres in GLB (1 glTF unit = 1 m); centimetres in Unreal (1 uu = 1 cm)",
        "dimensions_m": {"W_y": W / 100, "H_z": H / 100, "D_x": D / 100},
        "pivot": {"type": asset.pivot, "text": asset.pivot_text,
                  "expected_bounds_ue_cm": {"min": lo, "max": hi}},
        "axes": {"unreal": "+X forward (asset front), +Y right, +Z up",
                 "gltf": "gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF)"},
        "movable_components": [n for n in nodes if n["role"] in ("movable", "interactive")],
        "static_components": [n["name"] for n in nodes if n["role"] in ("static", "display", "emissive")],
        "collision_recommendation": asset.collision,
        "nanite_recommendation": asset.nanite,
        "material_groups": {m: {"triangles": t, "base_srgb": MATERIALS[m][0], "metallic": MATERIALS[m][1],
                                "roughness": MATERIALS[m][2], "emissive": m in EMISSIVE}
                            for m, t in sorted(mats_used.items())},
        "emissive_components": emissive,
        "interaction_points": [{"name": a, "socket": b, "text": c} for a, b, c in asset.interaction],
        "mounting_points": [{"name": a, "socket": b, "text": c} for a, b, c in asset.mounting],
        "nodes": nodes,
        "notes": asset.notes,
        "validation": {"glb": glb_report, "glb_problems": problems,
                       "assembly": {"solids": check["solids"], "hulls": check["hulls"],
                                    "components": check["components"],
                                    "intersections": check["intersections"][:20],
                                    "floating_groups": check["floating_groups"][:10]}},
    }


def spec_md(sp):
    d = sp["dimensions_m"]
    L = [f"# {sp['name']} - {sp['title']}", "", sp["description"], "",
         f"Reference (visual only): `{sp['reference_image']}`", "",
         "| Property | Value |", "|---|---|",
         f"| Dimensions (m) | W {d['W_y']:.2f} (Y) x H {d['H_z']:.2f} (Z) x D {d['D_x']:.2f} (X) |",
         f"| Pivot | {sp['pivot']['type']}: {sp['pivot']['text']} |",
         f"| Forward / Up | {sp['axes']['unreal']} |",
         f"| glTF mapping | {sp['axes']['gltf']} |",
         f"| Triangles | {sp['validation']['glb']['triangles']} |",
         f"| Collision | {sp['collision_recommendation']} |",
         f"| Nanite | {sp['nanite_recommendation']} |", "",
         "## Node hierarchy", "", "| Node | Role | Tris | Motion | Note |", "|---|---|---|---|---|"]
    for n in sp["nodes"]:
        mo = json.dumps(n["motion"]) if n["motion"] else ""
        L.append(f"| `{n['name']}` | {n['role']} | {n['triangles']} | {mo} | {n['note']} |")
    L += ["", "## Material groups", "", "| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |", "|---|---|---|---|---|---|"]
    for m, g in sp["material_groups"].items():
        L.append(f"| `{m}` | {g['triangles']} | {g['base_srgb']} | {g['metallic']} | {g['roughness']} | {'yes' if g['emissive'] else ''} |")
    L += ["", "## Emissive components", ""] + [f"- `{e['node']}`: {', '.join(e['materials'])}" for e in sp["emissive_components"]]
    L += ["", "## Interaction points", ""] + [f"- **{i['name']}** (`{i['socket']}`): {i['text']}" for i in sp["interaction_points"]]
    L += ["", "## Mounting points", ""] + [f"- **{i['name']}** (`{i['socket']}`): {i['text']}" for i in sp["mounting_points"]]
    if sp["notes"]:
        L += ["", "## Notes", ""] + [f"- {x}" for x in sp["notes"]]
    v = sp["validation"]
    L += ["", "## Validation (re-loaded GLB)", "",
          f"- Bounds (UE cm): min {v['glb']['bounds_ue_cm']['min']} max {v['glb']['bounds_ue_cm']['max']}",
          f"- Expected: min {sp['pivot']['expected_bounds_ue_cm']['min']} max {sp['pivot']['expected_bounds_ue_cm']['max']}",
          f"- Material slots: {', '.join(v['glb']['material_slots'])}",
          f"- GLB problems: {v['glb_problems'] or 'none'}",
          f"- Assembly: {v['assembly']['solids']} solids, {v['assembly']['components']} connected component(s), "
          f"{len(v['assembly']['intersections'])} interpenetration(s)"]
    return "\n".join(L) + "\n"


def run(selected):
    os.makedirs(GLB_DIR, exist_ok=True)
    os.makedirs(SPEC_DIR, exist_ok=True)
    summary = []
    for mod_name in MODULES:
        if selected and not any(mod_name.startswith(s) for s in selected):
            continue
        if not os.path.exists(os.path.join(HERE, "assets", mod_name + ".py")):
            continue
        t0 = time.time()
        mod = importlib.import_module(mod_name)
        asset = mod.build()
        chk = check_assembly(asset.root, asset.allow_pairs)
        lo, hi = assembly_bounds(asset.root)
        env = envelope_problems(lo, hi, asset.envelope, asset.pivot)
        path = os.path.join(GLB_DIR, asset.name + ".glb")
        size = write_glb(path, asset.root, {"od_asset": asset.name, "od_envelope_cm_WHD": list(asset.envelope),
                                             "od_pivot": asset.pivot, "od_units": "m", "od_forward": "+X (glTF +X)",
                                             "od_up": "+Y glTF = +Z Unreal"})
        rep, probs = validate_glb(path)
        # GLB-side envelope check (re-loaded bounds)
        env_glb = envelope_problems(rep["bounds_ue_cm"]["min"], rep["bounds_ue_cm"]["max"], asset.envelope, asset.pivot)
        probs = probs + [f"envelope: {e}" for e in env_glb]
        if rep["root_node"] != asset.name:
            probs.append("root node name mismatch")
        sp = spec_for(asset, chk, rep, probs)
        with open(os.path.join(SPEC_DIR, asset.name + ".json"), "w") as fh:
            json.dump(sp, fh, indent=1)
        with open(os.path.join(SPEC_DIR, asset.name + ".md"), "w") as fh:
            fh.write(spec_md(sp))
        ok = not probs and not env and not chk["intersections"] and not chk["floating_groups"]
        line = {"asset": asset.name, "ok": ok, "tris": rep["triangles"], "bytes": size, "nodes": len(rep["nodes"]),
                "materials": len(rep["material_slots"]), "size_m": rep["size_m"], "envelope": env,
                "problems": probs, "intersections": chk["intersections"][:12], "floating": chk["floating_groups"][:6],
                "seconds": round(time.time() - t0, 1)}
        summary.append(line)
        print(f"{'OK ' if ok else 'FAIL'} {asset.name}: {rep['triangles']} tris, {len(rep['nodes'])} nodes, "
              f"{rep['size_m']}, {line['seconds']}s")
        for k in ("envelope", "problems", "intersections", "floating"):
            for x in line[k]:
                print("    ", k, x)
    return summary


if __name__ == "__main__":
    res = run(sys.argv[1:])
    if not sys.argv[1:]:
        with open(os.path.join(SPEC_DIR, "ValidationReport.json"), "w") as fh:
            json.dump(res, fh, indent=1)
        md = ["# ODYSSEY Asset Pack - validation report", "",
              "| Asset | Result | Tris | Nodes | Mat slots | Size D x W x H (m) |", "|---|---|---|---|---|---|"]
        for r in res:
            s = r["size_m"]
            md.append(f"| {r['asset']} | {'PASS' if r['ok'] else 'FAIL'} | {r['tris']} | {r['nodes']} | {r['materials']} | "
                      f"{s['D_x']} x {s['W_y']} x {s['H_z']} |")
        with open(os.path.join(SPEC_DIR, "ValidationReport.md"), "w") as fh:
            fh.write("\n".join(md) + "\n")
