"""12 OD_ENV_WallUtilityPanel - wall utility / service panel (reference 12_Wall_Utility_Panel.png).

Envelope W 1.00 (Y) x H 1.20 (Z) x D 0.18 (X), pivot centre of the rear face (wall): x in [0, 18].
Recessed equipment bay inside a chamfered white frame: hinged power-access door, status display,
connector plate, guarded emergency switch, intake/exhaust vents.
"""
from od_core import Node, prism, rect, face_surface, split_by_mats, offset_poly, ccw
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, GLASS, ION, RED, AMBER, HAZARD, EMISSIVE
from od_kit import (strip, vent, screws, corner_screws, screen, warning_triangle, chevrons, hinge_knuckles,
                    hazard_plate, led_row)
from od_asset import Asset

NAME = "OD_ENV_WallUtilityPanel"


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Backplate, frame, bay, vents, connector plate")
    lights = root.child("StatusLights", role="emissive", note="Frame ion strips and LEDs")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    B.append(prism(GUNMETAL, rect(-50, 50, -60, 60, 8), "x", 0, 4, bevel=0.6, label="wall_backplate"))
    S0 = face_surface("+x", 4)                         # u = -Y, v = Z
    inner = rect(-44, 44, -52, 52, 4)
    B.append(S0.frame(WHITE, rect(-50, 50, -60, 60, 8), inner, 0, 8, bevel=0.6, label="frame"))
    B.append(S0.prism(GRAPHITE, offset_poly(ccw(inner), -0.05), 0, 1.0, label="bay_floor"))
    Sf = S0.sub(0, 0, 8)                               # frame front (x = 12)
    for u in (-47, 47):
        put(strip(Sf, u - 0.6, u + 0.6, -22, 22, ION))
    put(strip(Sf, -16, 16, 55.4, 56.6, ION))
    put(strip(Sf, -16, 16, -56.6, -55.4, ION))
    B.extend(screws(Sf, [(-44, 55), (44, 55), (-44, -55), (44, -55)], r=0.9, h=0.4))
    put(chevrons(Sf, 26, -58.5, 3.5, mat=HAZARD))
    put(chevrons(Sf, -36, 54.5, 3.5, mat=HAZARD))

    S = S0.sub(0, 0, 1.0)                              # bay floor (x = 5)
    B.extend(vent(S, -32, 32, 38, 49, depth=2.0, chamfer=2.0, pitch=1.8))
    B.extend(vent(S, -41, -15, -48, -32, depth=2.0, chamfer=1.5, pitch=1.8))
    B.extend(vent(S, 15, 41, -48, -32, depth=2.0, chamfer=1.5, pitch=1.8))
    put(hazard_plate(S, -11, 11, -47, -36, width=1.6))
    # power access compartment + hinged door (hinge on the viewer's-left edge)
    B.append(S.box(GRAPHITE, -42, -14, -8, 36, 0, 2.0, bevel=0.4, label="power_recess"))
    Sd = S.sub(0, 0, 2.0)
    B.extend(hinge_knuckles(Sd, -42.6 + 1.2, -4, 32, n=2, r=0.7, length=6))
    door = root.child("PowerAccessDoor", pivot=Sd.at(-41, 14, 0), role="movable",
                      motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 110, "opens_toward_ue": [1, 0, 0]},
                      note="Power access door, hinge on the +Y (viewer's left) edge")
    D = [Sd.box(GUNMETAL, -39.8, -15, -7, 35, 0, 2.6, bevel=0.5, label="power_door")]
    Dd = Sd.sub(0, 0, 2.6)
    D += warning_triangle(Dd, -27.5, 20, 9)
    D += vent(Dd, -35, -20, 26, 32, depth=0.8, chamfer=0.8, pitch=1.4)
    D.append(Dd.box(HAZARD, -18.6, -17.0, 4, 24, 0, 2.2, bevel=0.5, label="door_pull"))
    D += chevrons(Dd, -35, -4, 3.5, mat=HAZARD)
    door.add(D)
    # status display
    bz, dp = screen(S, -10, 26, 8, 36, bezel=2.0, depth=2.0, chamfer=2.0, bezel_mat=GUNMETAL)
    B.extend(bz)
    root.child("Screen_Status", role="display", note="Utility status display (0..1 UV)").add(dp)
    # connector plate: two circular power connectors + two data ports
    B.append(S.box(GUNMETAL, -10, 26, -8, 5, 0, 1.6, bevel=0.4, label="connector_plate"))
    Sc = S.sub(0, 0, 1.6)
    for u in (-3, 7):
        B.append(Sc.tube(ALU, u, -1.5, 4.0, 2.6, 0, 2.6, sides=24, bevel=0.3, label="connector_shell"))
        B.append(Sc.cyl(GRAPHITE, u, -1.5, 2.55, 0, 0.6, sides=20, label="connector_face"))
        for du, dv in ((-1, -0.8), (1, -0.8), (0, 1.0)):
            B.append(Sc.cyl(HAZARD, u + du, -1.5 + dv, 0.35, 0.6, 1.3, sides=8, label="connector_pin"))
    for v in (1.5, -4.5):
        B.append(Sc.box(GRAPHITE, 14, 22, v - 1.2, v + 1.2, 0, 0.5, bevel=0.3, label="data_port"))
        put([Sc.box(ION, 15.5, 20.5, v - 0.4, v + 0.4, 0.5, 0.7, label="data_port_led")])
    # guarded emergency switch (reaches the 0.18 m front plane)
    B.append(S.box(GRAPHITE, 29, 42, -8, 36, 0, 9.0, bevel=0.8, label="emergency_housing"))
    Se = S.sub(0, 0, 9.0)
    B.append(Se.box(GUNMETAL, 31, 40, 2, 26, 0, 0.6, bevel=0.2, label="emergency_bezel"))
    put([Se.box(RED, 32.5, 38.5, 29, 31, 0, 0.4, bevel=0.1, label="emergency_led")])
    btn = root.child("EmergencySwitch_Button", pivot=Se.at(35.5, 13, 0.6), role="interactive",
                     motion={"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.6]})
    btn.add(Se.box(RED, 32.6, 38.4, 8, 18, 0.6, 2.2, bevel=0.5, label="emergency_button"))
    grd = root.child("EmergencySwitch_Guard", pivot=Se.at(35.5, 26, 0.6), role="interactive",
                     motion={"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 100, "opens_toward_ue": [0, 0, 1],
                             "note": "flip-up cover hinged on its top edge"})
    G = Se.sub(0, 0, 0.6)
    grd.add(G.box(GLASS, 31.4, 39.6, 3, 25.4, 2.4, 3.0, bevel=0.2, label="guard_window"),
            G.box(GUNMETAL, 31, 31.4, 2.6, 25.4, 0, 3.4, label="guard_side"),
            G.box(GUNMETAL, 39.6, 40, 2.6, 25.4, 0, 3.4, label="guard_side"),
            G.box(GUNMETAL, 31.4, 39.6, 25.4, 26, 0, 3.4, label="guard_hinge_bar"),
            G.box(RED, 31.4, 39.6, 2.6, 3.0, 0, 3.4, label="guard_lip"))
    put(led_row(S, -36, -12, 5, 2.4, mat=AMBER))

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_Screen", S.at(8, 22, 2.5), "Status display")
    root.socket("SOCKET_Interact_PowerDoor", Dd.at(-17.8, 14, 2.2), "Power access door pull")
    root.socket("SOCKET_Interact_Emergency", Se.at(35.5, 13, 4.0), "Emergency switch (lift guard, press)")
    root.socket("SOCKET_Interact_Connectors", Sc.at(2, -1.5, 2.6), "Power connectors")
    root.socket("SOCKET_Mount_Wall", (0.0, 0.0, 0.0), "Pivot: centre of the rear face, flush to wall")
    for i, (y, z) in enumerate(((44, 54), (-44, 54), (44, -54), (-44, -54))):
        root.socket(f"SOCKET_Mount_Anchor_{i + 1}", (0.0, y, z), "Wall anchor through backplate corner")
    return Asset(
        name=NAME, title="Wall Utility Panel", reference="12_Wall_Utility_Panel.png",
        envelope=(100, 120, 18), pivot="wall", pivot_text="centre of the rear face (flush to wall)",
        root=root,
        description=("Wall-mounted utility panel: gunmetal wall backplate, chamfered white frame with ion strips, "
                     "recessed equipment bay holding a hinged power-access door, status display, circular power "
                     "connectors and data ports, a guarded emergency switch and intake/exhaust vents."),
        collision="None needed (flush wall detail) or one box 0.18 x 1.00 x 1.20 for traces.",
        nanite="Nanite ON for Body; door/guard/button/display small separate meshes.",
        interaction=[("Status display", "SOCKET_Interact_Screen", "Utility status UI"),
                     ("Power door", "SOCKET_Interact_PowerDoor", "Opens 110 deg"),
                     ("Emergency switch", "SOCKET_Interact_Emergency", "Lift guard 100 deg, press button"),
                     ("Connectors", "SOCKET_Interact_Connectors", "Plug-in point for cables/tools")],
        mounting=[("Wall", "SOCKET_Mount_Wall", "Flush to wall; four corner anchors")],
        notes=["Reference is drawn landscape; the prototype contract is portrait W 1.00 x H 1.20 m, which this follows."],
    )
