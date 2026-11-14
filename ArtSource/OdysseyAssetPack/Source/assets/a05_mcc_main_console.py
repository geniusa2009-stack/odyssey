"""05 OD_MCC_MainConsole - Mission Control main operator console (references 05 / 05B).

Envelope W 4.80 (Y) x H 1.30 (Z) x D 1.60 (X), pivot bottom-centre (floor). Front (+X) = operators.
Three-segment arc: a straight centre segment (1.60 m) and two wings angled toward the operators,
joined by white wedge pillars with ion strips. Every segment: plinth, lower body with vented front,
seated-height sloped desk (0.74 m) with control modules and a desk display, reclined display hood
with two displays. Centre segment adds the e-stop, three mode levers and the header block.
The wing angle and length are solved so the assembly fills the envelope exactly.
"""
import math

from od_core import (Node, box, prism, Surface, face_surface, split_by_mats, norm, mat_cols, add, mul, Solid,
                     Face, Hull, mat_vec)
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, AMBER, RED, HAZARD, EMISSIVE
from od_kit import (strip, vent, screws, corner_screws, screen, button, knob, toggle, fader_slot, hazard_plate,
                    led_row, chevrons)
from od_asset import Asset

NAME = "OD_MCC_MainConsole"
DESK = [(0, 62), (41, 62), (45, 65.5), (45, 71), (43, 74), (0, 84)]
HOOD = [(-40.8, 62), (0, 62), (0, 84), (-7, 124), (-10, 127.5), (-38.8, 127.5), (-40.8, 125.5)]
CW = 80.0                    # centre half-width


def segment(ya, yb, kind):
    """Solids of one console segment between y = ya..yb in segment-local space. Returns {node: [solids]}."""
    out = {"Body": [], "Lights": [], "Screens": [], "Caps": [], "Nodes": []}
    B, Lt = out["Body"], out["Lights"]

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); Lt.extend(e)

    w = yb - ya
    B.append(box(GRAPHITE, -36, 30, ya + 3, yb - 3, 0, 7, bevel=0.8, label="plinth"))
    B.append(box(GRAPHITE, -38, 22, ya, yb, 7, 62, label="lower_core"))
    Sf = face_surface("+x", 22)                        # u = -Y
    u0, u1 = -yb + 2, -ya - 2
    B.append(Sf.box(WHITE, u0, u1, 9, 60, 0, 3, bevel=0.8, label="front_skin"))
    Fs = Sf.sub(0, 0, 3)
    n = 2 if w < 150 else 3
    step = (u1 - u0) / n
    for i in range(n):
        a, b = u0 + step * i + 5, u0 + step * (i + 1) - 5
        B.extend(vent(Fs, a, b, 14, 40, depth=1.2, chamfer=2.0, pitch=2.2))
        put(strip(Fs, a + 4, b - 4, 47.4, 48.6, ION))
    put(strip(Fs, u0 + 3, u0 + 4.2, 14, 54, ION) + strip(Fs, u1 - 4.2, u1 - 3, 14, 54, ION))
    B.extend(corner_screws(Fs, u0, u1, 9, 60, inset=2.2))
    # rear: vented panels
    Sr = face_surface("-x", -38)                       # u = +Y
    B.append(Sr.box(WHITE, ya + 2, yb - 2, 9, 60, 0, 2.8, bevel=0.6, label="rear_skin"))
    Rs = Sr.sub(0, 0, 2.8)
    for i in range(n):
        a, b = ya + 2 + (w - 4) / n * i + 6, ya + 2 + (w - 4) / n * (i + 1) - 6
        B.extend(vent(Rs, a, b, 22, 50, depth=0.0 + 1.0, chamfer=2.0, pitch=2.4))
    # desk
    B.append(prism(WHITE, DESK, "y", ya, yb, bevel=1.0, label="desk"))
    t = norm((-43, 0, 10)); nn = norm((10, 0, 43))
    D = Surface((43, -0.0, 74), (0, -1, 0), t, nn)     # u = -Y
    Dm = D.sub(0, 0, 0.8)
    mods = []
    m_n = 2 if w < 150 else 3
    du = (u1 - u0 - 4) / m_n
    for i in range(m_n):
        a, b = u0 + 2 + du * i + 1.5, u0 + 2 + du * (i + 1) - 1.5
        B.append(D.box(GRAPHITE, a, b, 5, 37, 0, 0.8, bevel=0.3, label="desk_module"))
        mods.append((a, b))
    for i, (a, b) in enumerate(mods):
        c = (a + b) / 2
        role = kind[i] if i < len(kind) else "buttons"
        if role == "display":
            bz, dp = screen(Dm, a + 3, b - 3, 14, 34, bezel=1.4, depth=1.0, chamfer=1.4)
            B.extend(bz); out["Screens"].append(("DeskDisplay", dp))
            for k in range(4):
                bb = button(Dm, a + 6 + k * (b - a - 12) / 3, 9, 3.0, 2.2, cap=ION if k else AMBER)
                B.append(bb[0]); out["Caps"].append(bb[1])
        elif role == "estop":
            B.extend(hazard_plate(Dm, c - 11, c + 11, 13, 35, width=2.2))
            Dh = Dm.sub(0, 0, 0.62)
            B.append(Dh.cyl(GUNMETAL, c, 24, 4.6, 0, 1.4, sides=28, bevel=0.3, label="estop_collar"))
            out["Nodes"].append(("Control_EStop", Dh.at(c, 24, 1.4),
                                 {"type": "slide", "dir_ue": [round(-x, 4) for x in Dh.n], "range_cm": [0, 0.8]},
                                 [Dh.cyl(RED, c, 24, 1.6, 1.4, 2.6, sides=16, label="estop_stem"),
                                  Dh.cyl(RED, c, 24, 3.8, 2.6, 4.8, sides=32, bevel=0.7, label="estop_cap")]))
            for k in range(3):
                bb = button(Dm, c - 8 + 8 * k, 8, 3.0, 2.0, cap=RED if k == 1 else AMBER)
                B.append(bb[0]); out["Caps"].append(bb[1])
        elif role == "levers":
            for k in range(3):
                st, cap = fader_slot(Dm, c - 10 + 10 * k, 22, 20)
                B.extend(st)
                out["Nodes"].append((f"Control_ModeLever_{k + 1:02d}", Dm.at(c - 10 + 10 * k, 22, 0.2),
                                     {"type": "slide", "dir_ue": [round(x, 4) for x in Dm.v], "range_cm": [-8.8, 8.8]}, cap))
            Lt.extend(led_row(Dm, c - 12, 35, 9, 3.0, mat=ION))
        else:   # buttons + knob
            kp = knob(Dm, a + 7, 24, 2.6)
            Lt.append(kp[0])
            out["Nodes"].append(("Control_Knob", Dm.at(a + 7, 24, 0), {"type": "rotate", "axis_ue": [round(x, 4) for x in Dm.n],
                                                                      "range_deg": [-135, 135]}, kp[1:]))
            cols = max(2, int((b - a - 18) // 5.5))
            for r, v in enumerate((30, 22, 14)):
                for k in range(cols):
                    bb = button(Dm, a + 15 + k * 5.5, v, 3.4, 2.4, cap=(AMBER if (r == 1 and k == 0) else ION))
                    B.append(bb[0]); out["Caps"].append(bb[1])
            Lt.extend(led_row(Dm, a + 4, 9, 4, 2.6, mat=AMBER))
    # hood + displays
    B.append(prism(WHITE, HOOD, "y", ya, yb, bevel=1.2, label="display_hood"))
    tf = norm((-7, 0, 40)); nf = norm((40, 0, 7))
    F = Surface((0, 0, 84), (0, -1, 0), tf, nf)
    hu0, hu1 = -yb + 3, -ya - 3
    ns = 2
    dv = (hu1 - hu0) / ns
    for i in range(ns):
        a, b = hu0 + dv * i + 1.5, hu0 + dv * (i + 1) - 1.5
        bz, dp = screen(F, a, b, 3, 36, bezel=2.2, depth=1.6, chamfer=2.2)
        B.extend(bz); out["Screens"].append((f"Display_{'AB'[i]}", dp))
    put(strip(F, hu0 + 6, hu1 - 6, 37.6, 38.6, ION, margin=0.3))
    Shr = face_surface("-x", -40.8)
    B.extend(vent(Shr, ya + 10, yb - 10, 92, 116, depth=1.2, chamfer=2.0, pitch=2.4))
    return out


def _transform(solids, R, t):
    return [s.xf(R, t) for s in solids]


def _wing_frame(theta, side):
    """Rotation and translation for a wing hinged at the centre segment's front corner."""
    c, s = math.cos(theta), math.sin(theta)
    f = (c, -side * s, 0.0)                  # wing local +X
    # local +Y maps to (side*s, c): for the left wing (+Y) that is the outward direction; the right
    # wing is authored with local y in [-wl, 0], so its outward side is local -Y
    R = mat_cols(f, (side * s, c, 0.0), (0.0, 0.0, 1.0))
    J = (45.0, side * CW, 0.0)
    t = (J[0] - mat_vec(R, (45.0, 0.0, 0.0))[0], J[1] - mat_vec(R, (45.0, 0.0, 0.0))[1], 0.0)
    return R, t, f


def _hull2d(pts):
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in pts))
    if len(pts) < 3:
        return pts

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _all_solids(seg):
    out = list(seg["Body"]) + list(seg["Lights"]) + list(seg["Caps"])
    for _, dp in seg["Screens"]:
        out += dp
    for _, _, _, parts in seg["Nodes"]:
        out += parts
    return out


def solve_arc():
    """Find wing length wl and angle theta so that x-range = 160 and y-max = 240 exactly."""
    def wing_hull(wl):
        seg = segment(0.0, wl, ["display", "buttons"])
        return _hull2d([p for s in _all_solids(seg) for f in s.faces for p in f.pts])

    cen = segment(-CW, CW, ["buttons", "levers", "estop"])
    cx = [p[0] for s in _all_solids(cen) for f in s.faces for p in f.pts]
    cmin, cmax = min(cx), max(cx)

    def bounds(hull, theta):
        R, t, _ = _wing_frame(theta, 1)
        xs, ys = [], []
        for (x, y) in hull:
            q = mat_vec(R, (x, y, 0.0))
            xs.append(q[0] + t[0]); ys.append(q[1] + t[1])
        return min(min(xs), cmin), max(max(xs), cmax), max(ys)

    lo_w, hi_w = 100.0, 170.0
    best = None
    for _ in range(18):
        wl = (lo_w + hi_w) / 2
        hull = wing_hull(wl)
        lo_t, hi_t = math.radians(10), math.radians(60)
        for _ in range(40):
            th = (lo_t + hi_t) / 2
            xmin, xmax, ymax = bounds(hull, th)
            if xmax - xmin < 160.0:
                lo_t = th
            else:
                hi_t = th
        th = (lo_t + hi_t) / 2
        xmin, xmax, ymax = bounds(hull, th)
        best = (wl, th, xmin, xmax, ymax)
        if ymax < 240.0:
            lo_w = wl
        else:
            hi_w = wl
    return best


def build():
    wl, th, xmin, xmax, ymax = solve_arc()
    shift = -(xmin + xmax) / 2.0
    root = Node(NAME, (0, 0, 0), "group")
    lights = root.child("StatusLights", role="emissive", note="Ion strips / LEDs of all segments")
    controls = root.child("Controls", role="group", note="Desk controls of all segments")
    LALL = []

    def place(seg, tag, R, t):
        t2 = (t[0] + shift, t[1], t[2])
        body = root.child(f"Body_{tag}", role="static", note=f"{tag} segment shell, desk, hood, modules")
        body.add(_transform(seg["Body"], R, t2))
        LALL.extend(_transform(seg["Lights"], R, t2))
        for nm, dp in seg["Screens"]:
            root.child(f"{nm}_{tag}", role="display", note="0..1 UV on OD_MAT_Display").add(_transform(dp, R, t2))
        controls.child(f"Control_Buttons_{tag}", role="interactive",
                       motion={"type": "press", "dir_ue": [0, 0, -1], "range_cm": [0, 0.3]},
                       note="Momentary button caps").add(_transform(seg["Caps"], R, t2))
        for nm, piv, mo, parts in seg["Nodes"]:
            p = mat_vec(R, piv)
            mo = dict(mo)
            for key in ("dir_ue", "axis_ue"):
                if key in mo:
                    mo[key] = [round(c, 4) for c in mat_vec(R, tuple(mo[key]))]
            a, e = split_by_mats(_transform(parts, R, t2), EMISSIVE)
            controls.child(f"{nm}_{tag}", pivot=(p[0] + t2[0], p[1] + t2[1], p[2] + t2[2]), role="interactive",
                           motion=mo).add(a, e)

    place(segment(-CW, CW, ["buttons", "levers", "estop"]), "Centre", ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0, 0, 0))
    for side, tag in ((1, "WingL"), (-1, "WingR")):
        R, t, f = _wing_frame(th, side)
        ya, yb = (0.0, wl) if side > 0 else (-wl, 0.0)
        kinds = ["display", "buttons"] if side > 0 else ["buttons", "display"]
        place(segment(ya, yb, kinds), tag, R, t)
        # wedge pillar closing the gap between centre and wing (rear opens by theta)
        J = (45.0 + shift, side * CW)
        Rc = (-38.0 + shift, side * CW)
        Rw = (45.0 + shift - 83.0 * f[0], side * CW - 83.0 * f[1])
        poly = [J, Rc, Rw]
        wedge = prism(WHITE, poly, "z", 7, 62, bevel=0.8, label="joint_wedge_lower")
        hood_rear_c = (-40.8 + shift, side * CW)
        Rw2 = (45.0 + shift - 85.8 * f[0], side * CW - 85.8 * f[1])
        J2 = (0.0 + shift, side * CW)
        Jw2 = (45.0 + shift - 45.0 * f[0], side * CW - 45.0 * f[1])
        hood_wedge = prism(GUNMETAL, [J2, hood_rear_c, Rw2, Jw2], "z", 62, 120, bevel=0.8, label="joint_pillar")
        jp = root.child(f"Joint_{tag}", role="static", note="Wedge joint between centre and wing")
        jp.add(wedge, hood_wedge)
    # header block on the centre hood
    hb = root.child("HeaderBlock", role="static", note="ODYSSEY Mission Control header block")
    Top = face_surface("+z", 127.5)
    hb.add(Top.box(GUNMETAL, -40, 40, 12 - shift, 34 - shift, 0, 2.5, bevel=0.6, label="header_block"))
    lights.add(LALL)
    root.socket("SOCKET_Operator_Centre", (110.0, 0.0, 0.0), "Centre operator position (chair)")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot")
    return Asset(
        name=NAME, title="Mission Control Main Console", reference="05_Mission_Control_Main_Console.png, 05B_Mission_Control_Reference_Sheet.png",
        envelope=(480, 130, 160), pivot="floor", pivot_text="bottom-centre of the envelope (floor contact)",
        root=root,
        description=("Three-segment mission control console: straight 1.60 m centre segment with e-stop, three mode "
                     f"levers and button bank, plus two {wl / 100:.2f} m wings angled {math.degrees(th):.1f} deg toward "
                     "the operators, joined by wedge pillars. Each segment has a vented front with ion strips, a sloped "
                     "seated-height desk with control modules (wings: desk display + buttons), and a reclined hood with "
                     "two displays and a header strip; header block on the centre hood."),
        collision="Custom: per segment one box for the lower body+desk and one for the hood (6 UCX) + 2 wedge hulls.",
        nanite="Body segments Nanite ON; displays and controls separate (render targets / interaction).",
        interaction=[("Displays", "Display_A_Centre", "Six hood displays + two desk displays (render targets)"),
                     ("Emergency stop", "Control_EStop_Centre", "Centre desk"),
                     ("Mode levers", "Control_ModeLever_01_Centre", "Normal / Test / Override"),
                     ("Operator", "SOCKET_Operator_Centre", "Chair positions in front of each segment")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing arc; the 8.6 m room-scale ring of the 05B sheet is built from this unit plus wall displays")],
        notes=[f"Solved wing length {wl:.2f} cm and angle {math.degrees(th):.3f} deg so the arc fills 4.80 x 1.60 m exactly.",
               "05B sheet shows the full 8.6 x 3.2 m command ring; the contract unit is this 4.80 x 1.30 x 1.60 m console."],
    )
