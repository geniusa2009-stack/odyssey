"""14 OD_PROP_SupplyCrate - hard-shell supply crate (reference 14_Supply_Cargo_Crate.png).

Envelope W 1.00 (Y) x H 0.70 (Z) x D 0.70 (X), pivot bottom-centre (floor). Front (+X) = latch side.
Lid hinges at the rear top edge; two over-centre latches; fold-down top handles; side carry handles.
"""
from od_core import Node, box, prism, face_surface, mirror, quad_mirror, split_by_mats, rect
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, HAZARD, EMISSIVE
from od_kit import strip, vent, chevrons, handle_bar, corner_screws, screws, led_row
from od_asset import Asset

NAME = "OD_PROP_SupplyCrate"
L_POLY = [(27, 46), (31, 46), (31, 42), (35, 42), (35, 50), (27, 50)]   # corner bumper (x, y)


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Lower shell, skids, corner bumpers, straps, side handles")
    lights = root.child("StatusLights", role="emissive", note="Front ion status strips")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    B.append(box(WHITE, -31, 31, -46, 46, 4, 50, bevel=1.0, label="shell_lower"))
    for s in (-1, 1):
        B.append(box(GUNMETAL, s * 16, s * 26, -44, 44, 0, 4, bevel=0.6, label="skid"))
    put(quad_mirror([prism(GRAPHITE, L_POLY, "z", 0, 24, bevel=1.0, label="corner_bumper_low")]))
    # straps (front, rear) on the lower shell
    for side, plane in (("+x", 31), ("-x", -31)):
        S = face_surface(side, plane)
        for u in (-22, 22):
            B.append(S.box(GRAPHITE, u - 4, u + 4, 4, 50, 0, 0.8, bevel=0.2, label="strap_lower"))
    F = face_surface("+x", 31)
    Fs = F.sub(0, 0, 0.8)
    B.append(F.box(WHITE, -15, 15, 10, 44, 0, 0.6, bevel=0.3, label="front_raised_panel"))
    Fp = F.sub(0, 0, 0.6)
    put(chevrons(Fp, -6, 26, 10, mat=GUNMETAL))
    B.extend(vent(Fp, -11, 11, 12.5, 19.5, depth=0.8, chamfer=1.0, pitch=1.6))
    B.extend(corner_screws(Fp, -15, 15, 10, 44, inset=1.6))
    for u in (-36, 36):
        put(strip(F, u - 0.6, u + 0.6, 12, 32, ION))
    # latch bases on the straps
    for u in (-22, 22):
        B.append(Fs.box(ALU, u - 2, u + 2, 40, 46, 0, 1.2, bevel=0.3, label="latch_base"))
    # side carry handles + vents
    for side, plane in (("+y", 46), ("-y", -46)):
        S = face_surface(side, plane)
        B.extend(handle_bar(S, -12, 12, 34, standoff=2.0, r=1.0))
        B.extend(vent(S, -14, 14, 10, 20, depth=1.0, chamfer=1.2, pitch=1.8))
        B.extend(corner_screws(S, -27, 27, 4, 50, inset=2.0))
    # rear hinge knuckles (lid hinge line at x = -31, z = 50)
    for y in (-34, 0, 34):
        B.append(box(GUNMETAL, -32.6, -31, y - 5, y + 5, 46, 49.6, bevel=0.2, label="hinge_leaf_body"))
    put(led_row(face_surface("-x", -31), -4, 14, 3, 4.0, mat=ION))

    # ---------------------------------------------------------------- lid
    lid = root.child("Lid", pivot=(-31.0, 0.0, 50.0), role="movable",
                     motion={"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 100, "opens_toward_ue": [0, 0, 1]},
                     note="Lid hinges on the rear top edge")
    LD = [box(WHITE, -31, 31, -46, 46, 50, 60, bevel=1.0, label="lid_shell")]
    LD += quad_mirror([prism(GRAPHITE, L_POLY, "z", 50, 62, bevel=1.0, label="corner_bumper_lid")])
    for y in (-34, 0, 34):
        LD.append(box(GUNMETAL, -32.6, -31, y - 5, y + 5, 50.4, 54, bevel=0.2, label="hinge_leaf_lid"))
    for side, plane in (("+x", 31), ("-x", -31)):
        S = face_surface(side, plane)
        for u in (-22, 22):
            LD.append(S.box(GRAPHITE, u - 4, u + 4, 50, 60, 0, 0.8, bevel=0.2, label="strap_lid"))
    T = face_surface("+z", 60)                        # u = -Y, v = -X
    for u in (-22, 22):
        LD.append(T.box(GRAPHITE, u - 4, u + 4, -31, 31, 0, 0.8, bevel=0.2, label="strap_top"))
    LD.append(T.box(WHITE, -15, 15, -24, 24, 0, 1.6, bevel=0.5, label="lid_raised_panel"))
    LD += chevrons(T.sub(0, 0, 1.6), -7, -6, 12, mat=GUNMETAL)
    for u in (-22, 22):
        LD.append(Fs.box(ALU, u - 2, u + 2, 53, 58, 0, 1.2, bevel=0.3, label="latch_keeper"))
    LDa, LDe = split_by_mats(LD + strip(F.sub(0, 0, 0), -10, 10, 54.6, 55.6, ION), EMISSIVE)
    lid.add(LDa, LDe)
    # fold-down top handles (each its own node)
    for i, u in enumerate((-38, 38)):
        piv = T.at(u, 0, 0)
        hn = lid.child(f"Handle_Top_{'L' if u > 0 else 'R'}", pivot=piv, role="movable",
                       motion={"type": "hinge", "axis_ue": [1, 0, 0], "range_deg": [0, 85], "note": "folds flat"})
        hn.add(T.box(GUNMETAL, u - 1.6, u + 1.6, -16, -12, 0, 6.6, bevel=0.4, label="handle_foot"),
               T.box(GUNMETAL, u - 1.6, u + 1.6, 12, 16, 0, 6.6, bevel=0.4, label="handle_foot"),
               T.box(ALU, u - 1.7, u + 1.7, -17, 17, 6.6, 10.0, bevel=0.8, label="handle_grip"))
    # over-centre latches (lever spans the seam: body base -> lid keeper)
    for i, u in enumerate((-22, 22)):
        piv = Fs.at(u, 41, 1.2)
        ln = root.child(f"Latch_{'L' if u < 0 else 'R'}", pivot=piv, role="interactive",
                        motion={"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 70], "note": "flips down to release"})
        Lv = Fs.sub(0, 0, 1.2)
        ln.add(Lv.box(ALU, u - 2.4, u + 2.4, 41, 57.5, 0, 1.2, bevel=0.35, label="latch_lever"),
               Lv.prism(HAZARD, [(u - 1.2, 50.5), (u + 1.2, 50.5), (u, 48.6)], 1.2, 1.32, label="latch_arrow"))

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_Lid", (31.0, 0.0, 58.0), "Open/close lid (latches first)")
    root.socket("SOCKET_Interact_Latch_L", Fs.at(-22, 50, 2.4), "Latch L")
    root.socket("SOCKET_Interact_Latch_R", Fs.at(22, 50, 2.4), "Latch R")
    root.socket("SOCKET_Carry_L", (0.0, 50.0, 34.0), "Side carry handle (+Y)")
    root.socket("SOCKET_Carry_R", (0.0, -50.0, 34.0), "Side carry handle (-Y)")
    root.socket("SOCKET_Stack_Top", (0.0, 0.0, 70.0), "Stacking point (top handles folded: 0.62 m)")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot")

    return Asset(
        name=NAME, title="Supply Crate", reference="14_Supply_Cargo_Crate.png",
        envelope=(100, 70, 70), pivot="floor", pivot_text="bottom-centre (floor contact under the skids)",
        root=root,
        description=("Two-piece hard-shell supply crate: lower shell on fork skids, hinged lid with raised panel, "
                     "graphite corner bumpers and wrap straps, two over-centre latches spanning the seam, "
                     "fold-down top handles and side carry handles with intake vents."),
        collision="Simple: one box 0.70 x 1.00 x 0.62 (handles excluded). Physics-simulated prop friendly.",
        nanite="Nanite optional (6-7k tris). For physics props keep a simple UCX box.",
        interaction=[("Lid", "SOCKET_Interact_Lid", "Hinge 100 deg after both latches release"),
                     ("Latches", "SOCKET_Interact_Latch_L", "Flip down 70 deg"),
                     ("Carry", "SOCKET_Carry_L", "Two-hand carry / drag")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Rests on skids"), ("Stack", "SOCKET_Stack_Top", "Stackable")],
    )
