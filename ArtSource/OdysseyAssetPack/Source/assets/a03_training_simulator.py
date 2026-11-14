"""03 OD_TRN_TrainingSimulator - crew training simulator pod (reference 03_Training_Simulator.png).

Envelope W 3.20 (Y) x H 2.80 (Z) x D 3.80 (X), pivot bottom-centre of the plinth (floor). Front (+X) =
the open side where trainees step onto the platform. A rear wall unit (columns, header with sign display,
main simulation screen, control desk) faces +X; the trainee seat on the platform faces the screen (-X).
"""
import math

from od_core import Node, box, prism, Surface, offset_poly, ccw, face_surface, split_by_mats, norm, rot_z, cyl, tube, rect, mirror
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, GLASS, ION, AMBER, RED, HAZARD, EMISSIVE
from od_kit import (strip, vent, screws, corner_screws, screen, button, knob, fader_slot, hazard_plate, led_row,
                    chevrons, warning_triangle)
from od_asset import Asset

NAME = "OD_TRN_TrainingSimulator"
PLATFORM = [(-190, -160), (159.25, -160), (189.25, -130), (189.25, 130), (159.25, 160), (-190, 160)]
DESK = [(-140, 84), (-84, 84), (-80, 87.5), (-80, 92), (-82, 95), (-140, 106)]


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Platform, rear wall unit, columns, header, desk")
    lights = root.child("StatusLights", role="emissive", note="Platform edge, column cores, header accents")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    # ---------------------------------------------------------------- platform
    B.append(prism(GRAPHITE, PLATFORM, "z", 0, 14, bevel=1.2, label="platform"))
    Pf = face_surface("+x", 189.25)
    for u in (-90, 0, 90):
        put(strip(Pf, u - 30, u + 30, 6.4, 7.6, ION))
    Top = face_surface("+z", 14)                       # u = -Y, v = -X
    for s in (-1, 1):
        u0, u1 = sorted((s * 6, s * 140))
        B.extend(vent(Top, u0, u1, -150, -80, depth=0.8, chamfer=2.0, pitch=3.0, frame_mat=GUNMETAL,
                      back_mat=GRAPHITE, slat_mat=GUNMETAL))
    put(hazard_plate(Top, -125, 125, -184, -172, width=6.0))
    B.extend(screws(Top, [(-150, -20), (150, -20)], r=1.0, h=0.3))

    # ---------------------------------------------------------------- rear wall unit
    B.append(box(GRAPHITE, -188, -140, -110, 110, 14, 236, label="wall_core"))
    col = [box(WHITE, -188, -110, 110, 158, 14, 236, bevel=1.5, label="column")]
    Sc = face_surface("+x", -110)                      # u = -Y
    col.append(Sc.frame(GUNMETAL, rect(-150, -118, 120, 196, 4), rect(-146, -122, 124, 192, 2.5), 0, 3, bevel=0.5, label="core_window_frame"))
    col.append(Sc.prism(GRAPHITE, offset_poly(ccw(rect(-146, -122, 124, 192, 2.5)), -0.05), 0, 0.6, label="core_window_back"))
    for k in range(4):
        col.append(Sc.box(ION, -142, -126, 130 + 16 * k, 138 + 16 * k, 0.6, 2.0, bevel=0.4, label="energy_cell"))
    col += vent(Sc, -150, -118, 204, 228, depth=1.4, chamfer=1.5, pitch=2.2)
    col.append(Sc.box(WHITE, -152, -116, 22, 110, 0, 2.0, bevel=0.8, label="column_access_panel"))
    col += warning_triangle(Sc.sub(0, 0, 2.0), -134, 90, 10)
    col += corner_screws(Sc.sub(0, 0, 2.0), -152, -116, 22, 110, inset=2.5)
    col += strip(Sc, -114.6, -113.4, 30, 200, ION)
    So = face_surface("+y", 158)                       # outer side
    col += vent(So, -180, -130, 40, 120, depth=1.4, chamfer=2.0, pitch=2.4)
    col += corner_screws(So, -188, -110, 14, 236, inset=3.0)
    put(col)
    put([s for s in mirror(col, 1)])
    # header beam
    B.append(prism(WHITE, [(-190, 236), (-104, 236), (-104, 262), (-122, 280), (-190, 280)], "y", -160, 160, bevel=1.5, label="header"))
    H = face_surface("+x", -104)
    B.append(H.box(GRAPHITE, -70, 70, 240, 258, 0, 2.0, bevel=0.8, label="sign_housing"))
    bz, dp = screen(H.sub(0, 0, 2.0), -68, 68, 241.5, 256.5, bezel=1.5, depth=1.0, chamfer=1.6)
    B.extend(bz)
    root.child("Sign_Header", role="display", note="ODYSSEY Training Simulator sign (0..1 UV)").add(dp)
    for s in (-1, 1):
        put(strip(H, *sorted((s * 90, s * 140)), 248.4, 249.6, ION))
    Hb = face_surface("-z", 236)                       # underside of the header: u = -Y, v = +X
    for u in (-70, 0, 70):
        put(strip(Hb, u - 22, u + 22, -132, -126, ION, margin=0.6))
    # main simulation screen on the wall core
    W = face_surface("+x", -140)
    B.append(W.box(GUNMETAL, -108, 108, 112, 230, 0, 2.0, bevel=0.8, label="screen_surround"))
    bz, dp = screen(W.sub(0, 0, 2.0), -104, 104, 116, 226, bezel=3.0, depth=2.0, chamfer=3.0)
    B.extend(bz)
    root.child("Screen_Main", role="display", note="Main simulation screen (0..1 UV on OD_MAT_Display)").add(dp)

    # ---------------------------------------------------------------- control desk
    B.append(box(GRAPHITE, -140, -92, -100, 100, 14, 84, label="desk_body"))
    D0 = face_surface("+x", -92)
    B.append(D0.box(WHITE, -98, 98, 18, 82, 0, 3.0, bevel=0.8, label="desk_front_skin"))
    Df = D0.sub(0, 0, 3.0)
    for a, b in ((-90, -34), (-26, 26), (34, 90)):
        B.append(Df.box(WHITE, a, b, 26, 70, 0, 0.6, bevel=0.4, label="desk_panel"))
        B.extend(corner_screws(Df.sub(0, 0, 0.6), a, b, 26, 70, inset=2.0))
    put(strip(Df, -40, 40, 76.4, 77.6, ION))
    put(chevrons(Df.sub(0, 0, 0.6), 72, 32, 7, mat=GUNMETAL))
    B.append(prism(WHITE, DESK, "y", -100, 100, bevel=1.0, label="desk_top"))
    t = norm((-58, 0, 11)); n = norm((11, 0, 58))
    D = Surface((-82, 0, 95), (0, -1, 0), t, n)        # u = -Y, v = up the slope (toward the screen)
    Dm = D.sub(0, 0, 0.8)
    controls = root.child("Controls", role="group", note="Instructor / trainee desk controls")
    caps = []
    for a, b in ((-94, -56), (-50, -16), (-12, 26), (32, 64), (70, 94)):
        B.append(D.box(GRAPHITE, a, b, 4, 52, 0, 0.8, bevel=0.3, label="desk_module"))
    bz, dp = screen(Dm, -91, -59, 12, 44, bezel=1.6, depth=1.0, chamfer=1.6)
    B.extend(bz)
    root.child("Screen_Desk", role="display", note="Desk scenario display").add(dp)
    kp = knob(Dm, -40, 30, 3.4)
    L.append(kp[0])
    controls.child("Control_Knob", pivot=Dm.at(-40, 30, 0), role="interactive",
                   motion={"type": "rotate", "axis_ue": [round(c, 4) for c in Dm.n], "range_deg": [-135, 135]}).add(kp[1:])
    for u in (-46, -40, -34, -28, -22):
        bb = button(Dm, u, 14, 3.4, 2.6)
        B.append(bb[0]); caps.append(bb[1])
    for i, u in enumerate((-4, 6, 16)):
        st, cap = fader_slot(Dm, u, 28, 24)
        B.extend(st)
        a, e = split_by_mats(cap, EMISSIVE)
        controls.child(f"Control_Fader_{i + 1:02d}", pivot=Dm.at(u, 28, 0.2), role="interactive",
                       motion={"type": "slide", "dir_ue": [round(c, 4) for c in Dm.v], "range_cm": [-10.8, 10.8]}).add(a, e)
    B.extend([s for s in hazard_plate(Dm, 36, 60, 16, 42, width=2.6)])
    Dh = Dm.sub(0, 0, 0.62)
    B.append(Dh.cyl(GUNMETAL, 48, 29, 5.0, 0, 1.4, sides=28, bevel=0.3, label="estop_collar"))
    controls.child("Control_EStop", pivot=Dh.at(48, 29, 1.4), role="interactive",
                   motion={"type": "slide", "dir_ue": [round(-c, 4) for c in Dh.n], "range_cm": [0, 0.8]}).add(
        Dh.cyl(RED, 48, 29, 1.6, 1.4, 2.6, sides=16, label="estop_stem"),
        Dh.cyl(RED, 48, 29, 4.2, 2.6, 5.0, sides=32, bevel=0.7, label="estop_cap"))
    for r, v in enumerate((40, 30, 20, 10)):
        for k in range(3):
            bb = button(Dm, 76 + 7 * k, v, 4.0, 3.0, cap=AMBER if (r == 0 and k == 2) else ION)
            B.append(bb[0]); caps.append(bb[1])
    controls.child("Control_Buttons", role="interactive",
                   motion={"type": "press", "dir_ue": [round(-c, 4) for c in Dm.n], "range_cm": [0, 0.3]}).add(caps)
    put(led_row(Dm, -10, 46, 10, 3.0, mat=ION))

    # ---------------------------------------------------------------- trainee seat (faces -X, swivels)
    seat_c = (40.0, -50.0)
    R180 = rot_z(180)

    def P(solids):     # seat authored facing +X around the origin, then turned to face the screen
        return [s.xf(R180, (seat_c[0], seat_c[1], 0.0)) for s in solids]

    sb = root.child("SimSeat_Base", role="static", note="Seat pedestal on the platform")
    sb.add(P([cyl(GUNMETAL, (0, 0, 18), 26, 8, "z", sides=32, bevel=1.0, label="seat_pedestal"),
              cyl(ALU, (0, 0, 32), 9, 20, "z", sides=24, bevel=0.5, label="seat_column")]))
    lights_seat = P([tube(ION, (0, 0, 22.8), 24, 9.05, 1.6, "z", sides=32, label="pedestal_ring")])
    seat = root.child("SimSeat", pivot=(seat_c[0], seat_c[1], 42.0), role="movable",
                      motion={"type": "rotate", "axis_ue": [0, 0, 1], "range_deg": [-120, 120]},
                      note="Trainee seat (swivel); arm consoles carry the trainee controls")
    S = [cyl(GUNMETAL, (0, 0, 43.5), 16, 3, "z", sides=28, bevel=0.4, label="seat_plate"),
         box(GUNMETAL, -24, 26, -24, 24, 45, 50, bevel=0.8, label="seat_frame"),
         box(RUBBER, -12, 28, -22, 22, 50, 61, bevel=2.8, label="seat_cushion")]
    a = math.radians(10)
    Bk = Surface((-18, 0, 50), (0, -1, 0), (-math.sin(a), 0, math.cos(a)), (math.cos(a), 0, math.sin(a)))
    S += [Bk.box(GUNMETAL, -16, 16, 0.5, 70, -3, 0, bevel=0.6, label="back_frame"),
          Bk.box(WHITE, -26, 26, 4, 78, -9, -3, bevel=1.5, label="back_shell"),
          Bk.box(RUBBER, -21, 21, 8, 70, 0, 7, bevel=2.4, label="back_cushion"),
          Bk.box(WHITE, -15, 15, 78, 96, -9, 2, bevel=1.5, label="headrest_shell"),
          Bk.box(RUBBER, -12, 12, 80, 94, 2, 7, bevel=2.0, label="headrest_pad")]
    Bb = Surface(Bk.at(0, 0, -9), Bk.u, Bk.v, (-Bk.n[0], -Bk.n[1], -Bk.n[2]))   # back face of the shell
    sl = list(strip(Bb, -18.6, -17.4, 20, 60, ION, margin=0.3)) + list(strip(Bb, 17.4, 18.6, 20, 60, ION, margin=0.3))
    for s in (-1, 1):
        y0, y1 = sorted((s * 24, s * 34))
        S += [box(GUNMETAL, -6, 4, y0, y1, 45, 50, bevel=0.5, label="arm_bracket"),
              box(WHITE, -8, 26, y0, y1, 50, 68, bevel=1.5, label="arm_console"),
              box(GRAPHITE, 4, 24, *sorted((s * 25.5, s * 32.5)), 68, 69, bevel=0.3, label="arm_pad")]
        Ap = Surface((14, s * 29, 69), (0, -1, 0), (1, 0, 0), (0, 0, 1))
        for k, cap in enumerate((ION, AMBER, ION)):
            bb = button(Ap, 0, -6 + 6 * k, 3.2, 2.6, cap=cap)
            S += bb
        sl += strip(face_surface("+y" if s > 0 else "-y", s * 34), *sorted((s * -4, s * 22)), 58.4, 59.6, ION, margin=0.3)
    seat.add(P(S))
    seat.child("SimSeat_Lights", role="emissive").add(P(sl))
    lights.add(L + lights_seat)
    body.add(B)

    root.socket("SOCKET_Interact_Desk", Dm.at(0, 28, 2), "Desk controls (instructor)")
    root.socket("SOCKET_Interact_Screen", W.at(0, 171, 4), "Main simulation screen centre")
    root.socket("SOCKET_Sit_Trainee", (seat_c[0] - 8.0, seat_c[1], 61.0), "Trainee seat anchor (faces -X)")
    root.socket("SOCKET_Board", (175.0, 0.0, 14.0), "Step-on point at the platform front edge")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot (plinth bottom-centre)")
    return Asset(
        name=NAME, title="Training Simulator", reference="03_Training_Simulator.png",
        envelope=(320, 280, 380), pivot="floor", pivot_text="bottom-centre of the plinth (floor contact)",
        root=root,
        description=("Walk-on crew training simulator: 0.14 m chamfered platform with floor gratings, ion edge "
                     "lights and a hazard step edge; rear wall unit with two white columns (energy-cell windows, "
                     "vents, access panels), header beam with sign display and down-lights, a 2.1 x 1.1 m main "
                     "simulation screen, an instructor desk (desk display, knob, three faders, button banks, "
                     "e-stop) and a swivelling trainee seat with arm consoles facing the screen."),
        collision=("Custom: platform box (walkable, 0.14 m step), rear wall unit box, desk box, seat pedestal "
                   "cylinder + seat box (5 UCX)."),
        nanite="Body Nanite ON (large, many bevels). Screen/sign/seat/controls separate.",
        interaction=[("Desk", "SOCKET_Interact_Desk", "Scenario controls"),
                     ("Main screen", "SOCKET_Interact_Screen", "Simulation render target"),
                     ("Trainee seat", "SOCKET_Sit_Trainee", "Sit; seat swivels +-120 deg"),
                     ("Boarding", "SOCKET_Board", "Step onto platform")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing; needs 2.9 m ceiling clearance")],
    )
