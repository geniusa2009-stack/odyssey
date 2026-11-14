"""ODYSSEY Asset Pack - authoring-side checks on convex hulls (cm, Unreal axes).

* intersections: two solids whose convex hulls interpenetrate by more than TOL (separating-axis test
  over the face normals of both hulls)
* connectivity: every solid must touch (gap <= TOL) another solid so the asset is one connected
  assembly in its rest pose - no floating parts
* envelope: the assembled bounds equal the documented mounting envelope on all six sides
"""
from __future__ import annotations

TOL = 0.1  # cm (1 mm): contact tolerance; interpenetration deeper than this fails


def _proj(pts, a):
    lo = hi = pts[0][0] * a[0] + pts[0][1] * a[1] + pts[0][2] * a[2]
    for p in pts[1:]:
        d = p[0] * a[0] + p[1] * a[1] + p[2] * a[2]
        if d < lo:
            lo = d
        elif d > hi:
            hi = d
    return lo, hi


def hull_relation(h1, h2):
    """Return (max_gap, min_penetration) over the candidate axes."""
    max_gap = -1e18
    min_pen = 1e18
    for a in h1.axes + h2.axes:
        l1, u1 = _proj(h1.pts, a)
        l2, u2 = _proj(h2.pts, a)
        gap = max(l2 - u1, l1 - u2)
        if gap > max_gap:
            max_gap = gap
        pen = min(u1 - l2, u2 - l1)
        if pen < min_pen:
            min_pen = pen
        if max_gap > TOL:
            break
    return max_gap, min_pen


def _aabb(pts):
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def check_assembly(root, allow_pairs=()):
    """Returns dict with intersections, floating components, counts."""
    items = []  # (node name, solid, hull, aabb)
    for node, s in root.all_solids():
        for h in s.hulls:
            items.append((node.name, s, h, _aabb(h.pts)))
    solids = []
    sid = {}
    for node, s in root.all_solids():
        sid[id(s)] = len(solids)
        solids.append((node.name, s))
    parent = list(range(len(solids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # hulls of the same solid are connected by construction
    order = sorted(range(len(items)), key=lambda k: items[k][3][0][0])
    inter = []
    allow = {frozenset(p) for p in allow_pairs}
    for oi, a in enumerate(order):
        na, sa, ha, (loa, hia) = items[a]
        for b in order[oi + 1:]:
            nb, sb, hb, (lob, hib) = items[b]
            if lob[0] > hia[0] + TOL:
                break
            if sa is sb:
                continue
            if lob[1] > hia[1] + TOL or loa[1] > hib[1] + TOL or lob[2] > hia[2] + TOL or loa[2] > hib[2] + TOL:
                continue
            gap, pen = hull_relation(ha, hb)
            if gap <= TOL:
                union(sid[id(sa)], sid[id(sb)])
                if pen > TOL and gap < -TOL:
                    key = frozenset((sa.label or sa.mat, sb.label or sb.mat))
                    if key not in allow:
                        inter.append((na, sa.label or sa.mat, nb, sb.label or sb.mat, round(pen, 3)))
    comps = {}
    for i in range(len(solids)):
        comps.setdefault(find(i), []).append(i)
    groups = sorted(comps.values(), key=len, reverse=True)
    floating = []
    for g in groups[1:]:
        floating.append([f"{solids[i][0]}:{solids[i][1].label or solids[i][1].mat}" for i in g][:6])
    return {"solids": len(solids), "hulls": len(items), "intersections": inter, "floating_groups": floating,
            "components": len(groups)}


def assembly_bounds(root):
    lo = [1e18] * 3
    hi = [-1e18] * 3
    for _, s in root.all_solids():
        l, h = s.bounds()
        for i in range(3):
            lo[i] = min(lo[i], l[i]); hi[i] = max(hi[i], h[i])
    return lo, hi


def expected_bounds(envelope, pivot):
    """envelope = (W, H, D) in cm; returns ((xmin,ymin,zmin),(xmax,ymax,zmax)) per the mounting contract."""
    W, H, D = envelope
    if pivot == "floor":       # bottom-centre
        return (-D / 2, -W / 2, 0), (D / 2, W / 2, H)
    if pivot == "wall_base":   # bottom-centre of the rear face
        return (0, -W / 2, 0), (D, W / 2, H)
    if pivot == "wall":        # centre of the rear face
        return (0, -W / 2, -H / 2), (D, W / 2, H / 2)
    if pivot == "ceiling":     # top-centre; for the ceiling light D = length along X
        return (-D / 2, -W / 2, -H), (D / 2, W / 2, 0)
    raise ValueError(pivot)


def envelope_problems(lo, hi, envelope, pivot, tol=0.05):
    elo, ehi = expected_bounds(envelope, pivot)
    out = []
    for i, ax in enumerate("XYZ"):
        if abs(lo[i] - elo[i]) > tol:
            out.append(f"{ax} min {lo[i]:.2f} != {elo[i]:.2f}")
        if abs(hi[i] - ehi[i]) > tol:
            out.append(f"{ax} max {hi[i]:.2f} != {ehi[i]:.2f}")
    return out
