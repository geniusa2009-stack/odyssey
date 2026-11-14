"""13 OD_ENV_VentilationModule - wall ventilation unit (reference 13_Ventilation_Module.png).

Envelope W 1.40 (Y) x H 0.80 (Z) x D 0.40 (X), pivot centre of the rear face (wall): x in [0, 40].
Chamfered white housing with a 0.30 m deep louver bay (four adjustable louver rows in three bays),
filter plenum, gunmetal bay bezel, hinged filter hatch, side slot vents and corner caps.
"""
from od_core import Node, box, rect, face_surface, split_by_mats, offset_poly, ccw
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, ION, HAZARD, EMISSIVE
from od_kit import strip, vent, screws, corner_screws, chevrons, recessed_handle, led_row
from od_asset import Asset

NAME = "OD_ENV_VentilationModule"


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Housing, plenum, bezel, dividers, vents")
    lights = root.child("StatusLights", role="emissive", note="Airflow status strip")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    B.append(box(GUNMETAL, 0, 2, -64, 64, -36, 36, bevel=0.4, label="wall_plate"))
    S0 = face_surface("+x", 2)                          # u = -Y, v = Z
    bay = rect(-56, 56, -24, 26, 6)
    B.append(S0.frame(WHITE, rect(-68, 68, -40, 40, 10), bay, 0, 32, bevel=0.8, label="housing"))
    B.append(S0.prism(GRAPHITE, offset_poly(ccw(bay), -0.05), 0, 1.0, label="plenum_back"))
    Sp = S0.sub(0, 0, 1.0)
    B.extend(vent(Sp, -54, 54, -22, 24, depth=1.6, chamfer=4.0, pitch=1.3, vertical=True, slat_mat=GRAPHITE,
                  frame_mat=GUNMETAL, back_mat=GRAPHITE))
    # dividers (full bay depth)
    for u in (-19, 19):
        B.append(S0.box(GUNMETAL, u - 0.6, u + 0.6, -23.95, 25.95, 2.6, 32, label="bay_divider"))
    # front bezel around the bay (reaches the 0.40 m front plane)
    Sf = S0.sub(0, 0, 32)                               # x = 34
    B.append(Sf.frame(GUNMETAL, rect(-60, 60, -28, 30, 8), rect(-56, 56, -24, 26, 6), 0, 6, bevel=0.6, label="bay_bezel"))
    B.extend(screws(Sf, [(-64, 0), (64, 0)], r=0.6))
    # louver rows (each row = three blade segments between the walls/dividers, one node per row)
    louvers = root.child("Louvers", role="group", note="Adjustable louver rows (rotate about Y)")
    spans = [(-54.0, -19.6), (-18.4, 18.4), (19.6, 54.0)]
    for i, v in enumerate((-15, -4, 7, 18)):
        piv = S0.at(0, v, 24)
        rn = louvers.child(f"Louver_Row_{i + 1:02d}", pivot=piv, role="interactive",
                           motion={"type": "rotate", "axis_ue": [0, 1, 0], "range_deg": [-35, 35]})
        T = S0.sub(0, v, 24).tilt(-25)
        rn.add([T.box(ALU, a, b, -4.2, 4.2, -0.35, 0.35, bevel=0.15, label="louver_blade") for a, b in spans])
    # top band: status strip + slot vents
    put(strip(Sf, -18, 18, 34.4, 35.6, ION))
    B.extend(vent(Sf, 38, 54, 32, 37, depth=1.0, chamfer=0.6, pitch=1.4, vertical=True))
    B.extend(vent(Sf, -54, -38, 32, 37, depth=1.0, chamfer=0.6, pitch=1.4, vertical=True))
    # bottom band: hazard chevrons + hinged filter hatch
    put(chevrons(Sf, -48, -37, 6, mat=HAZARD))
    put(led_row(Sf, -24, -34, 4, 2.6, mat=ION))
    hatch = root.child("FilterHatch", pivot=Sf.at(27, -38, 0), role="movable",
                       motion={"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 90, "opens_toward_ue": [1, 0, 0],
                               "note": "drops down on its bottom edge for filter change"})
    H = [Sf.box(WHITE, 4, 50, -38, -29, 0, 1.6, bevel=0.4, label="filter_hatch")]
    Hs = Sf.sub(0, 0, 1.6)
    H += recessed_handle(Hs, 24, -33.5, 7, 4.2)
    H += corner_screws(Hs, 4, 50, -38, -29, inset=1.4, r=0.45)
    for k in range(5):
        H.append(Hs.cyl(GRAPHITE, 40 + (k % 3) * 2, -35 + (k // 3) * 2.5, 0.5, 0, 0.12, sides=8, label="hatch_perforation"))
    hatch.add(H)
    # sides: slot vents + graphite corner caps
    for side, plane in (("+y", 68), ("-y", -68)):
        S = face_surface(side, plane)
        k = 1 if side == "+y" else -1                 # '-y' faces have u = -X
        B.extend(vent(S, *sorted((k * 6, k * 30)), -16, 16, depth=1.4, chamfer=1.0, pitch=1.8))
        for vv in (-26, 26):
            B.append(S.box(GRAPHITE, *sorted((k * 4, k * 30)), vv - 3.6, vv + 3.6, 0, 2.0, bevel=0.5, label="corner_cap"))
    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_FilterHatch", Hs.at(24, -33.5, 1.0), "Filter hatch pull")
    root.socket("SOCKET_Interact_Louvers", Sf.at(0, 1, 0), "Louver adjust / airflow look-at")
    root.socket("SOCKET_FX_Airflow", S0.at(0, 1, 38), "Air outlet: particle/airflow FX origin, +X")
    root.socket("SOCKET_Mount_Wall", (0.0, 0.0, 0.0), "Pivot: centre of rear face, flush to wall")
    for i, (y, z) in enumerate(((60, 32), (-60, 32), (60, -32), (-60, -32))):
        root.socket(f"SOCKET_Mount_Anchor_{i + 1}", (0.0, y, z), "Wall anchor through wall plate")
    return Asset(
        name=NAME, title="Ventilation Module", reference="13_Ventilation_Module.png",
        envelope=(140, 80, 40), pivot="wall", pivot_text="centre of the rear face (flush to wall)",
        root=root,
        description=("Wall ventilation unit: chamfered white housing with a deep louver bay (four adjustable rows "
                     "across three bays split by gunmetal dividers), recessed filter plenum, gunmetal bay bezel, "
                     "airflow status strip, side slot vents with graphite corner caps and a drop-down filter hatch."),
        collision="None (wall detail) or one box 0.40 x 1.40 x 0.80.",
        nanite="Nanite ON for Body; louver rows and hatch as small separate meshes.",
        interaction=[("Filter hatch", "SOCKET_Interact_FilterHatch", "Drops 90 deg"),
                     ("Louvers", "SOCKET_Interact_Louvers", "Rows rotate +-35 deg")],
        mounting=[("Wall", "SOCKET_Mount_Wall", "Flush to wall; four anchors")],
    )
