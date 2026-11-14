"""10 OD_OBS_WindowFrame - observation deck window frame (references 10 / 10B).

Envelope W 15.0 (Y) x H 5.10 (Z) x D 0.60 (X), pivot bottom-centre of the envelope, which lies in the
glazing plane (glass centred on x = 0). +X faces the room (deck side), -X faces space.
Build steps follow the 10B sheet: base frame -> diagonal supports -> glass panes -> details & lights.
"""
from od_core import Node, prism, rect, face_surface, split_by_mats
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, GLASS, ION, AMBER, HAZARD, EMISSIVE
from od_kit import strip, vent, screws, hazard_plate, chevrons, led_row, corner_screws
from od_asset import Asset

NAME = "OD_OBS_WindowFrame"
UB, UT = 560.0, 470.0       # strut centre at the sill / head (|u|)
SILL, HEAD = 40.0, 470.0    # opening bottom / top (z)


def build():
    root = Node(NAME, (0, 0, 0), "group")
    frame_n = root.child("Frame", role="static", note="Base frame ring, deck-side and space-side details")
    lights = root.child("StatusLights", role="emissive", note="Ion/amber accent lights")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    S0 = face_surface("+x", -22)                     # u = -Y, v = Z
    outer = rect(-750, 750, 0, 510, 60)
    inner = rect(-700, 700, SILL, HEAD, 45)
    B.append(S0.frame(WHITE, outer, inner, 0, 44, bevel=1.5, label="base_frame"))

    # ---------------------------------------------------------------- supports (diagonal struts)
    sup = root.child("Supports", role="static", note="Diagonal structural supports")
    SP = []
    for s in (-1, 1):
        ub, ut = s * UB, s * UT
        SP.append(S0.prism(GUNMETAL, [(ub - 12, SILL), (ub + 12, SILL), (ut + 12, HEAD), (ut - 12, HEAD)], 10, 34,
                           bevel=1.0, label="strut"))
        for h0, h1 in ((0, 10), (34, 44)):          # white cover plates front/back of each strut
            SP.append(S0.prism(WHITE, [(ub - 9, SILL), (ub + 9, SILL), (ut + 9, HEAD), (ut - 9, HEAD)], h0, h1,
                               bevel=0.8, label="strut_cover"))
    sup.add(SP)

    # ---------------------------------------------------------------- glass (three panes in the x = 0 plane)
    gl = [("Glass_Centre", [(-UB + 12, SILL), (UB - 12, SILL), (UT - 12, HEAD), (-UT + 12, HEAD)]),
          ("Glass_Side_L", [(-700 + 45, SILL), (-UB - 12, SILL), (-UT - 12, HEAD), (-700 + 45, HEAD), (-700, HEAD - 45), (-700, SILL + 45)]),
          ("Glass_Side_R", [(UB + 12, SILL), (700 - 45, SILL), (700, SILL + 45), (700, HEAD - 45), (700 - 45, HEAD), (UT + 12, HEAD)])]
    for name, poly in gl:
        root.child(name, role="static", note="Reinforced multi-layer glazing (OD_MAT_Glass, translucent)").add(
            S0.prism(GLASS, poly, 21, 23, label="glass_pane"))
    # glazing stops: thin gunmetal beads along sill and head on both faces of the glass
    for h0, h1 in ((19, 21), (23, 25)):
        for a, b in ((-UB + 13, UB - 13), (-655, -UB - 12), (UB + 12, 655)):
            B.append(S0.box(GUNMETAL, a, b, SILL, SILL + 3, h0, h1, label="glazing_bead_sill"))
        for a, b in ((-UT + 13, UT - 13), (-655, -UT - 13), (UT + 13, 655)):
            B.append(S0.box(GUNMETAL, a, b, HEAD - 3, HEAD, h0, h1, label="glazing_bead_head"))

    # ---------------------------------------------------------------- deck side (+X face, x = 22)
    F = S0.sub(0, 0, 44)
    B.append(F.box(GRAPHITE, -130, 130, 474, 506, 0, 7, bevel=1.5, label="head_housing"))
    H = F.sub(0, 0, 7)
    put(strip(H, -90, 90, 488.8, 491.2, ION))
    B.extend(vent(H, -124, -100, 478, 502, depth=1.0, chamfer=1.5, pitch=2.0))
    B.extend(vent(H, 100, 124, 478, 502, depth=1.0, chamfer=1.5, pitch=2.0))
    for s in (-1, 1):
        for (a, b) in ((260, 380), (560, 640)):
            put(strip(F, *sorted((s * a, s * b)), 489.0, 491.0, ION))
        # sill modules with hazard plates and ion lights
        for (a, b) in ((60, 180), (300, 420)):
            u0, u1 = sorted((s * a, s * b))
            B.append(F.box(GUNMETAL, u0, u1, 6, 34, 0, 6, bevel=1.2, label="sill_module"))
            M = F.sub(0, 0, 6)
            if a == 60:
                put(hazard_plate(M, u0 + 20, u1 - 20, 12, 28, width=5.0))
            else:
                put(strip(M, u0 + 20, u1 - 20, 19, 21, ION))
            B.extend(corner_screws(M, u0, u1, 6, 34, inset=3.0, r=0.9))
        # side bands: vents + amber markers
        u0, u1 = sorted((s * 708, s * 742))
        B.extend(vent(F, u0, u1, 160, 350, depth=1.2, chamfer=2.0, pitch=3.0))
        put([F.box(AMBER, u0 + 8, u1 - 8, 380, 386, 0, 0.6, bevel=0.2, label="amber_marker"),
             F.box(AMBER, u0 + 8, u1 - 8, 124, 130, 0, 0.6, bevel=0.2, label="amber_marker")])
        put(strip(F, *sorted((s * 724.4, s * 725.6)), 400, 460, ION))
    put(led_row(F, -40, 20, 9, 10, mat=ION))
    B.extend(screws(F, [(-725, 60), (725, 60), (-720, 470), (720, 470)], r=1.2, h=0.4))

    # ---------------------------------------------------------------- space side (-X face, x = -22): ribs
    R = face_surface("-x", -22)                       # u = +Y
    for u in (-600, -300, 0, 300, 600):
        B.append(R.box(GUNMETAL, u - 10, u + 10, 2, 38, 0, 8, bevel=1.5, label="rib_sill"))
        B.append(R.box(GUNMETAL, u - 10, u + 10, 472, 508, 0, 8, bevel=1.5, label="rib_head"))
    for s in (-1, 1):
        B.append(R.box(GUNMETAL, *sorted((s * 706, s * 744)), 120, 390, 0, 8, bevel=1.5, label="rib_jamb"))

    frame_n.add(B)
    lights.add(L)
    root.socket("SOCKET_View_Centre", (40.0, 0.0, 255.0), "Look-out point / camera anchor for the deck view")
    root.socket("SOCKET_Space_Backdrop", (-500.0, 0.0, 255.0), "Place the Earth/space backdrop beyond -X")
    root.socket("SOCKET_Mount_Opening", (0.0, 0.0, 0.0), "Pivot: bottom-centre, glazing plane")
    return Asset(
        name=NAME, title="Observation Deck Window Frame", reference="10_Observation_Deck_Window.png, 10B_Observation_Window_Build_Reference.png",
        envelope=(1500, 510, 60), pivot="floor", pivot_text="bottom-centre of the envelope, in the glazing plane (x = 0)",
        root=root,
        description=("Modular observation window: 15.0 x 5.1 m chamfered white base frame (0.44 m deep), two "
                     "diagonal gunmetal supports with white covers splitting a central trapezoid pane from two "
                     "side panes, glazing beads, deck-side head housing with ion strip and vents, sill modules with "
                     "hazard plates and ion lights, jamb vents and amber markers; structural ribs on the space side."),
        collision="Custom: frame as 4 boxes (sill, head, jambs) + 2 strut boxes; glass: one blocking box per pane.",
        nanite=("Frame/Supports: Nanite ON. Glass is translucent: not Nanite. Very large asset - split into "
                "3 m modules in-engine if lightmap density is a concern."),
        interaction=[("View", "SOCKET_View_Centre", "Observation look-at")],
        mounting=[("Wall opening", "SOCKET_Mount_Opening", "Fits a 15.0 x 5.1 m cut; frame 0.44 m deep, ribs to 0.60 m")],
        notes=["Reference sheet example is 6.0 x 2.4 x 0.5 m; this follows the contract 15.0 x 5.10 x 0.60 m with the same build steps."],
    )
