"""ODYSSEY Asset Pack - shared material family, GLB writer and GLB re-loader/validator.

Coordinate conversion (documented and verified by `validate_glb`):
    authoring (Unreal) cm: +X forward, +Y right, +Z up
    glTF metres:           gl.x = ue.x / 100, gl.y = ue.z / 100, gl.z = ue.y / 100
That mapping is a reflection (det = -1), which is exactly the handedness change between Unreal's
left-handed Z-up frame and glTF's right-handed Y-up frame; triangle winding is reversed on export
so faces stay counter-clockwise (front-facing) in glTF. Unreal's glTF/Interchange importer applies
the inverse mapping (UE = (gl.x, gl.z, gl.y) x 100), so the asset arrives unrotated, unmirrored,
with +X forward and its pivot at the node origin.
"""
from __future__ import annotations

import json
import math
import struct

from od_core import Node, is_convex, poly_area2, ear_clip

# ------------------------------------------------------------------------------------------ materials
def srgb_to_linear(hexcol):
    h = hexcol.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


# name: (base hex, metallic, roughness, emissive hex or None, emissive strength, alpha)
MATERIALS = {
    "OD_MAT_AerospaceWhite":        ("#D8D9D5", 0.0, 0.42, None, 0.0, 1.0),
    "OD_MAT_Graphite":              ("#1C2025", 0.0, 0.58, None, 0.0, 1.0),
    "OD_MAT_Gunmetal":              ("#454B52", 0.65, 0.45, None, 0.0, 1.0),
    "OD_MAT_BrushedAluminum":       ("#92989E", 1.0, 0.30, None, 0.0, 1.0),
    "OD_MAT_Rubber":                ("#141618", 0.0, 0.88, None, 0.0, 1.0),
    "OD_MAT_Glass":                 ("#9FB7BF", 0.0, 0.04, None, 0.0, 0.22),
    "OD_MAT_Display":               ("#09131C", 0.0, 0.12, "#0E2A3A", 1.0, 1.0),
    "OD_MAT_IonBlue_Emissive":      ("#61BED2", 0.0, 0.30, "#61BED2", 2.2, 1.0),
    "OD_MAT_Amber_Emissive":        ("#D69A35", 0.0, 0.35, "#D69A35", 1.8, 1.0),
    "OD_MAT_EmergencyRed_Emissive": ("#B84743", 0.0, 0.35, "#B84743", 1.8, 1.0),
    # family extensions (documented in README): painted hazard amber (non-emissive) and a
    # light-fixture diffuser. Same palette hues, no new colours.
    "OD_MAT_HazardPaint":           ("#D69A35", 0.0, 0.55, None, 0.0, 1.0),
    "OD_MAT_Diffuser_Emissive":     ("#EEF2F3", 0.0, 0.50, "#EAF4F7", 4.0, 1.0),
}

# short aliases used by the asset scripts
WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, GLASS, DISPLAY, ION, AMBER, RED, HAZARD, DIFFUSER = (
    "OD_MAT_AerospaceWhite", "OD_MAT_Graphite", "OD_MAT_Gunmetal", "OD_MAT_BrushedAluminum", "OD_MAT_Rubber",
    "OD_MAT_Glass", "OD_MAT_Display", "OD_MAT_IonBlue_Emissive", "OD_MAT_Amber_Emissive",
    "OD_MAT_EmergencyRed_Emissive", "OD_MAT_HazardPaint", "OD_MAT_Diffuser_Emissive")
EMISSIVE = {ION, AMBER, RED, DIFFUSER}


def material_json(name):
    base, metal, rough, emi, strength, alpha = MATERIALS[name]
    m = {"name": name,
         "pbrMetallicRoughness": {"baseColorFactor": srgb_to_linear(base) + [alpha],
                                  "metallicFactor": metal, "roughnessFactor": rough},
         "extras": {"od_base_srgb": base}}
    if emi:
        m["emissiveFactor"] = srgb_to_linear(emi)
        if strength != 1.0:
            m["extensions"] = {"KHR_materials_emissive_strength": {"emissiveStrength": strength}}
    if alpha < 1.0:
        m["alphaMode"] = "BLEND"
    return m


# ------------------------------------------------------------------------------------------ conversion
def to_gl(p):
    return (p[0] / 100.0, p[2] / 100.0, p[1] / 100.0)


def dir_to_gl(d):
    return (d[0], d[2], d[1])


# ------------------------------------------------------------------------------------------ writer
class _Bin:
    def __init__(self):
        self.data = bytearray()
        self.views = []
        self.accessors = []

    def add(self, raw: bytes, target, comp, count, typ, mn=None, mx=None):
        while len(self.data) % 4:
            self.data.append(0)
        off = len(self.data)
        self.data += raw
        self.views.append({"buffer": 0, "byteOffset": off, "byteLength": len(raw), "target": target})
        acc = {"bufferView": len(self.views) - 1, "componentType": comp, "count": count, "type": typ}
        if mn is not None:
            acc["min"], acc["max"] = mn, mx
        self.accessors.append(acc)
        return len(self.accessors) - 1


def _triangulate(f):
    m = len(f.pts)
    if m == 3:
        return [(0, 1, 2)]
    n = f.nrm[0]
    ax = max(range(3), key=lambda i: abs(n[i]))
    o1, o2 = [i for i in range(3) if i != ax]
    p2 = [(p[o1], p[o2]) for p in f.pts]
    if n[ax] < 0:
        p2 = [(x, -y) for x, y in p2]
    if is_convex(p2):
        return [(0, k, k + 1) for k in range(1, m - 1)]
    if poly_area2(p2) < 0:
        p2r = list(reversed(p2))
        return [(m - 1 - a, m - 1 - b, m - 1 - c) for a, b, c in ear_clip(p2r)]
    return ear_clip(p2)


def _node_mesh(node: Node):
    """Group the node's faces by material -> {mat: (pos, nrm, uv, idx)} in node-local glTF space."""
    groups = {}
    piv = node.pivot
    for s in node.solids:
        for f in s.faces:
            mat = f.mat or s.mat
            g = groups.setdefault(mat, ([], [], [], []))
            pos, nrm, uv, idx = g
            base = len(pos)
            for p, n, t in zip(f.pts, f.nrm, f.uv):
                pos.append(to_gl((p[0] - piv[0], p[1] - piv[1], p[2] - piv[2])))
                nrm.append(dir_to_gl(n))
                uv.append(t)
            # triangulate (fan if convex, ear clipping otherwise); winding reversed for the handedness flip
            for (i0, i1, i2) in _triangulate(f):
                idx += [base + i0, base + i2, base + i1]
    return groups


def write_glb(path, root: Node, asset_extras=None):
    b = _Bin()
    mats = []
    mat_index = {}
    meshes = []
    nodes = []

    def mat_id(name):
        if name not in mat_index:
            mat_index[name] = len(mats)
            mats.append(material_json(name))
        return mat_index[name]

    def build(node: Node, parent_pivot):
        nd = {"name": node.name}
        t = to_gl((node.pivot[0] - parent_pivot[0], node.pivot[1] - parent_pivot[1], node.pivot[2] - parent_pivot[2]))
        if any(abs(c) > 1e-9 for c in t):
            nd["translation"] = [round(c, 6) for c in t]
        extras = {"od_role": node.role}
        if node.motion:
            extras["od_motion"] = node.motion
        if node.note:
            extras["od_note"] = node.note
        nd["extras"] = extras
        if node.solids:
            prims = []
            for mat, (pos, nrm, uv, idx) in sorted(_node_mesh(node).items()):
                n = len(pos)
                mn = [min(p[i] for p in pos) for i in range(3)]
                mx = [max(p[i] for p in pos) for i in range(3)]
                a_pos = b.add(struct.pack(f"<{3 * n}f", *[c for p in pos for c in p]), 34962, 5126, n, "VEC3", mn, mx)
                a_nrm = b.add(struct.pack(f"<{3 * n}f", *[c for p in nrm for c in p]), 34962, 5126, n, "VEC3")
                a_uv = b.add(struct.pack(f"<{2 * n}f", *[c for p in uv for c in p]), 34962, 5126, n, "VEC2")
                if n < 65536:
                    raw = struct.pack(f"<{len(idx)}H", *idx); comp = 5123
                    if len(raw) % 4:
                        raw += b"\0\0"
                else:
                    raw = struct.pack(f"<{len(idx)}I", *idx); comp = 5125
                a_idx = b.add(raw, 34963, comp, len(idx), "SCALAR")
                prims.append({"attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "TEXCOORD_0": a_uv},
                              "indices": a_idx, "material": mat_id(mat), "mode": 4})
            meshes.append({"name": node.name + "_Mesh", "primitives": prims})
            nd["mesh"] = len(meshes) - 1
        nodes.append(nd)
        my = len(nodes) - 1
        kids = [build(c, node.pivot) for c in node.children]
        if kids:
            nd["children"] = kids
        return my

    root_idx = build(root, (0.0, 0.0, 0.0))
    # fix accessor byteLength of padded index buffers
    for acc in b.accessors:
        v = b.views[acc["bufferView"]]
        if acc["componentType"] == 5123:
            v["byteLength"] = acc["count"] * 2
    while len(b.data) % 4:
        b.data.append(0)
    gltf = {
        "asset": {"version": "2.0", "generator": "ODYSSEY Asset Pack od_gltf.py (procedural, pure Python)",
                  "extras": asset_extras or {}},
        "extensionsUsed": ["KHR_materials_emissive_strength"],
        "scene": 0,
        "scenes": [{"name": root.name, "nodes": [root_idx]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": mats,
        "accessors": b.accessors,
        "bufferViews": b.views,
        "buffers": [{"byteLength": len(b.data)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(js) % 4:
        js += b" "
    total = 12 + 8 + len(js) + 8 + len(b.data)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A)); fh.write(js)
        fh.write(struct.pack("<II", len(b.data), 0x004E4942)); fh.write(bytes(b.data))
    return total


# ------------------------------------------------------------------------------------------ reader / validator
_COMP = {5126: ("f", 4), 5123: ("H", 2), 5125: ("I", 4), 5121: ("B", 1)}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path):
    with open(path, "rb") as fh:
        data = fh.read()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2 and total == len(data), "bad GLB header"
    jl, jt = struct.unpack_from("<II", data, 12)
    assert jt == 0x4E4F534A
    gltf = json.loads(data[20:20 + jl])
    bl, bt = struct.unpack_from("<II", data, 20 + jl)
    assert bt == 0x004E4942
    binb = data[28 + jl:28 + jl + bl]
    return gltf, binb


def accessor(gltf, binb, i):
    a = gltf["accessors"][i]
    v = gltf["bufferViews"][a["bufferView"]]
    fmt, size = _COMP[a["componentType"]]
    n = a["count"] * _NCOMP[a["type"]]
    off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    vals = struct.unpack_from(f"<{n}{fmt}", binb, off)
    k = _NCOMP[a["type"]]
    return [vals[j:j + k] for j in range(0, n, k)] if k > 1 else list(vals)


def validate_glb(path):
    """Re-load a GLB and return (report dict, list of problems). Bounds are reported in
    UNREAL space (cm, +X forward, +Y right, +Z up) by applying the importer's inverse mapping."""
    gltf, binb = read_glb(path)
    problems = []
    nodes = gltf["nodes"]
    world = {}

    def visit(i, parent_t):
        n = nodes[i]
        t = n.get("translation", [0, 0, 0])
        if "rotation" in n or "scale" in n or "matrix" in n:
            problems.append(f"node {n['name']} has rotation/scale/matrix (expected translation-only pivots)")
        wt = [parent_t[k] + t[k] for k in range(3)]
        world[i] = wt
        for c in n.get("children", []):
            visit(c, wt)

    for r in gltf["scenes"][0]["nodes"]:
        visit(r, [0, 0, 0])
    lo = [1e18] * 3
    hi = [-1e18] * 3
    tris = 0
    degenerate = 0
    node_names = []
    mat_slots = [m["name"] for m in gltf.get("materials", [])]
    for i, n in enumerate(nodes):
        node_names.append(n["name"])
        if "mesh" not in n:
            continue
        for prim in gltf["meshes"][n["mesh"]]["primitives"]:
            pos = accessor(gltf, binb, prim["attributes"]["POSITION"])
            nrm = accessor(gltf, binb, prim["attributes"]["NORMAL"])
            uv = accessor(gltf, binb, prim["attributes"]["TEXCOORD_0"])
            idx = accessor(gltf, binb, prim["indices"])
            if not (len(pos) == len(nrm) == len(uv)):
                problems.append(f"{n['name']}: attribute count mismatch")
            if any(i_ >= len(pos) for i_ in idx):
                problems.append(f"{n['name']}: index out of range")
            for q in nrm:
                l = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2)
                if abs(l - 1) > 1e-3:
                    problems.append(f"{n['name']}: non-unit normal"); break
            for p in pos:
                if any(math.isnan(c) or math.isinf(c) for c in p):
                    problems.append(f"{n['name']}: NaN/inf position"); break
            wt = world[i]
            for p in pos:
                ue = ((p[0] + wt[0]) * 100.0, (p[2] + wt[2]) * 100.0, (p[1] + wt[1]) * 100.0)
                for k in range(3):
                    lo[k] = min(lo[k], ue[k]); hi[k] = max(hi[k], ue[k])
            for k in range(0, len(idx), 3):
                a, b_, c = pos[idx[k]], pos[idx[k + 1]], pos[idx[k + 2]]
                e1 = (b_[0] - a[0], b_[1] - a[1], b_[2] - a[2])
                e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                area = 0.5 * math.sqrt(cr[0] ** 2 + cr[1] ** 2 + cr[2] ** 2)
                if area < 1e-9:  # < 0.01 mm^2
                    degenerate += 1
                else:
                    # winding must agree with the stored normal (front faces CCW in glTF)
                    na = nrm[idx[k]]
                    if cr[0] * na[0] + cr[1] * na[1] + cr[2] * na[2] < 0:
                        problems.append(f"{n['name']}: triangle winding disagrees with normal"); break
            tris += len(idx) // 3
    if degenerate:
        problems.append(f"{degenerate} degenerate triangles")
    report = {
        "file": path,
        "nodes": node_names,
        "material_slots": mat_slots,
        "triangles": tris,
        "bounds_ue_cm": {"min": [round(v, 3) for v in lo], "max": [round(v, 3) for v in hi]},
        "size_m": {"D_x": round((hi[0] - lo[0]) / 100, 4), "W_y": round((hi[1] - lo[1]) / 100, 4),
                   "H_z": round((hi[2] - lo[2]) / 100, 4)},
        "root_node": nodes[gltf["scenes"][0]["nodes"][0]]["name"],
        "root_translation": nodes[gltf["scenes"][0]["nodes"][0]].get("translation", [0, 0, 0]),
    }
    return report, problems
