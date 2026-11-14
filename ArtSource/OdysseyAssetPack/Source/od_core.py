"""ODYSSEY Asset Pack - procedural hard-surface core (pure Python, no dependencies).

Authoring space = Unreal space, in CENTIMETRES:
    +X = the asset's front (the side an operator faces / walks up to)
    +Y = the asset's right (so an operator standing in front sees +Y on their LEFT)
    +Z = up
The GLB writer (od_gltf.py) converts to glTF metres / Y-up:  gl = (x, z, y) / 100.
Unreal's glTF importer applies the inverse swap (UE = (gl.x, gl.z, gl.y) * 100), so the asset
lands in UE with +X forward, +Y right, +Z up and 1 uu = 1 cm, exactly as authored here.

Every Solid is a CONVEX piece (or a ring/prism that is decomposed into convex hulls for checks).
Faces carry their own UVs (1 UV unit = 1 m, planar per face) unless a primitive sets explicit
0..1 UVs (displays). Normals are flat (hard-surface) except cylinder/tube walls (smooth).
"""
from __future__ import annotations

import math

EPS = 1e-9


# ------------------------------------------------------------------------------------------ vectors
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def length(a): return math.sqrt(dot(a, a))


def norm(a):
    l = length(a)
    return (a[0] / l, a[1] / l, a[2] / l) if l > EPS else (0.0, 0.0, 0.0)


def lerp(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


# ------------------------------------------------------------------------------------------ matrices
IDENT = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def mat_cols(c0, c1, c2):
    """Matrix whose columns are c0, c1, c2 (local x, y, z axes expressed in world)."""
    return ((c0[0], c1[0], c2[0]), (c0[1], c1[1], c2[1]), (c0[2], c1[2], c2[2]))


def mat_mul(A, B):
    return tuple(tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_vec(M, v):
    return (M[0][0] * v[0] + M[0][1] * v[1] + M[0][2] * v[2],
            M[1][0] * v[0] + M[1][1] * v[1] + M[1][2] * v[2],
            M[2][0] * v[0] + M[2][1] * v[1] + M[2][2] * v[2])


def rot_x(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def rot_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def axis_angle(axis, deg):
    x, y, z = norm(axis)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    t = 1 - c
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


# ------------------------------------------------------------------------------------------ 2D helpers
def poly_area2(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a  # 2 x signed area (CCW > 0)


def ccw(poly):
    return list(poly) if poly_area2(poly) > 0 else list(reversed(poly))


def is_convex(poly):
    n = len(poly)
    sign = 0
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) < 1e-9:
            continue
        s = 1 if cr > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def edge_normals2(poly):
    """Outward 2D normals of each edge i (poly[i] -> poly[i+1]) for a CCW polygon."""
    out = []
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        l = math.hypot(dx, dy) or 1.0
        out.append((dy / l, -dx / l))
    return out


def offset_poly(poly, d):
    """Miter offset of a CCW polygon; d > 0 grows it, d < 0 shrinks it."""
    n = len(poly)
    en = edge_normals2(poly)
    out = []
    for i in range(n):
        n0, n1 = en[i - 1], en[i]
        k = 1.0 + n0[0] * n1[0] + n0[1] * n1[1]
        k = max(k, 0.2)
        out.append((poly[i][0] + d * (n0[0] + n1[0]) / k, poly[i][1] + d * (n0[1] + n1[1]) / k))
    return out


def chamfer_poly(poly, c):
    """Cut every corner of a polygon by c (float or per-corner list); 0 keeps the corner."""
    n = len(poly)
    cs = c if isinstance(c, (list, tuple)) else [c] * n
    out = []
    for i in range(n):
        p, a, b = poly[i], poly[i - 1], poly[(i + 1) % n]
        ci = cs[i]
        if ci <= 0:
            out.append(p)
            continue
        da = (a[0] - p[0], a[1] - p[1]); la = math.hypot(*da)
        db = (b[0] - p[0], b[1] - p[1]); lb = math.hypot(*db)
        out.append((p[0] + da[0] / la * ci, p[1] + da[1] / la * ci))
        out.append((p[0] + db[0] / lb * ci, p[1] + db[1] / lb * ci))
    return out


def rect(u0, u1, v0, v1, c=0.0):
    p = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return chamfer_poly(p, c) if (c if not isinstance(c, (list, tuple)) else max(c)) > 0 else p


def circle(r, n, cu=0.0, cv=0.0, phase=None):
    ph = math.pi / n if phase is None else phase
    return [(cu + r * math.cos(ph + 2 * math.pi * i / n), cv + r * math.sin(ph + 2 * math.pi * i / n)) for i in range(n)]


def clip_poly(poly, clip):
    """Sutherland-Hodgman: clip polygon by a convex CCW clip polygon."""
    out = list(poly)
    m = len(clip)
    for i in range(m):
        a, b = clip[i], clip[(i + 1) % m]
        inp, out = out, []
        if not inp:
            break

        def inside(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

        def inter(p, q):
            x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
            x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            if inside(q):
                if not inside(p):
                    out.append(inter(p, q))
                out.append(q)
            elif inside(p):
                out.append(inter(p, q))
    # drop near-duplicate points
    res = []
    for p in out:
        if not res or math.hypot(p[0] - res[-1][0], p[1] - res[-1][1]) > 1e-6:
            res.append(p)
    if len(res) > 1 and math.hypot(res[0][0] - res[-1][0], res[0][1] - res[-1][1]) < 1e-6:
        res.pop()
    return res


def ear_clip(poly):
    """Triangulate a simple CCW polygon -> list of index triples."""
    idx = list(range(len(poly)))
    tris = []

    def cr(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def inside(p, a, b, c):
        return cr(a, b, p) >= -1e-12 and cr(b, c, p) >= -1e-12 and cr(c, a, p) >= -1e-12

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cr(a, b, c) <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


# ------------------------------------------------------------------------------------------ solids
class Face:
    __slots__ = ("pts", "nrm", "uv", "mat")

    def __init__(self, pts, nrm, uv=None, mat=None):
        self.pts = pts      # convex planar polygon, ordered CCW seen from outside
        self.nrm = nrm      # list of per-vertex normals
        self.uv = uv        # list of per-vertex UVs or None (planar projection later)
        self.mat = mat      # material override (None = solid's material)


def _orient(pts, want):
    """Order pts so the polygon's winding normal agrees with `want`."""
    nx = ny = nz = 0.0
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    if nx * want[0] + ny * want[1] + nz * want[2] < 0:
        return list(reversed(pts)), True
    return list(pts), False


def _planar_uv(pts, n):
    ax = max(range(3), key=lambda i: abs(n[i]))
    if ax == 0:
        return [(p[1] / 100.0 * (1 if n[0] > 0 else -1), -p[2] / 100.0) for p in pts]
    if ax == 1:
        return [(p[0] / 100.0 * (-1 if n[1] > 0 else 1), -p[2] / 100.0) for p in pts]
    return [(p[0] / 100.0, p[1] / 100.0 * (1 if n[2] > 0 else -1)) for p in pts]


def make_face(pts, want_normal, vnormals=None, uv=None, mat=None):
    want = norm(want_normal)
    ordered, flipped = _orient(pts, want)
    if vnormals is None:
        vn = [want] * len(ordered)
    else:
        vn = list(reversed(vnormals)) if flipped else list(vnormals)
    if uv is None:
        uvs = _planar_uv(ordered, want)
    else:
        uvs = list(reversed(uv)) if flipped else list(uv)
    return Face(ordered, vn, uvs, mat)


class Hull:
    __slots__ = ("pts", "axes")

    def __init__(self, pts, axes):
        self.pts = pts
        self.axes = axes


class Solid:
    """A material-tagged convex (or convex-decomposed) piece of geometry."""
    __slots__ = ("mat", "faces", "hulls", "label")

    def __init__(self, mat, faces, hulls, label=""):
        self.mat = mat
        self.faces = faces
        self.hulls = hulls
        self.label = label

    def xf(self, R=IDENT, t=(0.0, 0.0, 0.0)):
        det = (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1]) - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
               + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))
        faces = []
        for f in self.faces:
            pts = [add(mat_vec(R, p), t) for p in f.pts]
            nr = [norm(mat_vec(R, n)) for n in f.nrm]
            uv = f.uv
            if det < 0:  # reflection: keep the winding counter-clockwise seen from outside
                pts.reverse(); nr.reverse()
                uv = list(reversed(uv)) if uv else uv
            faces.append(Face(pts, nr, uv, f.mat))
        hulls = [Hull([add(mat_vec(R, p), t) for p in h.pts], [norm(mat_vec(R, a)) for a in h.axes]) for h in self.hulls]
        return Solid(self.mat, faces, hulls, self.label)

    def bounds(self):
        lo = [1e18] * 3
        hi = [-1e18] * 3
        for f in self.faces:
            for p in f.pts:
                for i in range(3):
                    lo[i] = min(lo[i], p[i]); hi[i] = max(hi[i], p[i])
        return lo, hi

    def tri_count(self):
        return sum(len(f.pts) - 2 for f in self.faces)


# ------------------------------------------------------------------------------------------ primitives
def cbox(mat, center, size, bevel=0.0, R=None, label=""):
    """Chamfered box centred at `center` with full `size` along local axes (rotated by R)."""
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    b = min(bevel, hx * 0.45, hy * 0.45, hz * 0.45)
    faces = []
    if b <= 1e-6:
        for ax in range(3):
            for s in (-1, 1):
                pts = []
                for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    p = [0.0, 0.0, 0.0]
                    p[ax] = s * (hx, hy, hz)[ax]
                    o1, o2 = [i for i in range(3) if i != ax]
                    p[o1] = su * (hx, hy, hz)[o1]
                    p[o2] = sv * (hx, hy, hz)[o2]
                    pts.append(tuple(p))
                n = [0.0, 0.0, 0.0]; n[ax] = float(s)
                faces.append(make_face(pts, tuple(n)))
        pts_all = [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        axes = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    else:
        H = (hx, hy, hz)

        def cp(sx, sy, sz, ax):  # corner point lying on the main face of axis `ax`
            s = (sx, sy, sz)
            return tuple(s[i] * (H[i] if i == ax else H[i] - b) for i in range(3))

        signs = (-1, 1)
        for ax in range(3):
            o1, o2 = [i for i in range(3) if i != ax]
            for s in signs:
                pts = []
                for a, c in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    sv = [0, 0, 0]; sv[ax] = s; sv[o1] = a; sv[o2] = c
                    pts.append(cp(*sv, ax))
                n = [0.0, 0.0, 0.0]; n[ax] = float(s)
                faces.append(make_face(pts, tuple(n)))
        # 12 edge bevels: edge parallel to axis `ax`, at signs (s1, s2) of the other two axes
        for ax in range(3):
            o1, o2 = [i for i in range(3) if i != ax]
            for s1 in signs:
                for s2 in signs:
                    pts = []
                    for e in (-1, 1):
                        sv = [0, 0, 0]; sv[ax] = e; sv[o1] = s1; sv[o2] = s2
                        pts.append(cp(*sv, o1))
                        pts.append(cp(*sv, o2))
                    pts = [pts[0], pts[1], pts[3], pts[2]]
                    n = [0.0, 0.0, 0.0]; n[o1] = s1; n[o2] = s2
                    faces.append(make_face(pts, tuple(n)))
        for sx in signs:
            for sy in signs:
                for sz in signs:
                    pts = [cp(sx, sy, sz, 0), cp(sx, sy, sz, 1), cp(sx, sy, sz, 2)]
                    faces.append(make_face(pts, (sx, sy, sz)))
        pts_all = [cp(sx, sy, sz, ax) for sx in signs for sy in signs for sz in signs for ax in range(3)]
        axes = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        axes += [norm(v) for v in ((0, 1, 1), (0, 1, -1), (1, 0, 1), (1, 0, -1), (1, 1, 0), (1, -1, 0))]
        axes += [norm(v) for v in ((1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1))]
    s = Solid(mat, faces, [Hull(pts_all, axes)], label)
    return s.xf(R or IDENT, center)


def box(mat, x0, x1, y0, y1, z0, z1, bevel=0.0, label=""):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    return cbox(mat, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), bevel, label=label)


_AXIS_FRAMES = {
    # axis: (U, V, W) - a 2D polygon (u, v) is placed at u*U + v*V, extruded along W
    "x": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    "y": ((1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "z": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
}


def _p3(U, V, W, uv, w):
    return (uv[0] * U[0] + uv[1] * V[0] + w * W[0],
            uv[0] * U[1] + uv[1] * V[1] + w * W[1],
            uv[0] * U[2] + uv[1] * V[2] + w * W[2])


def _n3(U, V, n2):
    return norm((n2[0] * U[0] + n2[1] * V[0], n2[0] * U[1] + n2[1] * V[1], n2[0] * U[2] + n2[1] * V[2]))


def prism(mat, poly, axis, w0, w1, bevel=0.0, smooth=False, cap_uv=None, label=""):
    """Extrude a 2D polygon along an axis ('x','y','z') from w0 to w1 with chamfered cap edges.
    For axis 'y' the polygon is given in (x, z); for 'x' in (y, z); for 'z' in (x, y)."""
    U, V, W = _AXIS_FRAMES[axis]
    w0, w1 = sorted((w0, w1))
    poly = ccw(poly)
    n = len(poly)
    b = min(bevel, (w1 - w0) * 0.45)
    en = edge_normals2(poly)
    inset = offset_poly(poly, -b) if b > 1e-6 else poly
    Wn = norm(W)
    mWn = mul(Wn, -1)
    faces = []
    convex = is_convex(poly)
    tris = None if convex else ear_clip(poly)
    for wc, wn, capw in ((w1, Wn, w1), (w0, mWn, w0)):
        if convex:
            pts = [_p3(U, V, W, q, capw) for q in inset]
            faces.append(make_face(pts, wn, uv=None if cap_uv is None else cap_uv(inset)))
        else:
            for t in tris:
                pts = [_p3(U, V, W, inset[k], capw) for k in t]
                faces.append(make_face(pts, wn))
    for i in range(n):
        j = (i + 1) % n
        nn = _n3(U, V, en[i])
        a0, a1 = w0 + b, w1 - b
        pts = [_p3(U, V, W, poly[i], a0), _p3(U, V, W, poly[j], a0), _p3(U, V, W, poly[j], a1), _p3(U, V, W, poly[i], a1)]
        if smooth:
            ni = _n3(U, V, norm((en[i - 1][0] + en[i][0], en[i - 1][1] + en[i][1], 0)))
            nj = _n3(U, V, norm((en[i][0] + en[(i + 1) % n][0], en[i][1] + en[(i + 1) % n][1], 0)))
            faces.append(make_face(pts, nn, vnormals=[ni, nj, nj, ni]))
        else:
            faces.append(make_face(pts, nn))
        if b > 1e-6:
            for edge_w, cap_w, wn in ((w1 - b, w1, Wn), (w0 + b, w0, mWn)):
                pts = [_p3(U, V, W, poly[i], edge_w), _p3(U, V, W, poly[j], edge_w),
                       _p3(U, V, W, inset[j], cap_w), _p3(U, V, W, inset[i], cap_w)]
                faces.append(make_face(pts, add(nn, wn)))
    hulls = []
    if convex:
        pts = [_p3(U, V, W, q, w) for q in poly for w in (w0, w1)]
        axes = [Wn] + [_n3(U, V, e) for e in en]
        if b > 1e-6:
            axes += [norm(add(_n3(U, V, e), Wn)) for e in en] + [norm(add(_n3(U, V, e), mWn)) for e in en]
        hulls.append(Hull(pts, axes))
    else:
        for t in tris:
            tp = [poly[k] for k in t]
            pts = [_p3(U, V, W, q, w) for q in tp for w in (w0, w1)]
            axes = [Wn] + [_n3(U, V, e) for e in edge_normals2(ccw(tp))]
            hulls.append(Hull(pts, axes))
    return Solid(mat, faces, hulls, label)


def frame(mat, outer, inner, axis, w0, w1, bevel=0.0, smooth=False, label=""):
    """Ring between an outer and an inner polygon (same vertex count, corresponding vertices),
    extruded along an axis. Real opening: the inner walls face into the hole."""
    U, V, W = _AXIS_FRAMES[axis]
    w0, w1 = sorted((w0, w1))
    if poly_area2(outer) < 0:
        outer = list(reversed(outer)); inner = list(reversed(inner))
    if len(outer) != len(inner):
        if len(outer) == 4 and len(inner) == 8:
            outer = chamfer_poly(outer, 0.25)
        elif len(inner) == 4 and len(outer) == 8:
            inner = chamfer_poly(inner, 0.2)
        else:
            raise ValueError("frame(): outer/inner vertex counts differ")
    if poly_area2(inner) < 0:
        raise ValueError("frame(): inner polygon winding differs from outer")
    n = len(outer)
    b = min(bevel, (w1 - w0) * 0.45)
    eo, ei = edge_normals2(outer), edge_normals2(inner)
    oi = offset_poly(outer, -b) if b > 1e-6 else outer
    ii = offset_poly(inner, b) if b > 1e-6 else inner
    Wn = norm(W); mWn = mul(Wn, -1)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        for capw, wn in ((w1, Wn), (w0, mWn)):
            pts = [_p3(U, V, W, oi[i], capw), _p3(U, V, W, oi[j], capw), _p3(U, V, W, ii[j], capw), _p3(U, V, W, ii[i], capw)]
            faces.append(make_face(pts, wn))
        a0, a1 = w0 + b, w1 - b
        for poly, e, sgn in ((outer, eo, 1.0), (inner, ei, -1.0)):
            nn = mul(_n3(U, V, e[i]), sgn)
            pts = [_p3(U, V, W, poly[i], a0), _p3(U, V, W, poly[j], a0), _p3(U, V, W, poly[j], a1), _p3(U, V, W, poly[i], a1)]
            if smooth:
                ni = mul(_n3(U, V, norm((e[i - 1][0] + e[i][0], e[i - 1][1] + e[i][1], 0))), sgn)
                nj = mul(_n3(U, V, norm((e[i][0] + e[j][0], e[i][1] + e[j][1], 0))), sgn)
                faces.append(make_face(pts, nn, vnormals=[ni, nj, nj, ni]))
            else:
                faces.append(make_face(pts, nn))
        if b > 1e-6:
            for edge_w, cap_w, wn in ((w1 - b, w1, Wn), (w0 + b, w0, mWn)):
                for poly, ins, e, sgn in ((outer, oi, eo, 1.0), (inner, ii, ei, -1.0)):
                    pts = [_p3(U, V, W, poly[i], edge_w), _p3(U, V, W, poly[j], edge_w),
                           _p3(U, V, W, ins[j], cap_w), _p3(U, V, W, ins[i], cap_w)]
                    faces.append(make_face(pts, add(mul(_n3(U, V, e[i]), sgn), wn)))
    hulls = []
    for i in range(n):
        j = (i + 1) % n
        quad = ccw([outer[i], outer[j], inner[j], inner[i]])
        pts = [_p3(U, V, W, q, w) for q in quad for w in (w0, w1)]
        axes = [Wn] + [_n3(U, V, e) for e in edge_normals2(quad)]
        hulls.append(Hull(pts, axes))
    return Solid(mat, faces, hulls, label)


def cyl(mat, center, r, length_, axis="z", sides=16, bevel=0.0, label=""):
    U, V, W = _AXIS_FRAMES[axis]
    cu = dot(center, U); cv = dot(center, V); cw = dot(center, W)
    return prism(mat, circle(r, sides, cu, cv), axis, cw - length_ / 2, cw + length_ / 2, bevel, smooth=True, label=label)


def tube(mat, center, r_out, r_in, length_, axis="z", sides=24, bevel=0.0, label=""):
    U, V, W = _AXIS_FRAMES[axis]
    cu = dot(center, U); cv = dot(center, V); cw = dot(center, W)
    return frame(mat, circle(r_out, sides, cu, cv), circle(r_in, sides, cu, cv), axis,
                 cw - length_ / 2, cw + length_ / 2, bevel, smooth=True, label=label)


def torus(mat, center, R, r, axis="z", seg=32, sides=10, label=""):
    U, V, W = _AXIS_FRAMES[axis]
    faces, hulls = [], []
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        d = add(mul(U, math.cos(a)), mul(V, math.sin(a)))
        ring = []
        for k in range(sides):
            bta = 2 * math.pi * k / sides
            nrm = add(mul(d, math.cos(bta)), mul(W, math.sin(bta)))
            ring.append((add(center, add(mul(d, R), mul(nrm, r))), nrm))
        rings.append(ring)
    for i in range(seg):
        r0, r1 = rings[i], rings[(i + 1) % seg]
        for k in range(sides):
            k1 = (k + 1) % sides
            pts = [r0[k][0], r1[k][0], r1[k1][0], r0[k1][0]]
            nr = [r0[k][1], r1[k][1], r1[k1][1], r0[k1][1]]
            want = norm(add(add(nr[0], nr[1]), add(nr[2], nr[3])))
            faces.append(make_face(pts, want, vnormals=nr))
        pts = [p for p, _ in r0] + [p for p, _ in r1]
        axes = [W, norm(sub(rings[(i + 1) % seg][0][0], rings[i][0][0]))]
        a = 2 * math.pi * (i + 0.5) / seg
        axes.append(add(mul(U, math.cos(a)), mul(V, math.sin(a))))
        hulls.append(Hull(pts, axes))
    return Solid(mat, faces, hulls, label)


def display_plate(mat, center, size, R=None, label="display"):
    """Thin plate whose local +Z face carries a 0..1 UV rectangle (u right, v down)."""
    s = cbox(mat, (0, 0, 0), size, 0.0)
    hx, hy = size[0] / 2.0, size[1] / 2.0
    for f in s.faces:
        if f.nrm[0][2] > 0.99:
            f.uv = [((p[0] + hx) / (2 * hx), 1.0 - (p[1] + hy) / (2 * hy)) for p in f.pts]
    return s.xf(R or IDENT, center)


# ------------------------------------------------------------------------------------------ surfaces
class Surface:
    """A local placement frame on a face: u = viewer's right, v = up the face, n = out of the face.
    Placing things with Surface keeps every attached part flush with its mount (touching, never
    intersecting): a part placed at heights [h0, h1] occupies n in [h0, h1] above the face."""

    def __init__(self, origin, u, v, n):
        self.o = tuple(origin)
        self.u, self.v, self.n = norm(u), norm(v), norm(n)
        self.R = mat_cols(self.u, self.v, self.n)

    def at(self, u, v, h=0.0):
        return add(self.o, add(mul(self.u, u), add(mul(self.v, v), mul(self.n, h))))

    def sub(self, u, v, h=0.0):
        """A parallel surface translated within / above this one."""
        return Surface(self.at(u, v, h), self.u, self.v, self.n)

    def tilt(self, deg_about_u):
        """Rotate the frame about its u axis (v leans toward n for positive angles)."""
        c, sn = math.cos(math.radians(deg_about_u)), math.sin(math.radians(deg_about_u))
        return Surface(self.o, self.u, add(mul(self.v, c), mul(self.n, sn)), sub(mul(self.n, c), mul(self.v, sn)))

    def turn(self, deg_about_v):
        """Rotate the frame about its v axis (u leans toward n for positive angles)."""
        c, sn = math.cos(math.radians(deg_about_v)), math.sin(math.radians(deg_about_v))
        return Surface(self.o, add(mul(self.u, c), mul(self.n, sn)), self.v, sub(mul(self.n, c), mul(self.u, sn)))

    def box(self, mat, u0, u1, v0, v1, h0, h1, bevel=0.0, label=""):
        u0, u1 = sorted((u0, u1)); v0, v1 = sorted((v0, v1)); h0, h1 = sorted((h0, h1))
        c = self.at((u0 + u1) / 2, (v0 + v1) / 2, (h0 + h1) / 2)
        return cbox(mat, c, (u1 - u0, v1 - v0, h1 - h0), bevel, self.R, label)

    def prism(self, mat, poly, h0, h1, bevel=0.0, smooth=False, label=""):
        return prism(mat, poly, "z", h0, h1, bevel, smooth, label=label).xf(self.R, self.o)

    def frame(self, mat, outer, inner, h0, h1, bevel=0.0, label=""):
        return frame(mat, outer, inner, "z", h0, h1, bevel, label=label).xf(self.R, self.o)

    def cyl(self, mat, u, v, r, h0, h1, sides=16, bevel=0.0, label=""):
        return prism(mat, circle(r, sides, u, v), "z", h0, h1, bevel, smooth=True, label=label).xf(self.R, self.o)

    def tube(self, mat, u, v, r_out, r_in, h0, h1, sides=24, bevel=0.0, label=""):
        return frame(mat, circle(r_out, sides, u, v), circle(r_in, sides, u, v), "z", h0, h1, bevel,
                     smooth=True, label=label).xf(self.R, self.o)

    def display(self, mat, u0, u1, v0, v1, h0, h1, label="display"):
        c = self.at((u0 + u1) / 2, (v0 + v1) / 2, (h0 + h1) / 2)
        return display_plate(mat, c, (u1 - u0, v1 - v0, h1 - h0), self.R, label)


def face_surface(side, plane, cu=0.0, cv=0.0):
    """Surface on an axis-aligned face. side in {'+x','-x','+y','-y','+z','-z'}; `plane` is the face's
    coordinate on that axis; (cu, cv) is the origin within the face. u is the viewer's right when
    looking AT the face, v is up (for +-z faces v points to +x/-x... see table)."""
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    if side == "+x":   # viewer looks toward -X; their right is -Y
        return Surface((plane, -cu, cv), (0, -1, 0), Z, X)
    if side == "-x":   # rear face: viewer looks toward +X; right is +Y
        return Surface((plane, cu, cv), Y, Z, (-1, 0, 0))
    if side == "+y":   # viewer looks toward -Y; right is +X
        return Surface((cu, plane, cv), X, Z, Y)
    if side == "-y":   # viewer looks toward +Y; right is -X
        return Surface((-cu, plane, cv), (-1, 0, 0), Z, (0, -1, 0))
    if side == "+z":   # top: u = -Y (operator's right when standing at +X), v = -X (away from operator)
        return Surface((-cv, -cu, plane), (0, -1, 0), (-1, 0, 0), Z)
    if side == "-z":   # underside: u = -Y, v = +X
        return Surface((cv, -cu, plane), (0, -1, 0), X, (0, 0, -1))
    raise ValueError(side)


# ------------------------------------------------------------------------------------------ hierarchy
class Node:
    """A named glTF node. `pivot` is in asset space (cm); geometry stays in asset space while
    authoring and is re-expressed relative to the pivot at export."""

    def __init__(self, name, pivot=(0.0, 0.0, 0.0), role="static", motion=None, note=""):
        self.name = name
        self.pivot = tuple(pivot)
        self.role = role            # static | movable | interactive | emissive | display | socket | group
        self.motion = motion        # dict describing the rest-pose motion (see specs)
        self.note = note
        self.solids: list[Solid] = []
        self.children: list[Node] = []

    def add(self, *items):
        for it in items:
            if isinstance(it, (list, tuple)):
                self.add(*it)
            elif it is not None:
                self.solids.append(it)
        return self

    def child(self, name, pivot=None, role="static", motion=None, note=""):
        n = Node(name, self.pivot if pivot is None else pivot, role, motion, note)
        self.children.append(n)
        return n

    def socket(self, name, pos, note=""):
        n = Node(name, pos, "socket", None, note)
        self.children.append(n)
        return n

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def all_solids(self):
        for n in self.walk():
            for s in n.solids:
                yield n, s


def mirror_y(solids):
    """Mirror solids across the XZ plane (y -> -y). Winding is re-oriented."""
    out = []
    for s in solids if isinstance(solids, (list, tuple)) else [solids]:
        faces = []
        for f in s.faces:
            pts = [(p[0], -p[1], p[2]) for p in f.pts]
            nr = [(n[0], -n[1], n[2]) for n in f.nrm]
            faces.append(Face(list(reversed(pts)), list(reversed(nr)), list(reversed(f.uv)) if f.uv else None, f.mat))
        hulls = [Hull([(p[0], -p[1], p[2]) for p in h.pts], [(a[0], -a[1], a[2]) for a in h.axes]) for h in s.hulls]
        out.append(Solid(s.mat, faces, hulls, s.label))
    return out


def surface_turn(S: Surface, deg_about_v):
    return S.turn(deg_about_v)


def side_surface(S: Surface):
    """Frame whose (u, v) plane is S's (u, n) plane and whose extrusion axis is S.v - use it to
    extrude profiles drawn in (u, n) along v (wedges, ribs)."""
    return Surface(S.o, S.u, S.n, mul(S.v, -1))


def split_by_mats(solids, mats):
    a, b = [], []
    for s in solids:
        (b if s.mat in mats else a).append(s)
    return a, b


def mirror(solids, ax):
    """Mirror solids across the plane coordinate[ax] = 0 (ax: 0 = x, 1 = y, 2 = z)."""
    def m(p):
        q = list(p); q[ax] = -q[ax]; return tuple(q)
    out = []
    for s in solids if isinstance(solids, (list, tuple)) else [solids]:
        faces = [Face([m(p) for p in reversed(f.pts)], [m(n) for n in reversed(f.nrm)],
                      list(reversed(f.uv)) if f.uv else None, f.mat) for f in s.faces]
        hulls = [Hull([m(p) for p in h.pts], [m(a) for a in h.axes]) for h in s.hulls]
        out.append(Solid(s.mat, faces, hulls, s.label))
    return out


def quad_mirror(solids):
    """Copy solids authored for the (+x, +y) quadrant into all four quadrants."""
    a = list(solids)
    b = a + mirror(a, 1)
    return b + mirror(b, 0)
