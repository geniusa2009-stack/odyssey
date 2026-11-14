"""09 OD_SYS_ServerRack - ORION server equipment rack (reference 09_Server_Equipment_Rack.png).

Envelope W 0.60 (Y) x H 2.10 (Z) x D 1.00 (X), pivot bottom-centre (floor). Front (+X) = sled side.
White corner pillars with ion strips around a graphite cabinet; six pull-out server sleds, a central
status display module, intake grille module, side cable conduits, hinged rear door.
"""
from od_core import Node, box, face_surface, split_by_mats, quad_mirror, mirror, rect, cyl
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, HAZARD, EMISSIVE
from od_kit import strip, vent, screws, corner_screws, screen, handle_bar, hazard_plate, led_row, chevrons
from od_asset import Asset

NAME = "OD_SYS_ServerRack"


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Frame, pillars, panels, base, modules")
    lights = root.child("StatusLights", role="emissive", note="Pillar strips, header and base lights")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    B.append(box(GRAPHITE, -38, 38, -26, 26, 0, 12, bevel=1.0, label="base"))
    q = [box(RUBBER, 39, 49, 19, 29, 0, 1, bevel=0.2, label="foot_pad"),
         box(GUNMETAL, 38, 50, 18, 30, 1, 14, bevel=1.4, label="foot"),
         box(WHITE, 44, 49.25, 24, 30, 14, 206, bevel=1.0, label="pillar")]
    Fp = face_surface("+x", 49.25)
    q += strip(Fp, -27.6, -26.4, 28, 192, ION)
    q += screws(Fp, [(-27, 18), (-27, 200)], r=0.5)
    put(quad_mirror(q))
    Sb = face_surface("+x", 38)
    put(hazard_plate(Sb, -12, 12, 3, 9, width=1.5))
    put(strip(Sb, -17, -14.5, 5.4, 6.6, ION)); put(strip(Sb, 14.5, 17, 5.4, 6.6, ION))
    B.append(box(GRAPHITE, -44, 44, -24, 24, 14, 204, label="core"))
    sides = [box(GRAPHITE, -44, 44, 24, 28, 14, 204, bevel=0.4, label="side_panel")]
    Ss = face_surface("+y", 28)                       # u = +X, v = Z
    sides += vent(Ss, -36, -16, 24, 60, depth=1.2, chamfer=1.5, pitch=2.0)
    sides.append(Ss.box(GUNMETAL, -36, -8, 120, 180, 0, 0.8, bevel=0.3, label="side_id_plate"))
    sides += corner_screws(Ss.sub(0, 0, 0.8), -36, -8, 120, 180, inset=1.6)
    for x in (4, 8, 12):                              # cable conduits on the +Y side (amber sleeves)
        for z0, z1 in ((30, 48), (52, 110), (114, 172), (176, 190)):
            sides.append(cyl(HAZARD, (x, 29.0, (z0 + z1) / 2), 1.0, z1 - z0, "z", sides=10, label="conduit"))
    for z in (50, 112, 174):
        sides.append(Ss.box(GUNMETAL, 2, 14, z - 2, z + 2, 0, 0.6, bevel=0.15, label="conduit_saddle_plate"))
    B.extend(sides)
    B.extend(mirror([s for s in sides if s.label != "conduit"], 1))
    B.append(box(GUNMETAL, -50, 50, -30, 30, 206, 210, bevel=1.2, label="top_cap"))

    F = face_surface("+x", 44)                        # front bay: u = -Y, v = Z
    B.append(F.box(GRAPHITE, -23.6, 23.6, 192, 203.6, 0, 2.0, bevel=0.4, label="header_module"))
    put(strip(F.sub(0, 0, 2.0), -12, 12, 199.4, 200.6, ION))
    B.append(F.sub(0, 0, 2.0).box(GUNMETAL, -10, 10, 193.5, 197.5, 0, 0.4, bevel=0.15, label="header_badge"))

    def sled(i, z0):
        sn = root.child(f"Sled_{i:02d}", pivot=F.at(0, z0, 0), role="movable",
                        motion={"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"},
                        note="Server sled (1 of 6)")
        P = [F.box(GRAPHITE, -23.6, 23.6, z0, z0 + 13.0, 0, 4.0, bevel=0.5, label="sled_face")]
        S = F.sub(0, 0, 4.0)
        P += vent(S, -18, 2, z0 + 2, z0 + 11, depth=0.8, chamfer=1.0, pitch=1.1, vertical=True)
        P += led_row(S, 6, z0 + 8.5, 4, 2.6, mat=ION)
        P.append(S.box(ION, 5, 15, z0 + 3.5, z0 + 4.3, 0, 0.25, label="sled_activity_bar"))
        for u in (-21.4, 21.4):
            P += handle_bar(S, z0 + 3.0, z0 + 10.0, u, standoff=0.9, r=0.55, mat=HAZARD, vertical=True)
        a, e = split_by_mats(P, EMISSIVE)
        sn.add(a, e)

    for i, z0 in enumerate((177.6, 164.2, 150.8)):
        sled(i + 1, z0)
    for i, z0 in enumerate((95.4, 82.0, 68.6)):
        sled(i + 4, z0)
    # status display module
    B.append(F.box(GUNMETAL, -23.6, 23.6, 110.0, 150.2, 0, 3.0, bevel=0.6, label="display_module"))
    D = F.sub(0, 0, 3.0)
    bz, dp = screen(D, -21, 13, 113, 147, bezel=2.0, depth=1.4, chamfer=2.0)
    B.extend(bz)
    root.child("Screen_Status", role="display", note="Rack status display (0..1 UV)").add(dp)
    B.append(D.box(GRAPHITE, 15, 21, 120, 140, 0, 1.0, bevel=0.4, label="id_reader"))
    put([D.sub(0, 0, 1.0).box(ION, 16.5, 19.5, 128, 134, 0, 0.3, bevel=0.2, label="id_reader_glow")])
    # intake module
    B.append(F.box(GRAPHITE, -23.6, 23.6, 15.0, 67.0, 0, 2.0, bevel=0.5, label="intake_module"))
    I = F.sub(0, 0, 2.0)
    B.extend(vent(I, -19, 19, 19, 56, depth=2.0, chamfer=4.0, pitch=1.6))
    put(strip(I, -10, 10, 60.4, 61.6, ION))

    # rear door (hinged on the +Y edge)
    R = face_surface("-x", -44)                       # u = +Y
    rd = root.child("RearDoor", pivot=R.at(23.6, 15, 0), role="movable",
                    motion={"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 110, "opens_toward_ue": [-1, 0, 0]},
                    note="Rear service door, hinge on the +Y edge")
    RD = [R.box(GRAPHITE, -23.6, 23.6, 15, 203.6, 0, 3.0, bevel=0.6, label="rear_door")]
    Rs = R.sub(0, 0, 3.0)
    RD += vent(Rs, -18, 18, 140, 190, depth=1.2, chamfer=2.0, pitch=2.0)
    RD += vent(Rs, -18, 18, 30, 80, depth=1.2, chamfer=2.0, pitch=2.0)
    RD += handle_bar(Rs, 95, 125, -19, standoff=1.4, r=0.8, mat=HAZARD, vertical=True)
    RD += chevrons(Rs, 6, 100, 6, mat=HAZARD)
    RD += corner_screws(Rs, -23.6, 23.6, 15, 203.6, inset=2.0)
    rd.add(RD)

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Interact_Screen", D.at(-4, 130, 1.5), "Rack status display")
    root.socket("SOCKET_Interact_IDReader", D.at(18, 131, 1.3), "Badge / ID reader")
    root.socket("SOCKET_Interact_Sled_Top", F.at(0, 184, 5), "Top sled handle line (others at 13.4 cm pitch)")
    root.socket("SOCKET_Interact_RearDoor", Rs.at(-19, 110, 3), "Rear door handle")
    root.socket("SOCKET_Mount_Floor", (0.0, 0.0, 0.0), "Floor pivot; seismic anchors through feet")
    root.socket("SOCKET_Cable_Top", (0.0, 0.0, 210.0), "Overhead cable tray drop")
    return Asset(
        name=NAME, title="Server Equipment Rack", reference="09_Server_Equipment_Rack.png",
        envelope=(60, 210, 100), pivot="floor", pivot_text="bottom-centre (floor contact under the feet)",
        root=root,
        description=("ORION Systems server rack: graphite cabinet framed by white corner pillars with ion light "
                     "strips, six pull-out server sleds with honeycomb faces, LEDs and amber handles, a central "
                     "status display module with ID reader, a lower intake grille, amber side cable conduits, "
                     "corner feet on a recessed base with hazard plate and a hinged rear door."),
        collision="Simple: one box 1.00 x 0.60 x 2.10 (UCX). Sleds: own box when pulled out.",
        nanite="Nanite ON for Body; sleds/door/display separate.",
        interaction=[("Status display", "SOCKET_Interact_Screen", "Rack health UI"),
                     ("ID reader", "SOCKET_Interact_IDReader", "Badge in"),
                     ("Server sleds", "SOCKET_Interact_Sled_Top", "Slide out 0.60 m along +X"),
                     ("Rear door", "SOCKET_Interact_RearDoor", "Opens 110 deg")],
        mounting=[("Floor", "SOCKET_Mount_Floor", "Free-standing; keep 0.9 m front and rear clearance"),
                  ("Cable", "SOCKET_Cable_Top", "Top entry")],
    )
