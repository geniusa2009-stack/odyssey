"""04 OD_LAB_SampleAnalyzer - laboratory sample analyzer (reference 04_Laboratory_Sample_Analyzer_Ref.png).

Envelope W 1.60 (Y) x H 1.70 (Z) x D 0.90 (X), pivot bottom-centre (floor). Front (+X) = operator side.
Lower cabinet with side pods; 0.98 m worktop with control strip, cartridge tray tunnel and e-stop; central
glazed sample chamber (sliding glass door, sample rack with vials, analysis head) flanked by two toed-in
displays; top housing; rear maintenance panel.
"""
import math

from od_core import Node, box, prism, frame, rect, face_surface, split_by_mats, Surface, mirror, cyl, tube
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, GLASS, ION, AMBER, RED, HAZARD, EMISSIVE
from od_kit import (strip, vent, screws, corner_screws, screen, button, knob, hazard_plate, chevrons, led_row,
                    recessed_handle, warning_triangle)
from od_asset import Asset

NAME = "OD_LAB_SampleAnalyzer"


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Base, cabinet, pods, worktop, top housing, rear column")
    lights = root.child("StatusLights", role="emissive", note="Status strips and LEDs")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    # ---------------------------------------------------------------- base and cabinet
    B.append(box(GRAPHITE, -38, 36, -72, 72, 0, 8, bevel=0.8, label="plinth"))
    pod = []
    for x0, x1 in ((36, 45), (-45, -38)):
        pod.append(box(RUBBER, x0 + 1, x1 - 1, 57, 79, 0, 1, bevel=0.2, label="foot_pad"))
        pod.append(box(GUNMETAL, x0, x1, 56, 80, 1, 10, bevel=1.2, label="foot"))
    pod += strip(face_surface("+z", 10), -76, -60, -43.4, -42.2, AMBER, margin=0.4)
    pod.append(box(WHITE, -42, 34, 50, 80, 10, 88, bevel=1.0, label="pod"))
    Sp = face_surface("+x", 34)
    pod += vent(Sp, -76, -54, 16, 60, depth=1.4, chamfer=2.0, pitch=2.2)
    pod += strip(Sp, -76, -54, 66.4, 67.6, ION)
    pod += corner_screws(Sp, -80, -50, 10, 88, inset=2.2)
    Spr = face_surface("-x", -42)                      # u = +Y
    pod += vent(Spr, 54, 76, 40, 80, depth=1.2, chamfer=1.5, pitch=2.0)
    put(pod); put(mirror(pod, 1))
    B.append(box(GRAPHITE, -40, 30, -50, 50, 8, 88, label="core"))
    Sc = face_surface("+x", 30)
    B.append(Sc.box(WHITE, -49.6, 49.6, 10, 86, 0, 3.0, bevel=0.8, label="front_panel"))
    Sf = Sc.sub(0, 0, 3.0)
    B.append(Sf.box(GRAPHITE, -30, 30, 44, 54, 0, 0.5, bevel=0.3, label="label_plate"))
    put(chevrons(Sf, 34, 46, 6, mat=GUNMETAL))
    put(strip(Sf, -26, 26, 80.4, 81.6, ION))
    B.extend(vent(Sf, -40, 40, 16, 30, depth=1.0, chamfer=1.5, pitch=1.8))
    B.extend(corner_screws(Sf, -49.6, 49.6, 10, 86, inset=2.0))
    # rear maintenance panel (hinged)
    Sr = face_surface("-x", -40)
    mp = root.child("MaintenancePanel", pivot=Sr.at(-49.6, 12, 0), role="movable",
                    motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [-1, 0, 0]},
                    note="Rear maintenance access panel")
    M = [Sr.box(WHITE, -49.6, 49.6, 12, 86, 0, 2.0, bevel=0.6, label="maintenance_panel")]
    Ms = Sr.sub(0, 0, 2.0)
    M += vent(Ms, -36, 36, 56, 78, depth=0.8, chamfer=1.5, pitch=2.0)
    M += recessed_handle(Ms, 40, 46, 4, 12)
    M += warning_triangle(Ms, 0, 30, 9)
    M += corner_screws(Ms, -49.6, 49.6, 12, 86, inset=2.0)
    mp.add(M)

    # ---------------------------------------------------------------- worktop + controls
    B.append(prism(WHITE, [(-42, 88), (40, 88), (45, 91), (45, 95.5), (42.5, 98), (-42, 98)], "y", -80, 80, bevel=1.0, label="worktop"))
    W = face_surface("+z", 98)                         # u = -Y, v = -X  (x = -v)
    controls = root.child("Controls", role="group", note="Worktop controls")
    B.append(W.box(GRAPHITE, -72, -36, -41, -25, 0, 0.8, bevel=0.3, label="module_left"))
    B.append(W.box(GRAPHITE, -32, -17, -41, -25, 0, 0.8, bevel=0.3, label="module_knob"))
    B.append(W.box(GRAPHITE, 17, 44, -41, -25, 0, 0.8, bevel=0.3, label="module_right"))
    Wm = W.sub(0, 0, 0.8)
    caps, bases = [], []
    for i, u in enumerate((-66, -58, -50, -42)):
        for v, cap in ((-36, ION), (-30, RED if i == 3 else ION)):
            b = button(Wm, u, v, 4.4, 3.0, cap=cap)
            bases.append(b[0]); caps.append(b[1])
    for u, cap in ((24, RED), (32, ION), (40, AMBER)):
        b = button(Wm, u, -33, 5.0, 4.0, cap=cap)
        bases.append(b[0]); caps.append(b[1])
    B.extend(bases)
    controls.child("Control_Buttons", role="interactive",
                   motion={"type": "press", "dir_ue": [0, 0, -1], "range_cm": [0, 0.3]},
                   note="Load off / Load nominal / Diagnostic / mode buttons").add(caps)
    kp = knob(Wm, -24.5, -33, 3.0)
    L.append(kp[0])
    controls.child("Control_Knob", pivot=Wm.at(-24.5, -33, 0), role="interactive",
                   motion={"type": "rotate", "axis_ue": [0, 0, 1], "range_deg": [-135, 135]}).add(kp[1:])
    put(led_row(Wm, -30, -27, 5, 2.4, mat=ION))
    # e-stop
    put([s for s in hazard_plate(W, 50, 72, -42, -24, width=2.4)])
    Wh = W.sub(0, 0, 0.62)
    B.append(Wh.cyl(GUNMETAL, 61, -33, 5.0, 0, 1.4, sides=28, bevel=0.3, label="estop_collar"))
    controls.child("Control_EStop", pivot=Wh.at(61, -33, 1.4), role="interactive",
                   motion={"type": "slide", "dir_ue": [0, 0, -1], "range_cm": [0, 0.8], "note": "emergency stop"}).add(
        Wh.cyl(RED, 61, -33, 1.6, 1.4, 2.6, sides=16, label="estop_stem"),
        Wh.cyl(RED, 61, -33, 4.2, 2.6, 5.0, sides=32, bevel=0.8, label="estop_cap"))
    # cartridge tray tunnel + tray
    B.append(frame(GUNMETAL, rect(-14, 14, 98, 105), rect(-10.5, 10.5, 99, 102.5, 0.8), "x", 24, 41, bevel=0.4, label="cartridge_tunnel"))
    put(strip(face_surface("+x", 41), -8, 8, 103.4, 104.2, ION, margin=0.3))
    tray = root.child("CartridgeTray", pivot=(41.0, 0.0, 99.0), role="movable",
                      motion={"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 14, "note": "insert / eject"},
                      note="Sample cartridge slot tray")
    T = [box(GRAPHITE, 25, 41, -9.6, 9.6, 99, 101.6, bevel=0.3, label="tray")]
    for k in range(3):
        T.append(box(HAZARD, 30 + 3.4 * k, 32.6 + 3.4 * k, -6, 6, 101.6, 102.3, bevel=0.2, label="cartridge"))
    T.append(box(ALU, 41, 42.6, -6, 6, 99.4, 101.2, bevel=0.4, label="tray_pull"))
    tray.add(T)

    # ---------------------------------------------------------------- sample chamber
    ch = root.child("SampleChamber", role="static", note="Chamber frame, side glazing, rear wall, analysis head")
    C = [box(GUNMETAL, -28, 18, -32, 32, 98, 102, bevel=0.6, label="chamber_floor"),
         box(GRAPHITE, -28, -24, -32, 32, 102, 150, label="chamber_rear_wall"),
         box(GUNMETAL, -28, 18, -32, 32, 150, 154, bevel=0.6, label="chamber_roof")]
    for s in (-1, 1):
        C.append(box(ALU, 14, 18, *sorted((s * 28, s * 32)), 102, 150, bevel=0.5, label="chamber_post"))
        C.append(box(GLASS, -24, 14, *sorted((s * 30.5, s * 31.5)), 102, 150, label="chamber_side_glass"))
    C.append(cyl(ALU, (-5, 0, 145), 6.0, 10, "z", sides=24, bevel=0.6, label="analysis_head"))
    C.append(cyl(GUNMETAL, (-5, 0, 136), 1.6, 8, "z", sides=12, label="analysis_nozzle"))
    ca, ce = split_by_mats(C + [tube(ION, (-5, 0, 140.8), 7.6, 6.05, 1.2, "z", sides=24, label="head_ring")], EMISSIVE)
    ch.add(ca)
    ch.child("SampleChamber_Lights", role="emissive").add(ce)
    sa = root.child("SampleArea", role="interactive", note="Sample rack with 10 vials (pickable sample positions)")
    SA = [box(GRAPHITE, -14, 6, -20, 20, 102, 106, bevel=0.5, label="sample_rack")]
    for i in range(5):
        for j in range(2):
            y = -16 + 8 * i
            x = -9 + 10 * j
            SA.append(cyl(GLASS, (x, y, 111), 1.4, 10, "z", sides=12, label="vial"))
            SA.append(cyl(GUNMETAL, (x, y, 116.75), 1.6, 1.5, "z", sides=12, label="vial_cap"))
    SA.append(box(ION, 6, 6.4, -18, 18, 103, 105, label="rack_status_led"))
    a, e = split_by_mats(SA, EMISSIVE)
    sa.add(a, e)
    door = root.child("ChamberDoor", pivot=(16.0, 0.0, 102.0), role="movable",
                      motion={"type": "slide", "dir_ue": [0, 0, 1], "travel_cm": 40, "note": "glass door slides up behind the top housing"},
                      note="Sliding glass chamber door")
    door.add(box(GLASS, 15.5, 16.5, -27.95, 27.95, 102.4, 149.6, label="chamber_door_glass"),
             box(ALU, 16.5, 18.0, -10, 10, 104, 106, bevel=0.5, label="chamber_door_handle"),
             box(GUNMETAL, 16.5, 17.2, -27.95, 27.95, 147.6, 149.6, label="chamber_door_rail"))

    # ---------------------------------------------------------------- toed-in displays
    def display_pod(s):
        th = math.radians(20) * (-s)          # left (+Y) pod turns to face -Y slightly
        n = (math.cos(th), math.sin(th), 0.0)
        u = (math.sin(th), -math.cos(th), 0.0)
        c = (4.0, s * 56.0, 98.0)
        P = Surface(c, u, (0, 0, 1), n)
        out = [P.box(WHITE, -20, 20, 0, 56, -8, 0, bevel=1.0, label="display_pod")]
        bz, dp = screen(P, -18, 18, 6, 53, bezel=2.0, depth=1.4, chamfer=2.0)
        out += bz
        root.child("Display_L" if s > 0 else "Display_R", role="display",
                   note="Analysis display (0..1 UV on OD_MAT_Display)").add(dp)
        out += strip(P, -10, 10, 2.4, 3.4, ION, margin=0.3)
        return out
    put(display_pod(1) + display_pod(-1))

    # ---------------------------------------------------------------- top housing + rear column
    B.append(prism(WHITE, [(-34, 154), (22, 154), (22, 160), (16, 170), (-30, 170), (-34, 166)], "y", -50, 50, bevel=1.2, label="top_housing"))
    Ft = face_surface("+x", 22)
    put(strip(Ft, -24, 24, 156.6, 157.6, ION, margin=0.4))
    B.append(box(GRAPHITE, -42, -28, -40, 40, 98, 150, bevel=0.6, label="rear_service_column"))
    B.extend(vent(face_surface("-x", -42), -30, 30, 110, 140, depth=1.0, chamfer=1.5, pitch=2.0))

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_Chamber", (20.0, 0.0, 125.0), "Chamber door handle / sample access")
    root.socket("SOCKET_Interact_Cartridge", (43.0, 0.0, 100.3), "Cartridge tray pull")
    root.socket("SOCKET_Interact_EStop", Wh.at(61, -33, 5.0), "Emergency stop")
    root.socket("SOCKET_Interact_Controls", Wm.at(-40, -33, 1.2), "Mode buttons (load off / nominal / diagnostic)")
    root.socket("SOCKET_Interact_Display_L", (6.0, 56.0, 128.0), "Left display")
    root.socket("SOCKET_Interact_Display_R", (6.0, -56.0, 128.0), "Right display")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot")
    return Asset(
        name=NAME, title="Laboratory Sample Analyzer", reference="04_Laboratory_Sample_Analyzer_Ref.png",
        envelope=(160, 170, 90), pivot="floor", pivot_text="bottom-centre (floor contact)",
        root=root,
        description=("Automated sample analyzer: cabinet with vented side pods on corner feet, 0.98 m worktop with "
                     "mode buttons, selector knob, cartridge tray tunnel and mushroom e-stop; glazed sample chamber "
                     "with sliding glass door, 10-vial sample rack and an analysis head with ion ring; two toed-in "
                     "analysis displays; top housing with status strip; rear service column and hinged maintenance panel."),
        collision="Custom: cabinet box + worktop box + chamber box + top housing box (4 UCX).",
        nanite="Body Nanite ON; glass (chamber, door, vials) translucent - non-Nanite.",
        interaction=[("Sample chamber", "SOCKET_Interact_Chamber", "Door slides up 0.40 m"),
                     ("Cartridge tray", "SOCKET_Interact_Cartridge", "Slides out 0.14 m"),
                     ("Emergency stop", "SOCKET_Interact_EStop", "Immediate isolation"),
                     ("Mode buttons", "SOCKET_Interact_Controls", "Load off / nominal / diagnostic"),
                     ("Displays", "SOCKET_Interact_Display_L", "Analysis UI (L and R)")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing; 0.30 m rear clearance for the maintenance panel")],
        notes=["Reference sheet quotes 2.00 x 1.58 x 0.95 m; this follows the prototype contract 1.60 x 1.70 x 0.90 m."],
    )
