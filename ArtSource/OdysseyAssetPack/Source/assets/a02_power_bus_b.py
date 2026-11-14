"""02 OD_ENG_PowerBusB - Power Bus B distribution cabinet (reference 02_Power_Bus_B_Cabinet.png).

Envelope W 1.20 (Y) x H 2.20 (Z) x D 0.60 (X), pivot bottom-centre of the REAR face (wall_base):
x in [0, 60] with the rear face flush on the wall at x = 0. Front (+X) = service side.
"""
from od_core import Node, box, rect, face_surface, mirror_y, split_by_mats, offset_poly, ccw
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, AMBER, RED, HAZARD, EMISSIVE
from od_kit import (screws, corner_screws, strip, vent, chevrons, button, toggle, screen, recessed_handle,
                    handle_bar, warning_triangle, led_row, hazard_plate)
from od_asset import Asset

NAME = "OD_ENG_PowerBusB"


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Cabinet shell, plinth, module panels, breaker housings")
    lights = root.child("StatusLights", role="emissive", note="Header strip, plinth lights, LEDs (EmissiveScale)")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    # ---------------------------------------------------------------- plinth + corner feet
    B.append(box(GRAPHITE, 4, 56, -46, 46, 0, 12, bevel=0.8, label="plinth"))
    feet = []
    for (x0, x1) in ((0, 14), (46, 60)):
        feet.append(box(RUBBER, x0 + 1, x1 - 1, 47, 59, 0, 1, bevel=0.2, label="foot_pad"))
        feet.append(box(GUNMETAL, x0, x1, 46, 60, 1, 14, bevel=1.2, label="foot"))
    put(feet); put(mirror_y(feet))
    Sp = face_surface("+x", 56)
    B.extend(vent(Sp, -18, 18, 2.5, 10, depth=1.2, chamfer=1.5, pitch=1.6))
    for u in (-31, 31):
        put(strip(Sp, u - 5, u + 5, 5.6, 6.8, ION))

    # ---------------------------------------------------------------- shell
    B.append(box(GRAPHITE, 2, 54, -54, 54, 14, 212, label="core"))
    B.append(box(WHITE, 0, 2, -58, 58, 14, 212, bevel=0.5, label="rear_panel"))
    side = []
    for (z0, z1) in ((14, 80), (80.5, 150), (150.5, 212)):
        side.append(box(WHITE, 2, 58, 54, 58, z0, z1, bevel=0.6, label="side_panel"))
    So = face_surface("+y", 58)
    side += vent(So, 30, 50, 22, 44, depth=1.4, chamfer=1.5, pitch=2.0)
    side += vent(So, 36, 50, 166, 196, depth=1.4, chamfer=1.5, pitch=2.0, vertical=False)
    for (z0, z1) in ((14, 80), (80.5, 150), (150.5, 212)):
        side += corner_screws(So, 2, 58, z0, z1, inset=2.2)
    side.append(So.box(GUNMETAL, 8, 10, 96, 134, 0, 0.6, bevel=0.2, label="side_latch_rail"))
    put(side); put(mirror_y(side))
    B.append(box(WHITE, 0, 58, -58, 58, 212, 216, bevel=1.0, label="top_cap"))
    St = face_surface("+z", 216)                    # u = -Y, v = -X
    for u in (-40, 40):                             # lifting handles (front-to-back)
        T = St
        B.append(T.box(GUNMETAL, u - 1.4, u + 1.4, -50, -46, 0, 2.4, bevel=0.3, label="lift_foot"))
        B.append(T.box(GUNMETAL, u - 1.4, u + 1.4, -12, -8, 0, 2.4, bevel=0.3, label="lift_foot"))
        B.append(T.box(ALU, u - 0.8, u + 0.8, -51.4, -6.6, 2.4, 4.0, bevel=0.35, label="lift_bar"))
    B.append(St.box(GRAPHITE, -22, 22, -40, -16, 0, 0.5, bevel=0.2, label="top_gland_plate"))
    for k in range(3):
        B.append(St.cyl(RUBBER, -13 + 13 * k, -28, 3.0, 0.5, 2.0, sides=16, bevel=0.3, label="cable_gland"))
    Stf = face_surface("+x", 58)
    put(strip(Stf, -14, 14, 213.4, 214.6, ION))     # header strip on the cap front
    put(chevrons(Stf, 24, 212.6, 3.0, mat=GUNMETAL))

    # ---------------------------------------------------------------- front pilasters with grab handles
    F = face_surface("+x", 54)                     # u = -Y (viewer's right), v = Z
    for s in (-1, 1):
        u0, u1 = sorted((s * 46, s * 54))
        B.append(F.box(WHITE, u0, u1, 14, 212, 0, 1.0, bevel=0.3, label="pilaster"))
        B.extend(handle_bar(F.sub(0, 0, 1.0), 118, 178, s * 50, standoff=3.4, r=0.8, vertical=True))
        B.extend(screws(F.sub(0, 0, 1.0), [(s * 50, 20), (s * 50, 206)]))

    # ---------------------------------------------------------------- module stack (front plane x = 58)
    def panel(z0, z1, mat=GRAPHITE, label="module_panel", depth=1.0):
        B.append(F.box(mat, -45.5, 45.5, z0, z1, 0, depth, bevel=0.3, label=label))
        return F.sub(0, 0, depth)

    P = panel(190, 211.5, WHITE, "header_panel")
    B.extend(vent(P, -38, 38, 193, 208, depth=1.0, chamfer=2.0, pitch=1.6))
    # status display module
    P = panel(158, 189.5)
    bz, dp = screen(P, -40, 8, 161, 187, bezel=2.0, depth=1.4, chamfer=2.0)
    B.extend(bz)
    root.child("Screen_Status", role="display", note="Bus B load display (0..1 UV on OD_MAT_Display)").add(dp)
    B.append(P.box(GUNMETAL, 14, 40, 161, 187, 0, 0.8, bevel=0.3, label="led_bezel"))
    for k in range(3):
        put([P.box(ION, 22, 32, 165 + 7 * k, 168 + 7 * k, 0.8, 1.2, bevel=0.15, label="status_led")])
    # main breakers + toggles
    P = panel(118, 157.5)
    for i, u in enumerate((-36, -22, -8)):
        B.append(P.box(GUNMETAL, u - 5.5, u + 5.5, 121, 154, 0, 2.0, bevel=0.4, label="breaker_housing"))
        put([P.box(ION, u - 1.0, u + 1.0, 150, 152, 2.0, 2.3, label="breaker_led")])
        B.append(P.box(GRAPHITE, u - 3.5, u + 3.5, 126, 146, 2.0, 2.5, bevel=0.2, label="breaker_slot"))
        piv = P.at(u, 136, 2.5)
        bn = root.child(f"Breaker_Main_{i + 1:02d}", pivot=piv, role="interactive",
                        motion={"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-35, 35],
                                "note": "lever throws up (ON) / down (OFF) about Y"})
        H = P.sub(0, 0, 2.5)
        bn.add(H.box(GRAPHITE, u - 2.6, u + 2.6, 131, 141, 0, 2.0, bevel=0.5, label="breaker_lever"),
               H.box(RED, u - 2.2, u + 2.2, 137, 140.5, 2.0, 2.5, bevel=0.2, label="breaker_flag"))
    B.append(P.box(GUNMETAL, 4, 40, 121, 154, 0, 1.2, bevel=0.4, label="toggle_subpanel"))
    T = P.sub(0, 0, 1.2)
    for i, u in enumerate((14, 30)):
        parts = toggle(T, u, 134, guard=True)
        put([p for p in parts if p.label != "toggle_lever"])
        root.child(f"Toggle_{i + 1:02d}", pivot=T.at(u, 134, 0.95), role="interactive",
                   motion={"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-40, 40]}).add(
            [p for p in parts if p.label == "toggle_lever"])
        put([T.box(ION, u - 1.6, u + 1.6, 146, 148, 0, 0.3, label="toggle_led")])
    # MCB strip on a DIN rail
    P = panel(88, 117.5)
    B.append(P.box(ALU, -42, 42, 99, 103, 0, 0.6, label="din_rail"))
    mcb = root.child("MCB_Strip", role="group", note="Eight miniature breakers; each toggle is its own node")
    for i in range(8):
        u = -36.75 + i * 10.5
        B.append(P.box(GRAPHITE, u - 4.6, u + 4.6, 92, 110, 0.6, 3.0, bevel=0.4, label="mcb_body"))
        put([P.box(ION, u - 1.0, u + 1.0, 112, 114, 0, 0.3, bevel=0.1, label="mcb_led")])
        M = P.sub(0, 0, 3.0)
        mcb.child(f"MCB_Toggle_{i + 1:02d}", pivot=M.at(u, 101, 0), role="interactive",
                  motion={"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]}).add(
            M.box(ALU, u - 1.8, u + 1.8, 98, 104, 0, 1.4, bevel=0.3, label="mcb_toggle"))
    # kick plate under the door
    B.append(F.box(GUNMETAL, -45.5, 45.5, 14, 17.5, 0, 2.0, bevel=0.3, label="kick_plate"))
    put(hazard_plate(F.sub(0, 0, 2.0), -30, 30, 14.4, 17.1, width=1.4))

    # ---------------------------------------------------------------- lower access door (hinged on the +Y edge)
    door = root.child("AccessDoor", pivot=(58.0, 45.5, 18.0), role="movable",
                      motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 105, "opens_toward_ue": [1, 0, 0]},
                      note="Lower cable compartment door, hinge on the +Y edge")
    D = [F.box(WHITE, -45.5, 45.5, 18, 87.5, 0, 4.0, bevel=0.6, label="access_door")]
    Dd = F.sub(0, 0, 4.0)
    D += recessed_handle(Dd, 36, 58, 4.5, 14)
    D += warning_triangle(Dd, 24, 66, 7)
    D += vent(Dd, -36, 20, 24, 36, depth=1.0, chamfer=1.2, pitch=1.8)
    D.append(Dd.box(GRAPHITE, -40, 40, 44.5, 45.3, 0, 0.12, label="door_seam_inlay"))
    D += corner_screws(Dd, -45.5, 45.5, 18, 87.5, inset=2.2)
    door.add(D)

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_Breakers", F.at(-22, 136, 8), "Main breaker bank (3 levers)")
    root.socket("SOCKET_Interact_Screen", F.at(-16, 174, 5.5), "Status display")
    root.socket("SOCKET_Interact_MCB", F.at(0, 101, 10), "MCB strip")
    root.socket("SOCKET_Interact_AccessDoor", F.at(36, 58, 5), "Door pull")
    root.socket("SOCKET_Mount_Wall", (0.0, 0.0, 0.0), "Pivot: rear face bottom-centre, flush to wall")
    root.socket("SOCKET_Mount_WallAnchor_L", (0.0, 40.0, 200.0), "Upper wall anchor (M12) through rear panel")
    root.socket("SOCKET_Mount_WallAnchor_R", (0.0, -40.0, 200.0), "Upper wall anchor (M12) through rear panel")
    root.socket("SOCKET_Cable_Top", (28.0, 0.0, 218.0), "Top cable gland plate")

    return Asset(
        name=NAME, title="Power Bus B Cabinet", reference="02_Power_Bus_B_Cabinet.png",
        envelope=(120, 220, 60), pivot="wall_base", pivot_text="bottom-centre of the rear face (rear flush to wall)",
        root=root,
        description=("Wall-standing power distribution cabinet for Bus B. Stacked front modules: exhaust header, "
                     "status display with LED column, three main breakers with throw levers and a guarded toggle "
                     "sub-panel, an eight-way MCB strip on a DIN rail, and a hinged lower cable compartment door. "
                     "Corner feet on a recessed plinth with intake grille; vertical grab handles; top lifting bars "
                     "and cable glands."),
        collision="Simple: one box 0.60 x 1.20 x 2.20 (UCX). AccessDoor: own box when opened.",
        nanite="Body: Nanite ON. Levers/toggles/door/display: separate small meshes, Nanite optional.",
        interaction=[("Main breakers", "SOCKET_Interact_Breakers", "Throw levers ON/OFF (hinge about Y)"),
                     ("Status display", "SOCKET_Interact_Screen", "Bus load UI"),
                     ("MCB strip", "SOCKET_Interact_MCB", "8 toggles"),
                     ("Access door", "SOCKET_Interact_AccessDoor", "Opens 105 deg")],
        mounting=[("Wall", "SOCKET_Mount_Wall", "Rear flush to wall; floor standing on 4 feet"),
                  ("Wall anchors", "SOCKET_Mount_WallAnchor_L", "Two upper anchors (L/R)"),
                  ("Cable entry", "SOCKET_Cable_Top", "Top gland plate")],
    )
