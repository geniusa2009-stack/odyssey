"""01 OD_ENG_PowerConsole - Engineering power distribution console (reference 01_Power_Console.png).

Envelope W 1.80 (Y) x H 1.25 (Z) x D 0.90 (X), pivot bottom-centre (floor). Front (+X) = operator.
Seated-height desk (front edge 0.74 m) under a 9.7 deg reclined display face; side equipment pods
with recessed vents; bolted rear service hatch, cable gland plate and rear exhaust grille.
"""
from od_core import (Node, offset_poly, ccw, Surface, box, prism, frame, rect, chamfer_poly, face_surface, side_surface, mirror_y,
                     split_by_mats, norm, mul, add)
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, DISPLAY, ION, AMBER, RED, HAZARD, EMISSIVE
from od_kit import (screws, corner_screws, strip, vent, hazard_plate, chevrons, button, knob, toggle, fader_slot,
                    screen, recessed_handle, warning_triangle, led_row)
from od_asset import Asset

NAME = "OD_ENG_PowerConsole"

# key profile numbers (cm)
DESK_POLY = [(0, 62), (41, 62), (45, 65.5), (45, 71), (43, 74), (0, 84)]           # (x, z), extruded along Y
HOUSING_POLY = [(-42, 62), (0, 62), (0, 84), (-6, 119), (-9, 122), (-40, 122), (-42, 120)]


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Static shell, desk, housing, bezels, vents, control bases")
    lights = root.child("StatusLights", role="emissive", note="Ion/amber/red status strips and LEDs (drive EmissiveScale)")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    # ------------------------------------------------------------------ base: rubber pads, feet, recessed plinth
    B.append(box(GRAPHITE, -36, 30, -80, 80, 0, 7, bevel=0.8, label="plinth"))
    side_parts = []
    for (x0, x1) in ((30, 45), (-45, -36)):
        side_parts.append(box(RUBBER, x0 + 1, x1 - 1, 63, 89, 0, 1, bevel=0.2, label="foot_pad"))
        side_parts.append(box(GUNMETAL, x0, x1, 62, 90, 1, 10, bevel=1.2, label="foot"))
    # ------------------------------------------------------------------ side pods (built for +Y, mirrored)
    side_parts.append(box(GUNMETAL, -40, 30, 60, 88, 10, 62, label="pod_core"))
    So = face_surface("+y", 88)                       # outer side face: u = +X, v = +Z, n = +Y
    side_parts.append(So.frame(WHITE, rect(-40, 30, 10, 62, [0, 0, 4, 0]), rect(-31, 17, 18, 54, [0, 0, 2, 0]), 0, 1.75,
                               bevel=0.5, label="pod_side_skin"))
    side_parts += vent(So, -30.6, 16.6, 18.4, 53.6, h0=0, depth=1.6, chamfer=1.5, pitch=2.6)
    side_parts += corner_screws(So, -40, 30, 10, 62, inset=2.4, h0=1.75)
    Sf = face_surface("+x", 30)                       # pod front: u = -Y (viewer's right), v = +Z
    side_parts.append(Sf.frame(WHITE, rect(-90, -60, 10, 62, [0, 0, 0, 3]), rect(-84, -66, 14, 56, [0, 0, 0, 1.2]), 0, 2,
                               bevel=0.5, label="pod_front_skin"))
    side_parts += vent(Sf, -83.6, -66.4, 14.4, 42, h0=0, depth=1.6, chamfer=0.8, pitch=2.4)
    side_parts.append(Sf.box(GRAPHITE, -83.2, -66.4, 42.4, 55.2, 0, 0.8, bevel=0.2, label="pod_tag_plate"))
    side_parts += warning_triangle(Sf, -75, 49, 6.0, h0=0.8)
    side_parts += strip(Sf, -63.6, -62.4, 18, 56, ION, h0=2)
    side_parts += corner_screws(Sf, -90, -60, 10, 62, inset=1.6, h0=2)
    Sr = face_surface("-x", -40)                      # pod rear: u = +Y, v = +Z, n = -X
    side_parts.append(Sr.box(WHITE, 60, 88, 10, 62, 0, 1.5, bevel=0.4, label="pod_rear_panel"))
    side_parts += vent(Sr, 64, 84, 34, 56, h0=1.5, depth=1.2, chamfer=1.0, pitch=2.2)
    side_parts += corner_screws(Sr, 60, 88, 10, 62, inset=2.0, h0=1.5)
    put(side_parts)
    put(mirror_y(side_parts))

    # ------------------------------------------------------------------ lower centre body + service bay surround
    B.append(box(GRAPHITE, -38, 22, -60, 60, 7, 62, label="lower_core"))
    Sc = face_surface("+x", 22)
    B.append(Sc.frame(GUNMETAL, rect(-60, 60, 7, 62), rect(-55, 55, 11, 58, 1.0), 0, 3, bevel=0.4, label="service_surround"))
    put(strip(Sc, -26, 26, 59.4, 60.6, ION, h0=3))
    # rear: bolted hatch in a gunmetal surround, gland plate, exhaust vent
    Sb = face_surface("-x", -38)                      # u = +Y, v = +Z, n = -X
    B.append(Sb.frame(GUNMETAL, rect(-60, 60, 7, 62), rect(-54, 54, 12, 57, 1.0), 0, 2, bevel=0.4, label="rear_surround"))
    B.append(Sb.box(WHITE, -53.6, 53.6, 12.4, 56.6, 0, 1.6, bevel=0.5, label="rear_hatch"))
    Sh = Sb.sub(0, 0, 1.6)
    B.extend(corner_screws(Sh, -53.6, 53.6, 12.4, 56.6, inset=2.2))
    B.extend(vent(Sh, -30, 30, 34, 52, depth=1.2, chamfer=1.2, pitch=2.2))
    B.append(Sh.box(GRAPHITE, -24, 24, 15, 27, 0, 0.6, bevel=0.2, label="gland_plate"))
    for k in range(4):
        u = -16 + k * 10.6
        B.append(Sh.cyl(RUBBER, u, 21, 2.6, 0.6, 2.2, sides=16, bevel=0.3, label="cable_gland"))
        B.append(Sh.cyl(GUNMETAL, u, 21, 1.4, 2.2, 2.6, sides=12, label="gland_nut"))
    put(chevrons(Sh, 38, 16, 6, h0=0, mat=GUNMETAL))
    put(led_row(Sh, 40, 50, 3, 2.4, mat=ION))

    # ------------------------------------------------------------------ service panel (hinged door)
    sp = root.child("ServicePanel", pivot=(25.0, -54.6, 11.4), role="movable",
                    motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 95, "opens_toward_ue": [1, 0, 0],
                            "note": "free edge (+Y) swings out toward +X"},
                    note="Front service door, hinge on the -Y edge")
    S_door = Sc.sub(0, 0, 0)
    door = [S_door.box(WHITE, -54.6, 54.6, 11.4, 57.6, 0, 3.0, bevel=0.6, label="service_door")]
    Sd = Sc.sub(0, 0, 3.0)
    door += recessed_handle(Sd, -47, 36, 4.2, 13)
    door += chevrons(Sd, 36, 15, 6.5, mat=GUNMETAL)
    door += corner_screws(Sd, -54.6, 54.6, 11.4, 57.6, inset=2.2)
    door.append(Sd.box(GRAPHITE, -30, 30, 44, 45.2, 0, 0.15, label="door_seam_inlay"))
    sp.add(door)

    # ------------------------------------------------------------------ desk (sloped control surface)
    B.append(prism(WHITE, DESK_POLY, "y", -88, 88, bevel=1.0, label="desk"))
    Sl = face_surface("+x", 45)                       # desk front lip
    # desk top frame: origin at the front-top edge, u = -Y, v = uphill, n = surface normal
    t = norm((-43, 0, 10))
    n = norm((10, 0, 43))
    D = Surface((43, 0, 74), (0, -1, 0), t, n)
    mods = {"M1": (-84, -56), "M2": (-53, -21), "M3": (-18, 18), "M4": (21, 53), "M5": (56, 84)}
    for k, (u0, u1) in mods.items():
        B.append(D.box(GRAPHITE, u0, u1, 4, 38, 0, 0.8, bevel=0.3, label=f"module_{k}"))
    Dm = D.sub(0, 0, 0.8)
    controls = root.child("Controls", role="group", note="Interactive desk controls; caps/levers are separate nodes")
    btn_static, btn_caps = [], []

    def btn(u, v, w=2.6, h=2.0, cap=ION):
        bb = button(Dm, u, v, w, h, cap)
        btn_static.append(bb[0]); btn_caps.append(bb[1])

    # M1: selector knob, two buttons, guarded toggle, LEDs
    for i, (u, v) in enumerate([(-79, 30), (-79, 24)]):
        btn(u, v)
    def knob_node(name, u, v, r):
        kp = Dm.at(u, v, 0)
        kn = controls.child(name, pivot=kp, role="interactive",
                            motion={"type": "rotate", "axis_ue": [round(c, 4) for c in Dm.n], "range_deg": [-135, 135]})
        parts = knob(Dm, u, v, r)
        kn.add(parts[1:])
        L.append(parts[0])
    knob_node("Control_Knob_01", -65, 22, 2.8)
    def toggle_node(name, u, v):
        parts = toggle(Dm, u, v)
        piv = Dm.at(u, v, 0.95)
        tn = controls.child(name, pivot=piv, role="interactive",
                            motion={"type": "hinge", "axis_ue": [round(c, 4) for c in Dm.u], "range_deg": [-40, 40]})
        tn.add([p for p in parts if p.label == "toggle_lever"])
        B.extend([p for p in parts if p.label != "toggle_lever"])
    toggle_node("Control_Toggle_01", -77, 13)
    L.extend(led_row(Dm, -70, 34, 4, 2.4, mat=ION))
    # M2: button grid with two red interlocks and two toggles
    for u in (-46, -37, -28):
        btn(u, 31)
    toggle_node("Control_Toggle_02", -47, 21)
    toggle_node("Control_Toggle_03", -41, 21)
    btn(-33, 21, cap=RED); btn(-26, 21, cap=RED)
    for u in (-48, -40, -32, -24):
        btn(u, 10, w=2.8, h=2.2)
    # M3: three faders (bus load setpoints)
    for i, u in enumerate((-9, 0, 9)):
        st, cap = fader_slot(Dm, u, 21, 20)
        B.extend(st)
        fn = controls.child(f"Control_Fader_{i + 1:02d}", pivot=Dm.at(u, 21, 0.2), role="interactive",
                            motion={"type": "slide", "dir_ue": [round(c, 4) for c in Dm.v], "range_cm": [-8.8, 8.8]})
        fa, fe = split_by_mats(cap, EMISSIVE)
        fn.add(fa, fe)
    L.extend(led_row(Dm, -12, 35, 9, 3.0, mat=ION))
    btn(-12, 7, w=3.0, h=1.8); btn(12, 7, w=3.0, h=1.8, cap=AMBER)
    # M4: two rotary selectors + button pairs
    knob_node("Control_Knob_02", 31, 26, 2.4)
    knob_node("Control_Knob_03", 44, 26, 2.4)
    for u in (27, 33, 39, 45):
        btn(u, 14, w=2.6, h=1.8)
        btn(u, 8.5, w=2.6, h=1.8, cap=ION if u != 45 else AMBER)
    # M5: emergency stop (mushroom, press-to-latch) on hazard plate + isolation buttons
    B.extend([s for s in hazard_plate(Dm, 59, 81, 13, 35, n=None, width=2.2) if s.mat not in EMISSIVE])
    Dh = Dm.sub(0, 0, 0.62)
    B.append(Dh.cyl(GUNMETAL, 70, 24, 4.6, 0, 1.4, sides=28, bevel=0.3, label="estop_collar"))
    es = controls.child("Control_EStop", pivot=Dh.at(70, 24, 1.4), role="interactive",
                        motion={"type": "slide", "dir_ue": [round(-c, 4) for c in Dh.n], "range_cm": [0, 0.8],
                                "note": "press to latch, twist to release"})
    es.add(Dh.cyl(RED, 70, 24, 1.6, 1.4, 2.6, sides=16, label="estop_stem"),
           Dh.cyl(RED, 70, 24, 3.8, 2.6, 4.8, sides=32, bevel=0.7, label="estop_cap"))
    btn(63, 8, w=2.6, h=1.8, cap=RED); btn(70, 8, w=2.6, h=1.8, cap=RED)
    L.extend(led_row(Dm, 76, 8, 2, 2.6, mat=AMBER))
    B.extend(btn_static)
    cb = controls.child("Control_Buttons", role="interactive",
                        motion={"type": "press", "dir_ue": [round(-c, 4) for c in Dm.n], "range_cm": [0, 0.3]},
                        note="All momentary button caps (one node; press = translate -n 0.3 cm per cap in code/BP)")
    cb.add(btn_caps)

    # ------------------------------------------------------------------ upper display housing
    B.append(prism(WHITE, HOUSING_POLY, "y", -84, 84, bevel=1.2, label="display_housing"))
    # top vent cap (real recess) and a small corner grille
    St = face_surface("+z", 122)                      # u = -Y, v = -X (away from operator)
    B.append(St.frame(GUNMETAL, rect(-30, 30, 14, 34, 1.5), rect(-27, 27, 16.5, 31.5, 0.8), 0, 3, bevel=0.4, label="top_vent_cap"))
    B.append(St.prism(GRAPHITE, offset_poly(ccw(rect(-27, 27, 16.5, 31.5, 0.8)), -0.05), 0, 0.4, label="top_vent_floor"))
    for k in range(9):
        u = -24 + k * 6
        B.append(St.box(GUNMETAL, u - 0.6, u + 0.6, 17.3, 30.7, 0.4, 2.6, bevel=0.15, label="top_vent_fin"))
    B.extend(vent(St, -78, -62, 16, 30, depth=1.0, chamfer=1.0, pitch=2.0))
    # housing side faces: recessed vent + screws
    for side, plane in (("+y", 84), ("-y", -84)):
        Ss = face_surface(side, plane)
        u0, u1 = (-36, -14) if side == "+y" else (14, 36)
        B.extend(vent(Ss, u0, u1, 90, 112, depth=1.2, chamfer=1.5, pitch=2.2))
        B.extend(screws(Ss, [(u0 - 2.5, 68), (u1 + 2.5, 68)]))
    # housing rear: exhaust grille + nameplate
    Shr = face_surface("-x", -42)
    B.extend(vent(Shr, -50, 50, 88, 112, depth=1.5, chamfer=2.0, pitch=2.4))
    B.append(Shr.box(GRAPHITE, -14, 14, 70, 80, 0, 0.5, bevel=0.2, label="rear_nameplate"))
    B.extend(corner_screws(Shr, -14, 14, 70, 80, inset=1.5, h0=0.5, r=0.45))
    B.extend(screws(Shr, [(-70, 66), (70, 66), (-70, 116), (70, 116)]))

    # ------------------------------------------------------------------ display face
    tf = norm((-6, 0, 35))
    nf = norm((35, 0, 6))
    F = Surface((0, 0, 84), (0, -1, 0), tf, nf)      # u = -Y, v = up the reclined face
    bz, dp = screen(F, -46, 44, 3, 33, h0=0, bezel=2.2, depth=1.6, chamfer=2.0)
    B.extend(bz)
    root.child("Screen_Main", role="display", note="Main bus schematic display (0..1 UV on OD_MAT_Display)").add(dp)
    put(strip(F, -16, 16, 33.7, 34.3, ION, h0=0, margin=0.3))   # header strip above the main screen

    def side_pod(name, ua, ub, v0, v1, toe, outer_is_low_u):
        """Display pod: wedge (toe-in) + bezel + display; ua/ub = u extent on the face."""
        w = ub - ua
        import math
        rise = w * math.tan(math.radians(toe))
        if outer_is_low_u:   # left pod: outer edge at ua lifts
            wedge = [(ua, 0), (ub, 0), (ua, rise)]
        else:
            wedge = [(ua, 0), (ub, 0), (ub, rise)]
        W = side_surface(F)                           # polygon in (u, n), extruded along -v
        B.append(W.prism(WHITE, wedge, -v1, -v0, bevel=0.6, label=f"{name}_wedge"))
        hyp = math.hypot(w, rise)
        if outer_is_low_u:
            o = F.at(ua, v0, rise)
            u_dir = norm(add(mul(F.u, w), mul(F.n, -rise)))
        else:
            o = F.at(ua, v0, 0)
            u_dir = norm(add(mul(F.u, w), mul(F.n, rise)))
        n_dir = norm(add(mul(F.n, w), mul(F.u, rise if outer_is_low_u else -rise)))
        P = Surface(o, u_dir, F.v, n_dir)
        bzz, dpp = screen(P, 0.8, hyp - 0.8, 0.8, (v1 - v0) - 0.8, h0=0, bezel=2.0, depth=1.5, chamfer=1.6)
        B.extend(bzz)
        root.child(name, role="display", note="Side status display (0..1 UV on OD_MAT_Display)").add(dpp)
        return P

    side_pod("Screen_Left", -82, -49, 1.5, 33.5, 14, True)
    side_pod("Screen_Right", 48, 80, 7, 28, 12, False)

    body.add(B)
    lights.add(L)

    # ------------------------------------------------------------------ sockets (interaction + mounting)
    root.socket("SOCKET_Interact_MainScreen", F.at(-1, 18, 0.6), "Look-at / focus point of the main display")
    root.socket("SOCKET_Interact_Desk", D.at(0, 20, 1.0), "Hand/IK target over the fader bank")
    root.socket("SOCKET_Interact_EStop", Dh.at(70, 24, 4.8), "E-stop cap top")
    root.socket("SOCKET_Interact_ServicePanel", (25.0, 47.0, 36.0), "Service door pull")
    root.socket("SOCKET_Operator_Stand", (95.0, 0.0, 0.0), "Operator floor position (seated chair or standing)")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor mount = pivot")
    root.socket("SOCKET_Cable_Rear", Sh.at(0, 21, 2.6), "Rear cable gland plate (power feed in)")

    return Asset(
        name=NAME, title="Power Console (Engineering)", reference="01_Power_Console.png",
        envelope=(180, 125, 90), pivot="floor", pivot_text="bottom-centre of the envelope (floor contact)",
        root=root,
        description=("Free-standing engineering power distribution console. Seated-height sloped control desk "
                     "(front edge 0.74 m) with five control modules: selector knob bank, interlock buttons, three "
                     "bus-load faders, dual rotary selectors and a mushroom emergency stop on a hazard plate. "
                     "Reclined main schematic display flanked by toed-in status displays. Side equipment pods with "
                     "recessed intake vents; hinged front service door; bolted rear hatch with cable glands and a "
                     "rear exhaust grille."),
        collision=("Custom: 4 convex hulls (UCX) - plinth+lower body box (0.90 x 1.80 x 0.62), desk wedge, "
                   "display housing prism, rear feet. Controls: no collision; use per-control trigger boxes for "
                   "interaction traces. ServicePanel: own simple box when opened."),
        nanite=("Body: Nanite ON (dense bevels/screws, static). Screens, controls, ServicePanel, StatusLights: "
                "Nanite optional (low poly, movable/emissive) - keep them as separate static mesh components."),
        interaction=[("Main display", "SOCKET_Interact_MainScreen", "Bus schematic UI; render target on OD_MAT_Display"),
                     ("Desk controls", "SOCKET_Interact_Desk", "Knobs rotate, faders slide, toggles flip, buttons press"),
                     ("Emergency stop", "SOCKET_Interact_EStop", "Press to latch; drives emergency state"),
                     ("Service door", "SOCKET_Interact_ServicePanel", "Hinged maintenance access")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing; pivot on floor, 4 feet with rubber pads"),
                  ("Cable feed", "SOCKET_Cable_Rear", "Rear gland plate; leave >= 0.30 m rear clearance")],
    )
