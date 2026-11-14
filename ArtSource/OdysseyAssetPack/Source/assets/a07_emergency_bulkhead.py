"""07 OD_ENV_EmergencyBulkhead - emergency pressure bulkhead door (reference 07_Bulkhead_Emergency_Door.png).

Envelope W 2.40 (Y) x H 2.60 (Z) x D 0.45 (X), pivot bottom-centre of the opening (floor, centred in the
wall). Heavy chamfered portal (0.32 m deep) with hazard-striped jambs, red rotating-beacon housings,
header alarm bar, status/override panel; two 0.12 m pressure leaves hinged on the jambs, swinging out
toward +X. Leaf_L is the active leaf: it carries the manual handwheel (centred on the meeting seam,
overlapping Leaf_R like an astragal) and the locking mechanism, so it opens first.
"""
from od_core import Node, box, prism, rect, face_surface, split_by_mats, cyl, torus, Surface, mirror
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, AMBER, RED, HAZARD, EMISSIVE
from od_kit import strip, vent, screws, screen, button, hazard_plate, led_row, corner_screws
from od_asset import Asset

NAME = "OD_ENV_EmergencyBulkhead"
U_FRAME = [(-120, 0), (-96, 0), (-96, 212), (-80, 228), (80, 228), (96, 212), (96, 0), (120, 0), (120, 230),
           (90, 260), (-90, 260), (-120, 230)]
LEAF = [(0.4, 1.0), (95.7, 1.0), (95.7, 212.0), (79.9, 227.7), (0.4, 227.7)]   # (y, z) of the +Y leaf


def build():
    root = Node(NAME, (0, 0, 0), "group")
    frame_n = root.child("Frame", role="static", note="Portal, threshold, hazard jambs, hinges, keepers")
    F = [prism(WHITE, U_FRAME, "x", -16, 16, bevel=1.2, label="portal"),
         box(GUNMETAL, -16, 16, -96, 96, 0, 1.0, label="threshold")]
    Th = face_surface("+z", 1.0)
    F += hazard_plate(Th, -94, 94, -15.5, -7.0, width=4.0)
    F += hazard_plate(Th, -94, 94, 7.0, 15.5, width=4.0)
    for s in (-1, 1):                                   # hinge knuckles (front, on the jamb edge)
        for z0, z1 in ((24, 54), (100, 130), (172, 202)):
            F.append(cyl(ALU, (7.2, s * 94.8, (z0 + z1) / 2), 1.2, z1 - z0, "z", sides=12, label="hinge_knuckle"))
    lights_static = []

    def face_details(side):
        S = face_surface(side, 16 if side == "+x" else -16)
        tag = "Front" if side == "+x" else "Back"
        out = []
        for s in (-1, 1):
            u0, u1 = sorted((s * 97, s * 103.5))
            out += hazard_plate(S, u0, u1, 8, 208, width=5.0)
            out.append(S.box(GUNMETAL, *sorted((s * 105, s * 118)), 12, 40, 0, 2.0, bevel=0.6, label="jamb_cover"))
            out += corner_screws(S.sub(0, 0, 2.0), *sorted((s * 105, s * 118)), 12, 40, inset=1.8)
            # beacon housings (upper corners)
            out.append(S.box(GRAPHITE, *sorted((s * 86, s * 104)), 232, 244, 0, 4.0, bevel=0.8, label="beacon_housing"))
        out.append(S.box(GRAPHITE, -40, 40, 236, 252, 0, 3.0, bevel=0.8, label="header_bar_housing"))
        out += vent(S.sub(0, 0, 3.0), -36, 36, 246, 251, depth=1.0, chamfer=0.8, pitch=1.2, vertical=True)
        beacons = root.child(f"WarningLights_{tag}", role="emissive",
                             note="Red beacons + header alarm bar (pulse via EmissiveScale)")
        bl = []
        for s in (-1, 1):
            bl.append(S.sub(0, 0, 4.0).box(RED, *sorted((s * 88, s * 102)), 234, 242, 0, 2.5, bevel=0.8, label="beacon_lens"))
        bl.append(S.sub(0, 0, 3.0).box(RED, -30, 30, 238, 243, 0, 1.0, bevel=0.4, label="alarm_bar"))
        beacons.add(bl)
        # status / override panel on the viewer's right jamb
        out.append(S.box(GRAPHITE, 105, 119, 116, 172, 0, 3.0, bevel=0.8, label="override_housing"))
        A = S.sub(0, 0, 3.0)
        bz, dp = screen(A, 106.5, 117.5, 138, 169, bezel=1.4, depth=1.2, chamfer=1.4)
        out += bz
        op = root.child(f"OverridePanel_{tag}", role="interactive", note="Seal status display + override buttons")
        op.add(dp)
        for i, (u, cap) in enumerate(((108.8, AMBER), (115.2, RED))):
            bt = button(A, u, 127, 4, 4, cap=cap)
            out.append(bt[0])
            op.child(f"OverridePanel_{tag}_Button_{i + 1}", pivot=A.at(u, 127, 0.4), role="interactive",
                     motion={"type": "press", "dir_ue": [-1 if side == "+x" else 1, 0, 0], "range_cm": [0, 0.3]}).add(bt[1])
        return out

    D = face_details("+x") + face_details("-x")
    # lock keepers under the header soffit (vertical bolts of both leaves throw up into them)
    for s in (-1, 1):
        D.append(box(GUNMETAL, 6.5, 12, *sorted((s * 3.6, s * 10.4)), 224, 228, bevel=0.4, label="lock_keeper"))
    a, e = split_by_mats(F + D, EMISSIVE)
    frame_n.add(a)
    if e:
        root.child("Frame_Lights", role="emissive").add(e)

    # ---------------------------------------------------------------- leaves
    def leaf(s):
        name = "Leaf_L" if s > 0 else "Leaf_R"
        n = root.child(name, pivot=(7.2, s * 94.8, 0.0), role="movable",
                       motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [1, 0, 0],
                               "note": "swings out toward +X" + (" (active leaf, opens first)" if s > 0 else "")},
                       note="Pressure leaf (0.12 m)")
        P = [prism(GUNMETAL, LEAF, "x", -6, 6, bevel=1.0, label="leaf_plate")]
        for side, plane in (("+x", 6), ("-x", -6)):
            S = face_surface(side, plane)
            k = -1 if side == "+x" else 1                 # u of +Y
            u0, u1 = sorted((k * 4, k * 90))
            # raised perimeter rib (octagonal) and cross-brace (structural ribs, 2.0 cm)
            P.append(S.frame(GRAPHITE, rect(u0, u1, 6, 206, 14), rect(u0 + 6, u1 - 6, 12, 200, 10), 0, 2.0, bevel=0.5, label="leaf_rib_ring"))
            P.append(S.box(GRAPHITE, u0 + 6, u1 - 6, 102, 110, 0, 2.0, bevel=0.5, label="leaf_rib_mid"))
            for (a0, b0) in ((k * 10, k * 84),):
                P.append(S.prism(GRAPHITE, [(min(a0, b0) + 14, 30), (min(a0, b0) + 22, 30), (max(a0, b0), 92), (max(a0, b0) - 8, 92)]
                                 if k > 0 else [(max(a0, b0) - 22, 30), (max(a0, b0) - 14, 30), (min(a0, b0), 92), (min(a0, b0) + 8, 92)],
                                 0, 2.0, bevel=0.4, label="leaf_brace"))
            for (uu, vv) in ((k * 24, 186), (k * 70, 186), (k * 24, 24), (k * 70, 24)):
                P.append(S.box(AMBER, uu - 2.5, uu + 2.5, vv - 0.8, vv + 0.8, 0, 0.4, bevel=0.15, label="leaf_marker_light"))
            P += screws(S, [(k * 2.2, 60), (k * 2.2, 160)], r=0.7, h=0.3)
        if s < 0:
            P = mirror(P, 1)
        a, e = split_by_mats(P, EMISSIVE)
        n.add(a)
        n.child(f"{name}_Lights", role="emissive").add(e)
        # locking mechanism: vertical bolt on the seam-side rib, throws +Z into the header keeper
        lk = n.child(f"{name}_LockBolt", pivot=(9.25, s * 7.0, 222.0), role="interactive",
                     motion={"type": "slide", "dir_ue": [0, 0, 1], "travel_cm": 4,
                             "note": "throws up into the header keeper to lock (rest = retracted)"})
        lk.add(box(ALU, 8.0, 10.5, *sorted((s * 5.0, s * 9.0)), 132, 222, bevel=0.5, label="lock_bolt"))
        for zz in (150, 190, 214):
            for yy in ((4.0, 5.0), (9.0, 10.0)):
                n.add(box(GUNMETAL, 8.0, 10.5, *sorted((s * yy[0], s * yy[1])), zz - 3, zz + 3, label="bolt_guide"))
        return n

    leaf_l = leaf(1)
    leaf(-1)
    # manual handwheel (on Leaf_L, centred on the seam, overlaps Leaf_R in front)
    import math
    WC = (8.0, 5.2, 120.0)
    W = Surface(WC, (0, -1, 0), (0, 0, 1), (1, 0, 0))
    wheel = leaf_l.child("ManualWheel", pivot=WC, role="interactive",
                        motion={"type": "rotate", "axis_ue": [1, 0, 0], "range_deg": [0, 720],
                                "note": "two turns retract/throw both lock bolts"})
    WP = [W.cyl(GUNMETAL, 0, 0, 4.5, 0, 2.5, sides=20, bevel=0.4, label="wheel_boss"),
          W.cyl(ALU, 0, 0, 3.0, 2.5, 6.5, sides=20, bevel=0.5, label="wheel_hub"),
          torus(HAZARD, W.at(0, 0, 5.2), 13.5, 1.3, "x", seg=36, sides=10, label="wheel_rim")]
    for ang in (45, 135, 225, 315):
        c, sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        sp = Surface(W.at(0, 0, 5.2), (0, -c, sn), (0, sn, c), (1, 0, 0))
        WP.append(sp.box(HAZARD, -0.9, 0.9, 2.95, 12.25, -0.9, 0.9, bevel=0.3, label="wheel_spoke"))
    wheel.add(WP)

    root.socket("SOCKET_Interact_Wheel", (15.0, 5.2, 120.0), "Manual handwheel (front)")
    root.socket("SOCKET_Interact_Override_Front", (19.0, -112.0, 150.0), "Front override panel")
    root.socket("SOCKET_Interact_Override_Back", (-19.0, 112.0, 150.0), "Back override panel")
    root.socket("SOCKET_Mount_Opening", (0.0, 0.0, 0.0), "Pivot: bottom-centre of the wall opening")
    return Asset(
        name=NAME, title="Emergency Bulkhead Door", reference="07_Bulkhead_Emergency_Door.png",
        envelope=(240, 260, 45), pivot="floor", pivot_text="bottom-centre of the opening, centred in the wall (x = 0)",
        root=root,
        description=("Emergency pressure bulkhead: deep white portal with hazard-striped jambs, bolted jamb covers, "
                     "red beacon housings and header alarm bar on both faces, seal-status/override panels, hazard "
                     "threshold; two ribbed gunmetal pressure leaves hinged on the jambs (swing out +X) with amber "
                     "marker lights, ALU lock bolts throwing into jamb keepers, and an amber manual handwheel."),
        collision="Custom: portal as 3 boxes (jambs + header); each leaf its own box; wheel none.",
        nanite="Nanite ON for Frame and leaves; WarningLights/wheel small separate meshes.",
        interaction=[("Handwheel", "SOCKET_Interact_Wheel", "Rotate 2 turns: bolts retract, then Leaf_L swings"),
                     ("Override (front)", "SOCKET_Interact_Override_Front", "Seal status + override/emergency buttons"),
                     ("Override (back)", "SOCKET_Interact_Override_Back", "Same on the back face")],
        mounting=[("Wall opening", "SOCKET_Mount_Opening", "2.40 x 2.60 cut in a 0.32-0.45 m pressure wall")],
    )
