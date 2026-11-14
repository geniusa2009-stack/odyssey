"""06 OD_ENV_SlidingDoor - pressurised station sliding door (references 06 / 06B).

Envelope W 2.40 (Y) x H 2.60 (Z) x D 0.30 (X), pivot bottom-centre of the opening (floor, centred in the
wall thickness). Fills the 2.40 x 2.60 m wall cut of the greybox (door_w 240, door_h 260).
Clear opening 1.96 x 2.30 m. Two leaves run in a 7 cm pocket gap between the front and back frame plates
(top track + floor guide); fully open they retract 1.00 m each into wall pockets beyond the frame.
Both faces are finished (walk-through from either side).
"""
from od_core import Node, box, prism, frame, rect, chamfer_poly, face_surface, split_by_mats, mirror, offset_poly, ccw
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, GLASS, ION, AMBER, HAZARD, EMISSIVE
from od_kit import strip, vent, screws, screen, button, hazard_plate, chevrons, led_row
from od_asset import Asset

NAME = "OD_ENV_SlidingDoor"
U_FRAME = [(-120, 0), (-98, 0), (-98, 216), (-84, 230), (84, 230), (98, 216), (98, 0), (120, 0), (120, 236),
           (96, 260), (-96, 260), (-120, 236)]                     # (y, z)


def build():
    root = Node(NAME, (0, 0, 0), "group")
    fr = root.child("Frame", role="static", note="Front/back frame plates, pocket spacers, header")
    F = [prism(WHITE, U_FRAME, "x", 3.5, 12, bevel=0.8, label="frame_front"),
         prism(WHITE, U_FRAME, "x", -12, -3.5, bevel=0.8, label="frame_back")]
    for s in (-1, 1):
        F.append(box(GUNMETAL, -3.5, 3.5, *sorted((s * 116, s * 120)), 0, 236, label="pocket_end_spacer"))
    F.append(box(GUNMETAL, -3.5, 3.5, -96, 96, 236, 260, label="header_spacer"))
    tracks = root.child("Tracks", role="static", note="Top track and floor guide / threshold")
    T = [box(GUNMETAL, -1.5, 1.5, -116, 116, 233, 236, label="top_track"),
         box(GUNMETAL, -12, 12, -98, 98, 0, 1.0, label="threshold")]
    for s in (-1, 1):
        T.append(box(GUNMETAL, -3.5, 3.5, *sorted((s * 98, s * 116)), 0, 1.0, label="pocket_floor_guide"))
    Th = face_surface("+z", 1.0)                      # u = -Y, v = -X
    T += hazard_plate(Th, -96, 96, -11.5, -4.0, width=4.0)
    T += hazard_plate(Th, -96, 96, 4.0, 11.5, width=4.0)
    tracks.add(T)

    # ---------------------------------------------------------------- face details (front +X and back -X)
    def face_details(side):
        S = face_surface(side, 12 if side == "+x" else -12)      # u = viewer's right, v = Z
        tag = "Front" if side == "+x" else "Back"
        out = []
        out.append(S.box(GRAPHITE, -40, 40, 238, 255, 0, 2.0, bevel=0.6, label="sign_box"))
        bz, dp = screen(S.sub(0, 0, 2.0), -38, 38, 239.5, 253.5, bezel=1.4, depth=1.0, chamfer=1.6)
        out += bz
        root.child(f"Sign_{tag}", role="display", note="Module / access sign display (0..1 UV)").add(dp)
        ind = root.child(f"Indicator_Header_{tag}", role="emissive", note="Door state strip (idle/access/alert)")
        ind.add(strip(S, -30, 30, 233.4, 234.6, ION))
        for s in (-1, 1):
            u0, u1 = sorted((s * 101, s * 117))
            out += vent(S, u0, u1, 14, 52, depth=1.2, chamfer=1.5, pitch=2.0)
            out += hazard_plate(S, u0, u1, 196, 206, width=3.0)
            out += screws(S, [(s * 109, 8), (s * 109, 228)], r=0.7)
            out.append(S.box(AMBER, *sorted((s * 106, s * 112)), 222, 224.4, 0, 0.4, bevel=0.1, label="amber_marker"))
        jl = root.child(f"Indicator_Jamb_{tag}", role="emissive", note="Jamb edge lights")
        jl.add(strip(S, -101.0, -100.0, 60, 190, ION, margin=0.4) + strip(S, 100.0, 101.0, 60, 190, ION, margin=0.4))
        # access panel on the viewer's right jamb
        out.append(S.box(GRAPHITE, 102, 116, 104, 166, 0, 1.8, bevel=0.6, label="access_panel_housing"))
        A = S.sub(0, 0, 1.8)
        bz, dp = screen(A, 103.5, 114.5, 132, 162, bezel=1.2, depth=1.0, chamfer=1.2)
        out += bz
        ap = root.child(f"AccessPanel_{tag}", role="interactive", note="Biometric / ID access panel")
        ap.add(dp)
        bt = button(A, 109, 120, 6, 6, cap=AMBER)
        out.append(bt[0])
        ap.child(f"AccessPanel_{tag}_Button", pivot=A.at(109, 120, 0.4), role="interactive",
                 motion={"type": "press", "dir_ue": [-1 if side == "+x" else 1, 0, 0], "range_cm": [0, 0.3]}).add(bt[1])
        out += led_row(A, 105.5, 110, 3, 3.5, mat=ION)
        return out

    D = face_details("+x") + face_details("-x")
    a, e = split_by_mats(F + D, EMISSIVE)
    fr.add(a)
    root.child("Frame_Lights", role="emissive", note="Frame LEDs").add(e)

    # ---------------------------------------------------------------- leaves
    win = rect(30, 80, 128, 196, 12)                  # (y, z) window for the +Y leaf

    def leaf(name, s):
        n = root.child(name, role="movable",
                       motion={"type": "slide", "dir_ue": [0, s, 0], "travel_cm": 100,
                               "note": "retracts into the wall pocket (ease-in-out ~1.2 s)"},
                       note="Door leaf (gunmetal, reinforced glass window)")
        P = []
        # leaf = four plates around a concentric window ring (frame() needs concentric rings)
        P += [box(GUNMETAL, -2.6, 2.6, 1.25, 108, 1.0, 124, bevel=0.5, label="leaf_lower"),
              box(GUNMETAL, -2.6, 2.6, 1.25, 108, 200, 232.5, bevel=0.5, label="leaf_upper"),
              box(GUNMETAL, -2.6, 2.6, 1.25, 26, 124, 200, label="leaf_stile_inner"),
              box(GUNMETAL, -2.6, 2.6, 84, 108, 124, 200, label="leaf_stile_outer"),
              frame(GUNMETAL, rect(26, 84, 124, 200), win, "x", -2.6, 2.6, label="leaf_window_ring")]
        P.append(prism(GLASS, offset_poly(ccw(win), -0.02), "x", -0.6, 0.6, label="leaf_glass"))
        P.append(box(RUBBER, -2.2, 2.2, 0.25, 1.25, 1.5, 232.0, label="leaf_seal"))
        for side, plane in (("+x", 2.6), ("-x", -2.6)):
            S = face_surface(side, plane)
            k = -1 if side == "+x" else 1                 # u of +Y on this face
            uw = [k * y for y in (26, 84)]
            P.append(S.frame(GRAPHITE, rect(*sorted([k * 25, k * 85]), 123, 201),
                             rect(*sorted([k * 30, k * 80]), 128, 196, 12), 0, 0.45, label="window_bezel"))
            P += chevrons(S, *((k * 60 - 9) if k > 0 else (k * 60 - 9),), 80, 12, mat=WHITE, h0=0)
            P += hazard_plate(S, *sorted([k * 10, k * 100]), 14, 22, width=3.0)
            P += [S.box(ION, *sorted([k * 6, k * 7.2]), 40, 110, 0, 0.3, bevel=0.1, label="leaf_edge_light")]
        if s < 0:
            P = mirror(P, 1)
        a, e = split_by_mats(P, EMISSIVE)
        n.add(a, e)

    leaf("Panel_L", 1)
    leaf("Panel_R", -1)

    root.socket("SOCKET_Interact_Access_Front", (15.0, -109.0, 147.0), "Front access panel")
    root.socket("SOCKET_Interact_Access_Back", (-15.0, 109.0, 147.0), "Back access panel")
    root.socket("SOCKET_Trigger_Centre", (0.0, 0.0, 115.0), "Auto-open trigger volume centre (box 3.0 x 2.4 x 2.3 m)")
    root.socket("SOCKET_Mount_Opening", (0.0, 0.0, 0.0), "Pivot: bottom-centre of the wall opening")
    return Asset(
        name=NAME, title="Station Sliding Door", reference="06_Station_Sliding_Door_Reference.png, 06B_Station_Sliding_Door_Interior_Frame.png",
        envelope=(240, 260, 30), pivot="floor", pivot_text="bottom-centre of the opening, centred in the wall (x = 0)",
        root=root,
        description=("Pressurised bi-parting sliding door that fills a 2.40 x 2.60 m wall opening: white chamfered "
                     "portal frame (front and back plates around a pocket gap), header sign displays, ion header "
                     "and jamb lights, jamb vents and hazard plates, ID access panels on both sides, top track and "
                     "floor guide with hazard threshold, and two gunmetal leaves with reinforced glass windows, "
                     "chevrons and rubber meeting seals."),
        collision=("Custom: frame as 3 boxes (two jambs + header); each leaf its own box (moves with the leaf). "
                   "Add a trigger box for auto-open."),
        nanite="Frame: Nanite ON. Leaves: Nanite ON (opaque) but glass is translucent - keep glass on a non-Nanite section or masked.",
        interaction=[("Access panel (front)", "SOCKET_Interact_Access_Front", "ID / open / lock"),
                     ("Access panel (back)", "SOCKET_Interact_Access_Back", "ID / open / lock"),
                     ("Auto-open", "SOCKET_Trigger_Centre", "Proximity trigger")],
        mounting=[("Wall opening", "SOCKET_Mount_Opening", "Sits in the 2.40 x 2.60 cut; wall pockets 1.00 m each side for full retraction")],
        notes=["Reference sheet quotes 3.20 x 2.40 x 0.42 m; this follows the prototype contract 2.40 x 2.60 x 0.30 m."],
    )
