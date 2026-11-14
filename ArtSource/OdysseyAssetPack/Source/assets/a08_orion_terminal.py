"""08 OD_SYS_ORIONTerminal - ORION physical kiosk terminal (references 08B_ORION_Physical_Terminal.png, 08 sheet).

Envelope W 0.70 (Y) x H 1.55 (Z) x D 0.60 (X), pivot bottom-centre (floor). Front (+X) = user side.
Graphite tower leaning back on a weighted base; aluminium screen fascia with portrait touch display,
camera pod, speaker/mic/power band, ion status bar, hinged white service panel; rear vented hatch.
"""
from od_core import Node, box, prism, face_surface, split_by_mats, Surface, norm, mirror
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, GLASS, ION, EMISSIVE
from od_kit import strip, vent, screws, corner_screws, screen, led_row
from od_asset import Asset

NAME = "OD_SYS_ORIONTerminal"
TOWER = [(-22, 11), (20, 11), (20, 64), (9, 152), (6, 155), (-14, 155), (-22, 147)]


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Base, tower, fascia, bands, rear hatch")
    lights = root.child("StatusLights", role="emissive", note="Front ion status bar")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    B.append(box(RUBBER, -29, 29, -34, 34, 0, 1, bevel=0.3, label="base_pad"))
    B.append(box(GRAPHITE, -30, 30, -35, 35, 1, 10, bevel=2.0, label="base"))
    B.append(box(ALU, -27, 27, -32, 32, 10, 11, bevel=0.3, label="base_trim"))
    Sb = face_surface("+z", 11)                       # base trim top: u = -Y, v = -X
    B.extend(screws(Sb, [(-29, -24), (29, -24), (-29, 24), (29, 24)], r=0.8))
    B.append(prism(GRAPHITE, TOWER, "y", -29, 29, bevel=1.0, label="tower"))

    # lower front (x = 20): service panel, status bar, control band
    F = face_surface("+x", 20)
    sp = root.child("ServicePanel", pivot=F.at(26, 13, 0), role="movable",
                    motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [1, 0, 0]},
                    note="Lower service panel, hinge on the -Y edge")
    P = [F.box(WHITE, -26, 26, 13, 44, 0, 1.5, bevel=0.5, label="service_panel")]
    Ps = F.sub(0, 0, 1.5)
    P += corner_screws(Ps, -26, 26, 13, 44, inset=2.0)
    P.append(Ps.box(GRAPHITE, 8, 22, 16, 25, 0, 0.12, bevel=0.05, label="service_inlay"))
    sp.add(P)
    put(strip(F, -22, 22, 46.4, 47.6, ION))
    B.append(F.box(GUNMETAL, -26, 26, 50, 62, 0, 1.2, bevel=0.4, label="control_band"))
    C = F.sub(0, 0, 1.2)
    B.extend(vent(C, -14, 12, 52, 60, depth=0.8, chamfer=1.0, pitch=1.0))
    B.append(C.cyl(GRAPHITE, -19, 56, 1.0, 0, 0.3, sides=12, label="mic_port"))
    B.append(C.box(GRAPHITE, 16, 23, 52.5, 59.5, 0, 0.6, bevel=0.3, label="power_button_bezel"))
    pb = root.child("Control_PowerButton", pivot=C.at(19.5, 56, 0.6), role="interactive",
                    motion={"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.3]})
    pb.add(C.box(GUNMETAL, 17, 22, 53.5, 58.5, 0.6, 1.4, bevel=0.3, label="power_button"),
           C.tube(ION, 19.5, 56, 1.3, 0.9, 1.4, 1.5, sides=16, label="power_icon_ring"))

    # reclined screen face: (20, 64) -> (9, 152)
    t = norm((-11, 0, 88)); n = norm((88, 0, 11))
    S = Surface((20, 0, 64), (0, -1, 0), t, n)
    B.append(S.box(ALU, -28, 28, 0.6, 88.0, 0, 1.2, bevel=0.5, label="screen_fascia"))
    Sf = S.sub(0, 0, 1.2)
    bz, dp = screen(Sf, -25.5, 25.5, 5, 80, bezel=2.2, depth=1.2, chamfer=2.5)
    B.extend(bz)
    root.child("Screen_Main", role="display", note="Portrait touch display (0..1 UV on OD_MAT_Display)").add(dp)
    B.append(Sf.box(GRAPHITE, -6, 6, 81.5, 86.5, 0, 1.0, bevel=0.4, label="camera_pod"))
    B.append(Sf.sub(0, 0, 1.0).cyl(GLASS, 0, 84, 1.2, 0, 0.3, sides=16, label="camera_lens"))
    B.extend(screws(Sf, [(-26, 2.5), (26, 2.5), (-26, 86), (26, 86)], r=0.5))

    # side accent panels (aluminium) with gunmetal diagonal inlays
    side = []
    Ss = face_surface("+y", 29)                       # u = +X, v = Z
    side.append(Ss.prism(ALU, [(-20, 16), (14, 16), (14, 60), (-20, 96)], 0, 0.6, bevel=0.15, label="side_accent"))
    for k in range(3):
        side.append(Ss.sub(0, 0, 0.6).prism(GUNMETAL, [(-18, 66 + 6 * k), (-2, 47 + 6 * k), (-2, 49 + 6 * k), (-18, 68 + 6 * k)],
                                             0, 0.1, label="side_stripe"))
    B.extend(side)
    B.extend(mirror(side, 1))

    # rear: vented hatch + gland
    R = face_surface("-x", -22)                       # u = +Y
    B.append(R.box(GUNMETAL, -22, 22, 18, 84, 0, 1.0, bevel=0.4, label="rear_hatch"))
    Rh = R.sub(0, 0, 1.0)
    B.extend(corner_screws(Rh, -22, 22, 18, 84, inset=2.0))
    B.extend(vent(Rh, -15, 15, 58, 78, depth=0.8, chamfer=1.2, pitch=1.8))
    B.append(Rh.cyl(RUBBER, 0, 26, 3.0, 0, 1.6, sides=16, bevel=0.3, label="cable_gland"))
    B.extend(vent(R, -18, 18, 104, 136, depth=1.0, chamfer=1.6, pitch=2.0))
    put(led_row(Rh, -6, 36, 3, 6, mat=ION))

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_Screen", Sf.at(0, 42, 2), "Touch display centre (look-at / UI widget anchor)")
    root.socket("SOCKET_Interact_Power", C.at(19.5, 56, 1.5), "Power button")
    root.socket("SOCKET_User_Stand", (75.0, 0.0, 0.0), "User floor position")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot (anchor bolts through base)")
    root.socket("SOCKET_Cable_Rear", Rh.at(0, 26, 1.6), "Rear cable gland")
    return Asset(
        name=NAME, title="ORION Physical Terminal", reference="08B_ORION_Physical_Terminal.png",
        envelope=(70, 155, 60), pivot="floor", pivot_text="bottom-centre of the base (floor contact)",
        root=root,
        description=("Free-standing ORION kiosk: weighted graphite base with aluminium trim, graphite tower leaning "
                     "back 7 deg, aluminium fascia carrying a portrait touch display and camera pod, speaker / mic / "
                     "power band, ion status bar, hinged white service panel, aluminium side accents and a vented "
                     "rear hatch with cable gland."),
        collision="Simple: base box + tower convex hull (2 UCX).",
        nanite="Nanite ON for Body; display/button/panel separate.",
        interaction=[("Touch display", "SOCKET_Interact_Screen", "ORION UI render target"),
                     ("Power", "SOCKET_Interact_Power", "Press"), ("User position", "SOCKET_User_Stand", "Stand here")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing / bolted"), ("Cable", "SOCKET_Cable_Rear", "Rear")],
    )
