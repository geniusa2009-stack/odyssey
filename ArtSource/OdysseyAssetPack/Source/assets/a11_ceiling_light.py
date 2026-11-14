"""11 OD_ENV_CeilingLight - standard 2.0 m linear ceiling light module (reference 11_Ceiling_Light_Module_Reference.png).

Envelope L 2.00 (X) x W 0.50 (Y) x H 0.14 (Z), pivot top-centre (ceiling flush, z in [-14, 0]).
Matches SM_PROXY_CeilingLight_Linear (200 x 50 x 14). The diffuser and ion strips are emissive and are
meant to be driven by AOdysseyLightFixture (EmissiveScale) together with a rect light at SOCKET_Light.
"""
from od_core import Node, box, prism, face_surface, split_by_mats, rect, offset_poly, ccw, mirror
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, ION, HAZARD, DIFFUSER, EMISSIVE
from od_kit import strip, vent, corner_screws, screws, hazard_plate
from od_asset import Asset

NAME = "OD_ENV_CeilingLight"
HOUSING = [(-24, -1), (24, -1), (24, -7), (20, -11), (-20, -11), (-24, -7)]       # (y, z)
CAP = [(-25, -1), (25, -1), (25, -7.5), (20.5, -12), (-20.5, -12), (-25, -7.5)]


def build():
    root = Node(NAME, (0, 0, 0), "group")
    body = root.child("Body", role="static", note="Housing, end caps, bezel, brackets")
    lights = root.child("StatusLights", role="emissive", note="Ion edge strips (state colour via material instance)")
    B, L = [], []

    def put(solids):
        a, e = split_by_mats(solids, EMISSIVE)
        B.extend(a); L.extend(e)

    B.append(prism(WHITE, HOUSING, "x", -94, 94, bevel=0.8, label="housing"))
    for s in (-1, 1):
        x0, x1 = sorted((s * 94, s * 100))
        B.append(prism(GUNMETAL, CAP, "x", x0, x1, bevel=0.8, label="end_cap"))
        B.append(box(GUNMETAL, s * 62, s * 78, -10, 10, -1, 0, bevel=0.2, label="ceiling_bracket"))
    # bracket bolts sit on the bracket underside? no - on the housing top beside the brackets
    Sb = face_surface("-z", -11)                       # underside: u = -Y, v = +X
    B.append(Sb.frame(GRAPHITE, rect(-19, 19, -88, 88, 4), rect(-15, 15, -83, 83, 3), 0, 3.0, bevel=0.4, label="diffuser_bezel"))
    B.append(Sb.prism(GRAPHITE, offset_poly(ccw(rect(-15, 15, -83, 83, 3)), -0.05), 0, 0.3, label="reflector_back"))
    for s in (-1, 1):
        put(strip(Sb, s * 20 - 0.5, s * 20 + 0.5, -70, 70, ION, margin=0.4))
    for s in (-1, 1):                                  # cap underside ion bars
        Sc = face_surface("-z", -12)
        put(strip(Sc, -13, 13, s * 97 - 0.6, s * 97 + 0.6, ION, margin=0.4))
    # side faces: slot vents + hazard markers near the ends
    for side, plane in (("+y", 24), ("-y", -24)):
        S = face_surface(side, plane)
        B.extend(vent(S, -40, 40, -6.2, -1.8, depth=1.0, chamfer=0.6, pitch=1.4, vertical=True))
        for xu in (-84, 84):
            B.append(S.box(HAZARD, xu - 4, xu + 4, -5.5, -2.5, 0, 0.3, bevel=0.1, label="hazard_marker"))
    diff = root.child("Diffuser", pivot=(0.0, 0.0, -11.3), role="movable",
                      motion={"type": "slide", "dir_ue": [0, 0, -1], "range_cm": [0, 3], "note": "drops for lamp service"},
                      note="Emissive diffuser panel (OD_MAT_Diffuser_Emissive)")
    diff.add(Sb.sub(0, 0, 0.3).prism(DIFFUSER, offset_poly(ccw(rect(-15, 15, -83, 83, 3)), -0.05), 0, 2.3, label="diffuser"))

    body.add(B)
    lights.add(L)
    root.socket("SOCKET_Light", (0.0, 0.0, -14.5), "Rect light origin (0.30 x 1.66 m), facing -Z")
    root.socket("SOCKET_Mount_Ceiling", (0.0, 0.0, 0.0), "Pivot: top-centre, flush to ceiling")
    root.socket("SOCKET_Mount_Bracket_A", (70.0, 0.0, 0.0), "Ceiling bracket anchor")
    root.socket("SOCKET_Mount_Bracket_B", (-70.0, 0.0, 0.0), "Ceiling bracket anchor")
    return Asset(
        name=NAME, title="Ceiling Light Module (2.0 m)", reference="11_Ceiling_Light_Module_Reference.png",
        envelope=(50, 14, 200), pivot="ceiling", pivot_text="top-centre (ceiling flush); length along X",
        root=root,
        description=("Linear ceiling luminaire, 2.0 m standard module: white chamfered housing, gunmetal end caps, "
                     "two ceiling brackets, recessed graphite bezel holding a drop-down emissive diffuser, ion edge "
                     "strips and cap bars, side slot vents with hazard markers. Compact 1.2 m / 0.6 m variants can be "
                     "made by changing the housing length in the script."),
        collision="None (ceiling fixture, out of reach). If needed: one box 2.00 x 0.50 x 0.14.",
        nanite="Nanite ON for Body; Diffuser/StatusLights emissive meshes can stay non-Nanite.",
        interaction=[("Light state", "SOCKET_Light", "Normal (ion) / analysis (amber) / emergency (red): swap strip MI")],
        mounting=[("Ceiling", "SOCKET_Mount_Ceiling", "Flush; two brackets at x = +-0.70 m")],
        notes=["Reference shows a 0.60 x 0.30 m section; this module follows the in-repo prototype contract "
               "(2.00 x 0.50 x 0.14 m) so it replaces SM_PROXY_CeilingLight_Linear in place."],
    )
