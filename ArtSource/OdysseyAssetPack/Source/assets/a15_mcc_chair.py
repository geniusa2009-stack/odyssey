"""15 OD_MCC_MissionControlChair - mission control operator chair (reference 15_Mission_Control_Chair.png).

Envelope W 0.70 (Y) x H 1.20 (Z) x D 0.70 (X), pivot bottom-centre (floor). Front (+X) = where the
operator's knees point. Hierarchy: Base (static) -> Swivel (rotate Z) -> Seat, Backrest (recline hinge),
Arm_L / Arm_R (flip-up hinges) with arm control pads, Footrest (fold hinge).
Seat height 0.48 m, armrests 0.645 m, backrest reclined 8 deg, headrest top 1.20 m.
"""
import math

from od_core import Node, box, cyl, tube, Surface, face_surface, split_by_mats, mirror
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, AMBER, DISPLAY, EMISSIVE
from od_kit import strip, button, knob, led_row, screws
from od_asset import Asset

NAME = "OD_MCC_MissionControlChair"
RECLINE = 8.0
HINGE = (-14.0, 0.0, 38.0 + 2.0 * math.cos(math.radians(15)))


def build():
    root = Node(NAME, (0, 0, 0), "group")
    base = root.child("Base", role="static", note="Four-arm floor base, hub, column (does not swivel)")
    lights = root.child("StatusLights", role="emissive", note="Base arm lights and column ring")
    BB, L = [], []

    # ---------------------------------------------------------------- base
    BB.append(cyl(GUNMETAL, (0, 0, 4), 12, 8, "z", sides=16, bevel=1.0, label="hub"))
    ap = 12 * math.cos(math.pi / 16)
    arm = [box(GUNMETAL, ap, 33, -5, 5, 0, 7, bevel=1.2, label="base_arm"),
           box(ALU, 14, 30, -3.5, 3.5, 7, 7.8, bevel=0.3, label="base_arm_cap"),
           box(RUBBER, 33, 35, -4, 4, 0, 6, bevel=0.4, label="base_arm_foot")]
    S = face_surface("+y", 5)
    arm_e = strip(S, 18, 30, 2.8, 4.2, ION, margin=0.4)
    arms = arm + arm_e
    for k in range(4):
        R = ((math.cos(k * math.pi / 2), -math.sin(k * math.pi / 2), 0), (math.sin(k * math.pi / 2), math.cos(k * math.pi / 2), 0), (0, 0, 1))
        for s in arms:
            ss = s.xf(R)
            (L if ss.mat in EMISSIVE else BB).append(ss)
    BB.append(cyl(ALU, (0, 0, 19), 7, 22, "z", sides=24, bevel=0.4, label="column"))
    L.append(tube(ION, (0, 0, 24), 9.0, 7.05, 1.6, "z", sides=24, label="column_ring"))
    base.add(BB)

    # ---------------------------------------------------------------- swivel assembly
    sw = root.child("Swivel", pivot=(0.0, 0.0, 30.0), role="movable",
                    motion={"type": "rotate", "axis_ue": [0, 0, 1], "range_deg": [-180, 180]},
                    note="Everything above the column swivels 360 deg")
    seat = sw.child("Seat", role="static", note="Seat frame, side covers, cushion")
    SS, SL = [], []
    SS.append(cyl(GUNMETAL, (0, 0, 31.5), 14, 3, "z", sides=24, bevel=0.4, label="swivel_plate"))
    SS.append(box(GUNMETAL, -20, 24, -20, 20, 33, 38, bevel=0.6, label="seat_frame"))
    SS.append(box(RUBBER, -6, 27, -20, 20, 38, 48, bevel=2.5, label="seat_cushion"))
    side = [box(WHITE, -12, 24, 20, 23, 33, 46, bevel=0.8, label="seat_side_cover")]
    side += strip(face_surface("+y", 23), 4, 18, 39.4, 40.6, ION, margin=0.4)
    side.append(box(GUNMETAL, -8, 0, 23, 26, 34, 40, bevel=0.4, label="arm_bracket"))
    for s in side + mirror(side, 1):
        (SL if s.mat in EMISSIVE else SS).append(s)
    SS.append(cyl(ALU, HINGE, 2.0, 36, "y", sides=12, label="recline_hinge"))
    seat.add(SS)
    sw.child("Seat_Lights", role="emissive").add(SL)

    # ---------------------------------------------------------------- backrest (recline about the hinge axis)
    a = math.radians(RECLINE)
    V = (-math.sin(a), 0.0, math.cos(a))
    N = (math.cos(a), 0.0, math.sin(a))
    Bk = Surface(HINGE, (0, -1, 0), V, N)
    back = sw.child("Backrest", pivot=HINGE, role="movable",
                    motion={"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 22], "opens_toward_ue": [-1, 0, 0],
                            "note": "recline (rest pose = 8 deg)"})
    BK, BL = [], []
    BK.append(Bk.box(GUNMETAL, -16, 16, 1.95, 62, -2, 1, bevel=0.5, label="back_frame"))
    BK.append(Bk.box(WHITE, -22, 22, 4, 60, -6, -2, bevel=1.2, label="back_shell"))
    BK.append(Bk.box(RUBBER, -19, 19, 6, 60, 1, 7, bevel=2.2, label="back_cushion"))
    for s in (-1, 1):
        BK.append(Bk.box(RUBBER, *sorted((s * 19, s * 23)), 8, 52, 1, 9, bevel=1.5, label="back_bolster"))
        BL.extend(strip(Bk.sub(0, 0, 7), s * 13 - 0.4, s * 13 + 0.4, 18, 48, ION, margin=0.3))
    # headrest: solve its top so the assembly is exactly 1.20 m tall
    def headrest(vt):
        return [Bk.box(WHITE, -14, 14, 62, vt, -2, 2, bevel=1.0, label="headrest_shell"),
                Bk.box(RUBBER, -12, 12, 63, vt - 1.0, 2, 7, bevel=2.0, label="headrest_pad")]
    lo, hi = 70.0, 90.0
    for _ in range(40):
        mid = (lo + hi) / 2
        top = max(s.bounds()[1][2] for s in headrest(mid))
        lo, hi = (mid, hi) if top < 120.0 else (lo, mid)
    BK += headrest((lo + hi) / 2)
    back.add(BK)
    back.child("Backrest_Lights", role="emissive").add(BL)

    # ---------------------------------------------------------------- arms (flip up about Y at the post base)
    def arm_struct():
        return [box(ALU, -6, -1, 24, 28, 40, 60, bevel=0.5, label="arm_post"),
                box(GRAPHITE, -6, 22, 23, 33, 60, 64.5, bevel=1.2, label="arm_pad")]
    for nm, s in (("Arm_L", 1), ("Arm_R", -1)):
        an = sw.child(nm, pivot=(-3.5, s * 26.0, 40.0), role="movable",
                      motion={"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 80, "opens_toward_ue": [0, 0, 1],
                              "note": "armrest flips up for ingress"})
        parts = arm_struct()
        if s < 0:
            parts = mirror(parts, 1)
        T = Surface((0, s * 28, 64.5), (0, -1, 0), (1, 0, 0), (0, 0, 1))   # pad top: u = -Y, v = +X
        parts.append(T.box(GUNMETAL, -4.6, 4.6, 2, 20, 0, 0.6, bevel=0.2, label="arm_control_plate"))
        C = T.sub(0, 0, 0.6)
        ctl = an.child(f"{nm}_Controls", role="interactive", note="Arm control pad (buttons/knob/display)")
        cparts = []
        if s > 0:   # left arm: rotary selector + buttons
            cparts += knob(C, 0, 14, 1.8)
            for v in (5.5, 8.5):
                cparts += button(C, -2.2, v, 2.0, 1.6) + button(C, 2.2, v, 2.0, 1.6, cap=AMBER if v > 7 else ION)
        else:       # right arm: small display + buttons
            from od_kit import screen
            bz, dp = screen(C, -3.6, 3.6, 9, 19, bezel=0.8, depth=0.8, chamfer=0.8)
            cparts += bz
            an.child("Arm_R_Display", role="display").add(dp)
            cparts += button(C, -2.0, 5.5, 2.4, 1.6) + button(C, 2.0, 5.5, 2.4, 1.6, cap=AMBER)
        ca, ce = split_by_mats(cparts, EMISSIVE)
        ctl.add(ca, ce)
        side_face = face_surface("+y" if s > 0 else "-y", s * 33)
        k = 1 if s > 0 else -1
        e = strip(side_face, *sorted((k * 2, k * 18)), 61.6, 62.9, ION, margin=0.3)
        pa, pe = split_by_mats(parts + e, EMISSIVE)
        an.add(pa, pe)

    # ---------------------------------------------------------------- footrest (folds up about Y at the seat frame)
    fr = sw.child("Footrest", pivot=(25.0, 0.0, 36.0), role="movable",
                  motion={"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 75], "opens_toward_ue": [0, 0, 1],
                          "note": "folds up under the seat front"})
    FR = [box(GUNMETAL, 24, 26, -12, 12, 16, 36, bevel=0.5, label="footrest_strut"),
          box(GRAPHITE, 26, 35, -16, 16, 14, 17, bevel=0.8, label="footplate")]
    Ft = face_surface("+z", 17)                     # u = -Y, v = -X
    for u in (-10, -5, 0, 5, 10):
        FR.append(Ft.box(RUBBER, u - 1.4, u + 1.4, -33.5, -27.5, 0, 0.5, bevel=0.2, label="tread"))
    FR += strip(Ft, -12, 12, -34.3, -33.9, ION, margin=0.3)
    fa, fe = split_by_mats(FR, EMISSIVE)
    fr.add(fa, fe)

    lights.add(L)
    root.socket("SOCKET_Sit", (6.0, 0.0, 48.0), "Seated pelvis anchor (seat top)")
    root.socket("SOCKET_Interact_ArmL", (12.0, 28.0, 66.0), "Left arm control pad")
    root.socket("SOCKET_Interact_ArmR", (12.0, -28.0, 66.0), "Right arm display pad")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot")
    return Asset(
        name=NAME, title="Mission Control Chair", reference="15_Mission_Control_Chair.png",
        envelope=(70, 120, 70), pivot="floor", pivot_text="bottom-centre (floor contact)",
        root=root,
        description=("Operator chair: four-arm floor base with ion arm lights and an aluminium column, 360 deg "
                     "swivel assembly carrying a padded seat (0.48 m), reclining backrest with bolsters and "
                     "headrest, flip-up armrests with control pads (left: selector + buttons; right: mini display "
                     "+ buttons) and a folding footrest with rubber treads."),
        collision="Custom: base cylinder (r 0.35, h 0.30) + seat box + backrest box (3 UCX). Arms/footrest: none.",
        nanite="Nanite optional (~5k tris). Keep Swivel/Backrest/Arms/Footrest as separate components for animation.",
        interaction=[("Sit", "SOCKET_Sit", "Seat anchor; Swivel yaw follows the operator"),
                     ("Left arm pad", "SOCKET_Interact_ArmL", "Selector and buttons"),
                     ("Right arm pad", "SOCKET_Interact_ArmR", "Mini display and buttons")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing on four arms")],
    )
