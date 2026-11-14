"""ODYSSEY Earth Command kit geometry: Engineering proxies and the Engineering finish kit.

Pure Python, no Unreal import. `odyssey_slice_assets.py` turns these parts into StaticMesh assets
inside the editor; `python3 Tools/Editor/odyssey_kit_geometry.py --check` validates envelopes and
pivots natively.

PROXIES, NOT PRODUCTION MESHES. Every proxy is a hard-surface blockout composed from boxes and
cylinders. It follows the approved reference image's silhouette and the mounting contract of the
Replit architectural prototype (envelope, pivot, mount) so the production GLB/FBX can replace it
in place. No reference PNG is used as geometry or texture.

Units: cm. Axes (Unreal): +X = the asset's front, +Y = its right, +Z = up.
Pivot rules (from the prototype's mounting table):
  floor      bottom-centre of the envelope         x in [-D/2, D/2], y in [-W/2, W/2], z in [0, H]
  wall_base  bottom-centre of the rear face        x in [0, D],      y in [-W/2, W/2], z in [0, H]
  wall       centre of the rear face               x in [0, D],      y in [-W/2, W/2], z in [-H/2, H/2]
  ceiling    top-centre (ceiling flush)            x in [-L/2, L/2], y in [-W/2, W/2], z in [-H, 0]
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------------- palette
# ODYSSEY palette (sRGB hex) and the PBR response of each material slot.
PALETTE = {
    "white":    {"hex": "#D8D9D5", "metallic": 0.0, "roughness": 0.42},  # Aerospace White
    "graphite": {"hex": "#1C2025", "metallic": 0.0, "roughness": 0.62},  # Graphite
    "gunmetal": {"hex": "#454B52", "metallic": 0.55, "roughness": 0.46},  # Gunmetal
    "alu":      {"hex": "#92989E", "metallic": 1.0, "roughness": 0.32},  # Brushed Aluminum
    "ion":      {"hex": "#61BED2", "metallic": 0.0, "roughness": 0.30, "emissive": "#61BED2", "strength": 6.0},
    "amber":    {"hex": "#D69A35", "metallic": 0.0, "roughness": 0.50},  # Amber (warning markings only)
    "red":      {"hex": "#B84743", "metallic": 0.0, "roughness": 0.45, "emissive": "#B84743", "strength": 0.6},
    "screen":   {"hex": "#09131C", "metallic": 0.0, "roughness": 0.08, "emissive": "#61BED2", "strength": 0.9},
    "diffuser": {"hex": "#F2F3F0", "metallic": 0.0, "roughness": 0.50, "emissive": "#F4F6FA", "strength": 14.0},
}
MATERIAL_ORDER = list(PALETTE)  # stable slot order


def srgb_to_linear(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


# --------------------------------------------------------------------------------------------- parts
@dataclass
class Part:
    kind: str                      # "box" | "cyl"
    mat: str
    center: tuple[float, float, float]
    size: tuple[float, float, float] = (0, 0, 0)   # box: full extents along local x, y, z
    radius: float = 0.0                            # cyl
    length: float = 0.0                            # cyl, along its axis
    axis: str = "z"                                # cyl axis
    sides: int = 12
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0)  # (pitch about Y, yaw about Z, roll about X), degrees


def span(s, a, b):
    """Mirror helper: the interval between s*a and s*b, ordered."""
    return tuple(sorted((s * a, s * b)))


def box(mat, x0, x1, y0, y1, z0, z1, rot=(0.0, 0.0, 0.0)) -> Part:
    return Part("box", mat, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), rot=rot)


def boxc(mat, center, size, rot=(0.0, 0.0, 0.0)) -> Part:
    return Part("box", mat, tuple(center), tuple(size), rot=rot)


def cyl(mat, center, radius, length, axis="z", sides=12) -> Part:
    return Part("cyl", mat, tuple(center), radius=radius, length=length, axis=axis, sides=sides)


def rotate(p, rot):
    """Rotate point p by (pitch about Y, yaw about Z, roll about X) degrees, applied roll→pitch→yaw."""
    pitch, yaw, roll = (math.radians(a) for a in rot)
    x, y, z = p
    # roll about X
    y, z = y * math.cos(roll) - z * math.sin(roll), y * math.sin(roll) + z * math.cos(roll)
    # pitch about Y (positive pitch raises the +X end, Unreal convention)
    x, z = x * math.cos(pitch) - z * math.sin(pitch), x * math.sin(pitch) + z * math.cos(pitch)
    # yaw about Z
    x, y = x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw)
    return (x, y, z)


def faces(part: Part):
    """Yield (material, [(position, normal, uv)] * n, outward normal) quads/n-gons for one part.
    Vertices are ordered counter-clockwise when seen from outside along the outward normal."""
    cx, cy, cz = part.center
    out = []
    if part.kind == "box":
        hx, hy, hz = (s / 2 for s in part.size)
        corners = {}
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    corners[(sx, sy, sz)] = (sx * hx, sy * hy, sz * hz)
        quads = [
            ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
            ((-1, 0, 0), [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)]),
            ((0, 1, 0), [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)]),
            ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
            ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
            ((0, 0, -1), [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)]),
        ]
        for n, keys in quads:
            pts = [rotate(corners[k], part.rot) for k in keys]
            nn = rotate(n, part.rot)
            pts = [(cx + p[0], cy + p[1], cz + p[2]) for p in pts]
            out.append((part.mat, pts, nn, n))
    else:
        r, half, s = part.radius, part.length / 2, max(6, part.sides)

        def to_world(u, v, w):  # w along the axis
            if part.axis == "z":
                p = (u, v, w)
            elif part.axis == "x":
                p = (w, u, v)
            else:
                p = (v, w, u)
            p = rotate(p, part.rot)
            return (cx + p[0], cy + p[1], cz + p[2])

        def axis_vec(u, v, w):
            if part.axis == "z":
                p = (u, v, w)
            elif part.axis == "x":
                p = (w, u, v)
            else:
                p = (v, w, u)
            return rotate(p, part.rot)

        ring = [(math.cos(2 * math.pi * i / s), math.sin(2 * math.pi * i / s)) for i in range(s)]
        for i in range(s):
            a, b = ring[i], ring[(i + 1) % s]
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            ln = math.hypot(*mid)
            pts = [to_world(a[0] * r, a[1] * r, -half), to_world(b[0] * r, b[1] * r, -half),
                   to_world(b[0] * r, b[1] * r, half), to_world(a[0] * r, a[1] * r, half)]
            out.append((part.mat, pts, axis_vec(mid[0] / ln, mid[1] / ln, 0), "side"))
        top = [to_world(c[0] * r, c[1] * r, half) for c in ring]
        bottom = [to_world(c[0] * r, c[1] * r, -half) for c in reversed(ring)]
        out.append((part.mat, top, axis_vec(0, 0, 1), "cap"))
        out.append((part.mat, bottom, axis_vec(0, 0, -1), "cap"))
    return out


def bounds(parts):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for p in parts:
        for _, pts, _, _ in faces(p):
            for q in pts:
                for i in range(3):
                    lo[i] = min(lo[i], q[i])
                    hi[i] = max(hi[i], q[i])
    return lo, hi


# --------------------------------------------------------------------------------------------- proxies
@dataclass
class Proxy:
    asset: str           # StaticMesh asset name
    reference: str       # approved reference image (visual only)
    envelope: tuple      # W (y), H (z), D (x) in cm — the prototype's mounting envelope
    pivot: str           # floor | wall_base | wall | ceiling
    collision: str       # "box" (simple envelope box) | "none"
    movable_parts: list = field(default_factory=list)   # parts kept separable in the production mesh
    parts: list = field(default_factory=list)


def _slats(mat, x0, x1, y0, y1, z0, z1, n, horizontal=True):
    out = []
    if horizontal:
        step = (z1 - z0) / n
        for i in range(n):
            z = z0 + step * (i + 0.5)
            out.append(box(mat, x0, x1, y0, y1, z - step * 0.22, z + step * 0.22))
    else:
        step = (y1 - y0) / n
        for i in range(n):
            y = y0 + step * (i + 0.5)
            out.append(box(mat, x0, x1, y - step * 0.22, y + step * 0.22, z0, z1))
    return out


def power_console() -> Proxy:
    """01 Power Console — W180 x H125 x D90, bottom-centre, floor. Front (+X) = operator side."""
    P = []
    # plinth and feet
    P += [box("graphite", -42, 40, -86, 86, 0, 7),
          box("gunmetal", -44, 44, -90, -62, 0, 9), box("gunmetal", -44, 44, 62, 90, 0, 9)]
    # lower body (white) with recessed service door
    P += [box("white", -40, 28, -60, 60, 7, 70),
          box("gunmetal", 28, 29.5, -46, 46, 14, 62),
          box("white", 29.5, 31, -44, 44, 16, 60),
          box("alu", 31, 32.5, -36, -32, 26, 50),                     # door latch
          box("ion", 29.5, 31, -30, 30, 63.5, 65)]                    # under-desk status strip
    # side equipment pods with vent slats and ion edge strips
    for s in (-1, 1):
        y0, y1 = sorted((s * 60, s * 88))
        P += [box("gunmetal", -42, 34, y0, y1, 9, 76),
              box("graphite", 34, 35, y0 + 4, y1 - 4, 16, 60)]
        P += _slats("gunmetal", 35, 36.5, y0 + 6, y1 - 6, 18, 58, 6)
        P += [box("ion", 34, 36, s * 61 - 1, s * 61 + 1, 14, 70),
              box("amber", 35, 36, (y0 + y1) / 2 - 3, (y0 + y1) / 2 + 3, 63, 69)]   # hazard tag
    # sloped control desk (front edge lower), control modules on it
    desk_rot = (-14.0, 0.0, 0.0)
    P += [boxc("white", (12, 0, 81), (46, 176, 7), desk_rot)]
    for y, mat_btn in ((-58, "ion"), (-20, "ion"), (20, "ion"), (58, "red")):
        P += [boxc("graphite", (14, y, 85.2), (30, 34, 2.4), desk_rot)]
        for k in range(3):
            P += [boxc(mat_btn if k == 0 else "ion", (20 - 7 * k, y - 8, 86.6), (4, 5, 1.6), desk_rot),
                  boxc("alu", (20 - 7 * k, y + 8, 86.6), (4, 5, 1.6), desk_rot)]
    P += [cyl("alu", (14, -30, 87.2), 3.2, 3.0, "z", 16), cyl("alu", (14, 30, 87.2), 3.2, 3.0, "z", 16)]  # rotary selectors
    # upper instrument housing
    P += [box("white", -45, -14, -82, 82, 84, 118),
          box("gunmetal", -44, -24, -30, 30, 118, 125)]               # top vent cap
    P += _slats("graphite", -40, -28, -26, 26, 125, 125.6, 1)
    # main display (angled back) with bezel; side displays toed in
    scr_rot = (12.0, 0.0, 0.0)
    P += [boxc("graphite", (-11, 0, 102), (4, 108, 34), scr_rot),
          boxc("screen", (-8.6, 0, 102.5), (1.2, 100, 28), scr_rot)]
    for s in (-1, 1):
        rot = (10.0, -s * 14.0, 0.0)
        P += [boxc("graphite", (-14, s * 70, 101), (4, 26, 30), rot),
              boxc("screen", (-11.8, s * 70, 101.4), (1.0, 22, 25), rot)]
    return Proxy("SM_PROXY_PowerConsole", "01_Power_Console.png", (180, 125, 90), "floor", "box",
                 ["control desk switch caps", "e-stop guard", "service door"], P)


def bus_b_cabinet() -> Proxy:
    """02 Power Bus B Cabinet — W120 x H220 x D60, bottom-centre of rear face, wall."""
    P = [box("graphite", 2, 58, -58, 58, 0, 12),
         box("ion", 58, 59, -20, 20, 4, 6),
         box("white", 0, 54, -56, 56, 12, 206),
         box("gunmetal", 0, 58, -58, 58, 206, 213)]
    for s in (-1, 1):
        P += [box("gunmetal", 52, 58, *span(s, 52, 58), 12, 206),                  # front corner posts
              box("alu", 50, 54, *span(s, 44.5, 47.5), 213, 220),                 # carry bar posts
              box("alu", 30, 34, *span(s, 56, 58.5), 100, 190),                   # side grab rails
              box("graphite", 10, 44, *span(s, 56, 56.5), 20, 60)]                # side vent
    P += [box("alu", 50, 54, -46, 46, 216, 220)]                     # top carry bar
    # upper vent grille + status strip
    P += [box("graphite", 54, 56, -42, 42, 182, 200)] + _slats("gunmetal", 56, 57, -40, 40, 183, 199, 5)
    P += [box("ion", 54, 57, -14, 14, 201, 203.5)]
    # display module
    P += [box("graphite", 54, 57, -44, 16, 150, 178), box("screen", 57, 57.8, -40, 8, 153, 175)]
    P += [box("ion", 56, 58, 24, 30, 170, 174), box("ion", 56, 58, 24, 30, 162, 166), box("ion", 56, 58, 24, 30, 154, 158)]
    # main breaker row (3 large breakers) + auxiliary switches
    P += [box("graphite", 54, 56, -46, 46, 112, 148)]
    for y in (-30, -12, 6):
        P += [box("gunmetal", 56, 58, y - 7, y + 7, 116, 144), box("graphite", 58, 60, y - 3, y + 3, 126, 138),
              box("red", 58.5, 60, y - 3, y + 3, 136, 140), box("ion", 56.5, 58, y - 2, y + 2, 145, 146.5)]
    P += [cyl("alu", (58, 28, 130), 3.0, 4.0, "x", 12), cyl("alu", (58, 38, 130), 3.0, 4.0, "x", 12)]
    # 8-way MCB strip
    P += [box("graphite", 54, 56, -46, 46, 84, 108)]
    for i in range(8):
        y = -38 + i * 10.8
        P += [box("alu", 56, 58.5, y - 4, y + 4, 86, 102), box("graphite", 58.5, 59.5, y - 1.5, y + 1.5, 92, 98),
              box("ion", 56, 57.5, y - 1.5, y + 1.5, 103, 105)]
    # lower access door
    P += [box("gunmetal", 54, 55, -50, 50, 18, 80), box("white", 55, 56.5, -48, 48, 20, 78),
          box("amber", 56.5, 57, 26, 34, 62, 70), box("alu", 56.5, 59, 36, 40, 34, 52)]
    P += _slats("graphite", 56.5, 57, -40, 0, 24, 34, 4)
    P += [box("screen", 0.5, 54, -56.5, -56, 120, 127), box("screen", 0.5, 54, 56, 56.5, 120, 127)]  # Deep Navy side band
    return Proxy("SM_PROXY_PowerBusB_Cabinet", "02_Power_Bus_B_Cabinet.png", (120, 220, 60), "wall_base", "box",
                 ["three main breaker handles", "lower access door", "MCB strip"], P)


def orion_terminal() -> Proxy:
    """08/08B ORION Physical Terminal — W70 x H155 x D60, bottom-centre, floor."""
    P = [box("graphite", -30, 30, -35, 35, 0, 7), box("alu", -30, 30, -35, 35, 7, 9),
         box("white", -22, 18, -28, 28, 9, 82),
         box("gunmetal", 18, 19, -22, 22, 16, 70),                     # lower front service panel frame
         box("white", 19, 20, -20, 20, 18, 68),
         box("graphite", 20, 20.6, 6, 16, 22, 30),                     # access hatch
         box("ion", 18, 20, -24, 24, 79, 81),
         box("graphite", 16, 20, -16, 6, 84, 90), box("graphite", 16, 20, 12, 18, 84, 90)]  # speaker / power
    P += [box("white", -26, 6, -30, 30, 82, 152), box("gunmetal", -26, -10, -30, 30, 150, 155)]
    rot = (10.0, 0.0, 0.0)
    P += [boxc("graphite", (8, 0, 118), (5, 58, 70), rot), boxc("screen", (10.8, 0, 118.5), (1.2, 50, 62), rot),
          boxc("graphite", (8.5, 0, 151), (3, 12, 3), rot)]            # camera bar
    for s in (-1, 1):
        P += [box("gunmetal", -20, 10, *span(s, 29.4, 30.6), 30, 140),
              box("graphite", -16, 4, *span(s, 30.6, 31.0), 60, 64)]
    return Proxy("SM_PROXY_ORION_Terminal", "08B_ORION_Physical_Terminal.png", (70, 155, 60), "floor", "box",
                 ["touch screen surface", "power button"], P)


def server_rack() -> Proxy:
    """09 Server / Equipment Rack — W60 x H210 x D100, bottom-centre, floor, front +X."""
    P = [box("graphite", -48, 48, -30, 30, 0, 10)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            P += [box("amber", *span(sx, 44, 48), *span(sy, 24, 30), 2, 9.5),
                  box("white", *span(sx, 44, 50), *span(sy, 24, 30), 10, 204)]
    P += [box("graphite", -44, 44, -24, 24, 10, 204), box("gunmetal", -50, 50, -30, 30, 204, 210),
          box("ion", 49.2, 50, -14, 14, 205.5, 208)]
    for s in (-1, 1):
        P += [box("ion", 49, 50, *span(s, 26, 28), 30, 190)]
    def unit(z0):
        return [box("gunmetal", 44, 46, -22, 22, z0, z0 + 12), box("graphite", 46, 46.6, -16, 6, z0 + 2, z0 + 10),
                box("amber", 46, 48, -21, -18, z0 + 2, z0 + 10), box("amber", 46, 48, 18, 21, z0 + 2, z0 + 10),
                box("ion", 46, 46.8, 8, 16, z0 + 5, z0 + 7)]
    for z in (160, 173.5, 187):
        P += unit(z)
    for z in (60, 73.5, 87):
        P += unit(z)
    P += [box("graphite", 44, 46, -22, 22, 104, 154), box("screen", 46, 46.8, -19, 12, 108, 150),
          box("ion", 46, 47, 14, 19, 124, 134)]
    P += [box("graphite", 44, 46, -22, 22, 14, 54)] + _slats("gunmetal", 46, 47, -20, 20, 16, 52, 6)
    for s in (-1, 1):  # side cable trunking
        P += [box("gunmetal", -36, 30, *span(s, 23.5, 24.5), 20, 196)]
    return Proxy("SM_PROXY_ServerRack_42U", "09_Server_Equipment_Rack.png", (60, 210, 100), "floor", "box",
                 ["front door", "server sleds"], P)


def ceiling_light() -> Proxy:
    """11 Ceiling Light Module (standard 2.0 m) — L200 (x) x W50 (y) x H14, top-centre, ceiling.
    The diffuser and ion edge strips use EmissiveScale and dim with the light (AOdysseyLightFixture)."""
    P = [box("white", -94, 94, -25, 25, -10, 0),
         box("gunmetal", -100, -86, -25, 25, -12, 0), box("gunmetal", 86, 100, -25, 25, -12, 0),
         box("gunmetal", -70, 70, -16, 16, -0.5, 0),
         box("graphite", -86, 86, -20, 20, -12, -10),
         box("diffuser", -82, 82, -17, 17, -13.5, -12),
         box("ion", -60, 60, 22, 23.5, -12.5, -10), box("ion", -60, 60, -23.5, -22, -12.5, -10)]
    for sx in (-1, 1):
        P += [box("amber", *span(sx, 86, 90), -25.0, -21, -11, -6),
              box("amber", *span(sx, 86, 90), 21, 25.0, -11, -6)]
        P += _slats("graphite", *span(sx, 94, 94.6), -18, 18, -9, -2, 3)
    return Proxy("SM_PROXY_CeilingLight_Linear", "11_Ceiling_Light_Module_Reference.png", (50, 14, 200), "ceiling", "none",
                 ["diffuser panel"], P)


def wall_utility_panel() -> Proxy:
    """12 Wall Utility Panel — W100 x H120 x D18, centre of rear face, wall."""
    P = [box("gunmetal", 0, 6, -50, 50, -60, 60),
         box("white", 6, 12, -50, 50, 48, 60), box("white", 6, 12, -50, 50, -60, -48),
         box("white", 6, 12, -50, -42, -48, 48), box("white", 6, 12, 42, 50, -48, 48),
         box("graphite", 12, 13, -22, 22, 50, 58)]
    P += _slats("gunmetal", 13, 14, -20, 20, 51, 57, 3)
    P += [box("graphite", 6, 14, -40, -14, -30, 30),                   # power access door
          box("amber", 14, 15, -32, -22, 2, 14), box("amber", 14, 16.5, -16, -14, -10, 10),
          box("graphite", 6, 13, -10, 28, -14, 34), box("screen", 13, 13.8, -7, 25, -10, 30),
          box("gunmetal", 6, 15, 30, 40, -2, 34), box("red", 15, 17, 31.5, 38.5, 6, 28),
          box("graphite", 6, 13, -10, 28, -44, -20)]
    P += [cyl("alu", (15, -2, -32), 5.0, 6.0, "x", 16), cyl("alu", (15, 12, -32), 5.0, 6.0, "x", 16),
          box("ion", 13, 14, 18, 26, -36, -28)]
    P += [box("ion", 12, 13.5, -14, 14, 44, 46), box("ion", 12, 13.5, -14, 14, -46, -44),
          box("ion", 12, 13.5, -48, -46, -20, 20), box("ion", 12, 13.5, 46, 48, -20, 20)]
    for sy in (-1, 1):
        for sz in (-1, 1):
            P += [box("amber", 12, 13, *span(sy, 34, 40), *span(sz, 50, 54))]
    return Proxy("SM_PROXY_WallUtilityPanel", "12_Wall_Utility_Panel.png", (100, 120, 18), "wall", "none",
                 ["power access door", "emergency switch guard"], P)


def ventilation_module() -> Proxy:
    """13 Ventilation Module — W140 x H80 x D40, centre of rear face, wall."""
    P = [box("white", 0, 34, -66, 66, -36, 36)]
    for sy in (-1, 1):
        for sz in (-1, 1):
            P += [box("gunmetal", 0, 36, *span(sy, 56, 70), *span(sz, 26, 40))]
    P += [box("graphite", 34, 36, -54, 54, -20, 28)]
    louver = (-18.0, 0.0, 0.0)
    for z in (-14, -4, 6, 16, 24):
        P += [boxc("alu", (37, 0, z), (5, 104, 1.6), louver)]
    P += [box("gunmetal", 34, 38, -18, -15, -20, 28), box("gunmetal", 34, 38, 15, 18, -20, 28)]
    P += [box("ion", 34, 36.5, -18, 18, 30, 32.5),
          box("gunmetal", 34, 36, 10, 50, -36, -24), box("graphite", 36, 37, 20, 28, -33, -27),
          box("amber", 34, 35, -44, -24, -33, -29)]
    for sy in (-1, 1):
        P += _slats("graphite", 4, 30, *span(sy, 66, 67), -20, 20, 6, horizontal=True)
    return Proxy("SM_PROXY_VentModule_A", "13_Ventilation_Module.png", (140, 80, 40), "wall", "none",
                 ["louver blades", "filter hatch"], P)


PROXY_BUILDERS = {
    "power_console": power_console,
    "bus_b_cabinet": bus_b_cabinet,
    "orion_terminal": orion_terminal,
    "server_rack": server_rack,
    "ceiling_light": ceiling_light,
    "wall_utility_panel": wall_utility_panel,
    "ventilation_module": ventilation_module,
}


def expected_bounds(proxy: Proxy):
    W, H, D = proxy.envelope
    if proxy.pivot == "floor":
        return (-D / 2, -W / 2, 0), (D / 2, W / 2, H)
    if proxy.pivot == "wall_base":
        return (0, -W / 2, 0), (D, W / 2, H)
    if proxy.pivot == "wall":
        return (0, -W / 2, -H / 2), (D, W / 2, H / 2)
    if proxy.pivot == "ceiling":
        return (-D / 2, -W / 2, -H), (D / 2, W / 2, 0)
    raise ValueError(proxy.pivot)


def check_proxy(proxy: Proxy, tol=0.6):
    """Envelope + pivot contract: the parts stay inside the envelope and reach the pivot planes."""
    lo, hi = bounds(proxy.parts)
    elo, ehi = expected_bounds(proxy)
    problems = []
    for i, ax in enumerate("xyz"):
        if lo[i] < elo[i] - tol or hi[i] > ehi[i] + tol:
            problems.append(f"{ax} [{lo[i]:.1f},{hi[i]:.1f}] outside envelope [{elo[i]},{ehi[i]}]")
    # pivot planes must be touched (the mesh sits on / against its mount)
    anchor = {"floor": [(2, "lo")], "wall_base": [(0, "lo"), (2, "lo")], "wall": [(0, "lo")], "ceiling": [(2, "hi")]}[proxy.pivot]
    for i, side in anchor:
        v, e = (lo[i], elo[i]) if side == "lo" else (hi[i], ehi[i])
        if abs(v - e) > tol:
            problems.append(f"pivot plane {'xyz'[i]}={e} not reached ({v:.1f})")
    # the mesh fills the envelope (not a token box)
    for i, ax in enumerate("xyz"):
        if (hi[i] - lo[i]) < 0.85 * (ehi[i] - elo[i]):
            problems.append(f"{ax} extent {hi[i] - lo[i]:.1f} < 85% of envelope {ehi[i] - elo[i]}")
    return problems, (lo, hi)


# --------------------------------------------------------------------------------------------- room kit
@dataclass
class KitMesh:
    asset: str
    pivot_world: tuple       # world location of the mesh pivot (actor location)
    collision: str           # "complex" (use complex as simple) | "none"
    parts: list


def _modules(a0, a1, cuts, pitch=200.0):
    """Split [a0, a1] at door cuts [(centre, width)], then fit modules of ~pitch to each segment.
    Returns segments as lists of (s, e) module spans."""
    segs, start = [], a0
    for c, w in sorted(cuts):
        segs.append((start, c - w / 2))
        start = c + w / 2
    segs.append((start, a1))
    out = []
    for s, e in segs:
        if e - s < 30:
            continue
        n = max(1, round((e - s) / pitch))
        p = (e - s) / n
        out.append([(s + i * p, s + (i + 1) * p) for i in range(n)])
    return out


def engineering_kit(area: dict, corridor: dict, exclusions=None, wall=20.0, door_h=260.0):
    """Finish kit for the Engineering area: floor plates, wall system with service recess and ribs,
    ceiling bays and beams, ventilation openings, overhead services, door frame and the corridor-side
    transition. Shell blocks from the greybox stay as structure and wall/floor collision."""
    x0, x1, y0, y1 = area["bounds"]
    H = float(area["height"])
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ix0, ix1, iy0, iy1 = x0 + wall / 2, x1 - wall / 2, y0 + wall / 2, y1 - wall / 2
    L = lambda x, y: (x - cx, y - cy)  # world → mesh-local (pivot at room floor centre)
    excl = list(exclusions or [])  # world boxes (x0, x1, y0, y1, z0, z1) occupied by equipment

    def blocked(xa, xb, ya, yb, za, zb):
        return any(xa < e[1] and xb > e[0] and ya < e[3] and yb > e[2] and za < e[5] and zb > e[4] for e in excl)

    def world_span(side, s, e, d0, d1):
        sd = sides[side]
        f, k = sd["face"], sd["inward"]
        a, b = sorted((f + k * d0, f + k * d1))
        return (s, e, a, b) if sd["axis"] == "x" else (a, b, s, e)

    floor, walls, ceiling, services = [], [], [], []

    # ---- floor plates (1 m grid, 30 mm shadow gaps over the graphite subfloor)
    nx, ny = round((ix1 - ix0) / 100), round((iy1 - iy0) / 100)
    px, py = (ix1 - ix0) / nx, (iy1 - iy0) / ny
    for i in range(nx):
        for j in range(ny):
            ax, ay = L(ix0 + i * px + 1.5, iy0 + j * py + 1.5)
            floor.append(box("gunmetal", ax, ax + px - 3, ay, ay + py - 3, 0, 2))

    # ---- walls: kick panel, accent trim, wall panel, service recess with pipes, upper panel, ribs
    doors = area["doors"]
    sides = {
        "N": dict(axis="x", a0=ix0, a1=ix1, face=iy1, inward=-1),
        "S": dict(axis="x", a0=ix0, a1=ix1, face=iy0, inward=+1),
        "E": dict(axis="y", a0=iy0, a1=iy1, face=ix1, inward=-1),
        "W": dict(axis="y", a0=iy0, a1=iy1, face=ix0, inward=+1),
    }

    def slab(side, s, e, d0, d1, z0, z1, mat, target):
        """A box spanning [s,e] along the wall, from depth d0 to d1 off the wall face, z0..z1."""
        sd = sides[side]
        f, k = sd["face"], sd["inward"]
        a, b = sorted((f + k * d0, f + k * d1))
        if sd["axis"] == "x":
            target.append(box(mat, s - cx, e - cx, a - cy, b - cy, z0, z1))
        else:
            target.append(box(mat, a - cx, b - cx, s - cy, e - cy, z0, z1))

    def tube(side, s, e, depth, z, r, mat, target):
        sd = sides[side]
        f, k = sd["face"], sd["inward"]
        c = f + k * depth
        if sd["axis"] == "x":
            target.append(cyl(mat, ((s + e) / 2 - cx, c - cy, z), r, e - s, "x", 10))
        else:
            target.append(cyl(mat, (c - cx, (s + e) / 2 - cy, z), r, e - s, "y", 10))

    recess = H >= 440
    wall_top = 255.0 if recess else H - 40
    module_index = 0
    for side, sd in sides.items():
        cuts = [tuple(c) for c in doors.get(side, [])]
        # door cuts include the frame jambs (24 cm each side)
        cuts_framed = [(c, w + 48) for c, w in cuts]
        for seg in _modules(sd["a0"], sd["a1"], cuts_framed):
            for (s, e) in seg:
                g0, g1 = s + 7, e - 7      # 14 cm rib zone shared at every module boundary
                slab(side, g0, g1, 0, 8, 6, 62, "gunmetal", walls)
                slab(side, g0, g1, 0, 2, 66, 68.5, "ion", walls)
                slab(side, g0, g1, 0, 10, 72, wall_top, "white", walls)
                if recess:
                    # service recess: exposed pipe runs at 278 / 310 on brackets
                    slab(side, s, e, 0, 1, 255, 325, "graphite", walls)
                    tube(side, s, e, 12, 278, 4.5, "alu", walls)
                    tube(side, s, e, 13, 310, 5.5, "gunmetal", walls)
                    m = (s + e) / 2
                    slab(side, m - 3, m + 3, 0, 18, 270, 318, "gunmetal", walls)
                    slab(side, g0, g1, 0, 8, 325, H - 32, "white", walls)
                else:
                    slab(side, g0, g1, 0, 8, wall_top + 4, H - 32, "white", walls)
                # ventilation opening every third module (upper panel louvre) + floor vent
                if module_index % 3 == 1:
                    m = (s + e) / 2
                    top0 = 340 if recess else wall_top + 20
                    if not blocked(*world_span(side, m - 40, m + 40, 0, 45), top0 - 10, top0 + 44):
                        slab(side, m - 34, m + 34, 7, 10, top0, top0 + 34, "graphite", walls)
                        for k in range(4):
                            z = top0 + 5 + k * 7.5
                            slab(side, m - 31, m + 31, 9, 11, z, z + 2.2, "alu", walls)
                    if not blocked(*world_span(side, m - 40, m + 40, 25, 65), -1, 10):
                        slab(side, m - 40, m + 40, 30, 60, 0, 2.6, "graphite", floor)
                        for k in range(5):
                            d = 33 + k * 5.6
                            slab(side, m - 37, m + 37, d, d + 2.4, 2.6, 3.2, "gunmetal", floor)
                module_index += 1
            # ribs at every module boundary of this segment
            for b in sorted({seg[0][0]} | {e for _, e in seg}):
                slab(side, b - 7, b + 7, 0, 24, 0, H, "alu", walls)

    # ---- door frames on the Engineering side (jambs, header, threshold hazard plate, status strip)
    door_parts = []
    for side, lst in doors.items():
        for c, w in lst:
            sd = sides[side]
            for s0, s1 in ((c - w / 2 - 24, c - w / 2), (c + w / 2, c + w / 2 + 24)):
                slab(side, s0, s1, 0, 50, 0, 270, "alu", door_parts)
            slab(side, c - w / 2 - 36, c + w / 2 + 36, 0, 52, door_h, door_h + 44, "gunmetal", door_parts)
            slab(side, c - 40, c + 40, 52, 53.5, door_h + 18, door_h + 22, "ion", door_parts)
            for k in range(12):
                s0 = c - w / 2 + k * (w / 12)
                slab(side, s0, s0 + w / 12, 0, 36, 0, 1.2, "amber" if k % 2 == 0 else "graphite", door_parts)

    # ---- ceiling: 2 m bays, beams every module across the short span, service hatches
    xs = [ix0 + i * (ix1 - ix0) / round((ix1 - ix0) / 200) for i in range(round((ix1 - ix0) / 200) + 1)]
    ys = [iy0 + j * (iy1 - iy0) / round((iy1 - iy0) / 200) for j in range(round((iy1 - iy0) / 200) + 1)]
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            ceiling.append(box("white", xs[i] + 2 - cx, xs[i + 1] - 2 - cx, ys[j] + 2 - cy, ys[j + 1] - 2 - cy, H - 6, H))
            if (i + j) % 4 == 3:
                mx, my = (xs[i] + xs[i + 1]) / 2 - cx, (ys[j] + ys[j + 1]) / 2 - cy
                ceiling.append(box("gunmetal", mx - 40, mx + 40, my - 40, my + 40, H - 7, H - 6))
    for xb in xs[1:-1]:
        ceiling.append(box("gunmetal", xb - 10 - cx, xb + 10 - cx, iy0 - cy, iy1 - cy, H - 32, H))

    return {"floor": floor, "walls": walls, "ceiling": ceiling, "door": door_parts, "xs": xs, "ys": ys,
            "cx": cx, "cy": cy, "H": H, "interior": (ix0, ix1, iy0, iy1)}


def engineering_services(kit, placements):
    """Overhead services tied to the placed equipment: 48 V DC bus tray from the bus B cabinet,
    cross tray to the server racks, coolant loop A/B risers from the thermal plant to the recess,
    return-air duct from air handling to the ventilation module. World placements in, local parts out."""
    cx, cy, H = kit["cx"], kit["cy"], kit["H"]
    ix0, ix1, iy0, iy1 = kit["interior"]
    P = []
    cab = placements["bus_b_cabinet"]
    ty = cab[1]
    # tray A along X at the cabinet's Y, hung from the beams
    z = H - 70
    P += [box("alu", ix0 + 30 - cx, ix1 - 30 - cx, ty - 16 - cy, ty + 16 - cy, z, z + 1.5),
          box("alu", ix0 + 30 - cx, ix1 - 30 - cx, ty - 16 - cy, ty - 14.5 - cy, z, z + 10),
          box("alu", ix0 + 30 - cx, ix1 - 30 - cx, ty + 14.5 - cy, ty + 16 - cy, z, z + 10)]
    for k, off in enumerate((-8, 0, 8)):
        P.append(cyl("graphite" if k != 1 else "gunmetal", ((ix0 + ix1) / 2 - cx, ty + off - cy, z + 5), 3.6, ix1 - ix0 - 70, "x", 8))
    for xb in kit["xs"][1:-1]:
        P += [box("alu", xb - 1 - cx, xb + 1 - cx, ty - 15 - cy, ty - 13 - cy, z + 10, H - 32),
              box("alu", xb - 1 - cx, xb + 1 - cx, ty + 13 - cy, ty + 15 - cy, z + 10, H - 32)]
    # drop from the tray into the cabinet top
    P += [box("gunmetal", cab[0] + 8 - cx, cab[0] + 26 - cx, ty - 10 - cy, ty + 10 - cy, 220, z)]
    # tray B along Y (lower level, hung from the ceiling bays), then across to the server racks
    rx = placements["tray_b_x"]
    r0, r1, ry = placements["server_racks_span"]
    zb = H - 92
    yb0, yb1 = iy0 + 30, ry
    P += [box("alu", rx - 15 - cx, rx + 15 - cx, yb0 - cy, yb1 + 15 - cy, zb, zb + 1.5),
          box("alu", rx - 15 - cx, rx - 13.5 - cx, yb0 - cy, yb1 + 15 - cy, zb, zb + 9),
          box("alu", rx + 13.5 - cx, rx + 15 - cx, yb0 - cy, yb1 - 15 - cy, zb, zb + 9),
          cyl("gunmetal", (rx - cx, (yb0 + yb1) / 2 - cy, zb + 4.5), 3.4, yb1 - yb0, "y", 8),
          box("alu", rx + 15 - cx, r1 - cx, ry - 15 - cy, ry + 15 - cy, zb, zb + 1.5),
          box("alu", rx + 15 - cx, r1 - cx, ry - 15 - cy, ry - 13.5 - cy, zb, zb + 9),
          box("alu", rx - 15 - cx, r1 - cx, ry + 13.5 - cy, ry + 15 - cy, zb, zb + 9),
          cyl("gunmetal", ((rx + r1) / 2 - cx, ry - cy, zb + 4.5), 3.4, r1 - rx, "x", 8)]
    for k in range(3):  # drops into each rack top
        x = r0 + 30 + k * 65
        P += [box("gunmetal", x - 6 - cx, x + 6 - cx, ry - 6 - cy, ry + 6 - cy, 210, zb)]
    for yh in (yb0 + 150, (yb0 + yb1) / 2, yb1 - 60):
        P += [box("alu", rx - 1 - cx, rx + 1 - cx, yh - 1 - cy, yh + 1 - cy, zb + 9, H - 6)]
    # coolant loop A/B: risers from the thermal plant top to just under the beams, run to the east recess
    tp = placements["thermal_plant"]
    for k, (dx, mat) in enumerate(((-40, "alu"), (40, "gunmetal"))):
        x = tp[0] + dx
        zr = H - 48 - k * 12
        P += [cyl(mat, (x - cx, tp[1] - cy, (300 + zr) / 2), 6.0, zr - 300, "z", 12),
              cyl(mat, (((x + ix1 - 14) / 2) - cx, tp[1] - cy, zr), 6.0, ix1 - 14 - x, "x", 12),
              cyl(mat, (ix1 - 14 - cx, tp[1] - cy, (310 + zr) / 2), 6.0, zr - 310, "z", 12),
              cyl("red", (x - cx, tp[1] - cy, 380), 11.0, 2.5, "z", 16),          # isolation valve handwheel
              cyl("gunmetal", (x - cx, tp[1] - cy, 380), 7.5, 10.0, "z", 12)]     # valve body
    # return-air duct from the air handling unit up to the ventilation module
    ah = placements["air_handling"]
    P += [box("gunmetal", ah[0] - 25 - cx, ah[0] + 15 - cx, ah[1] - 60 - cy, ah[1] + 60 - cy, 240, 318),
          box("alu", ah[0] - 26 - cx, ah[0] + 16 - cx, ah[1] - 61 - cy, ah[1] + 61 - cy, 240, 246)]
    return P


def corridor_transition(door_x, wall_y, corridor_height, wall=20.0, door_w=240.0, door_h=260.0):
    """Corridor-side frame of the Engineering door plus two rib portals flanking it. Pivot: the
    door centre on the wall line, floor level. Corridor interior is +Y (north) of the wall."""
    f = wall / 2  # corridor-side wall face, local +Y
    P = []
    for s0, s1 in ((-door_w / 2 - 24, -door_w / 2), (door_w / 2, door_w / 2 + 24)):
        P.append(box("alu", s0, s1, f, f + 40, 0, 270))
    P += [box("gunmetal", -door_w / 2 - 36, door_w / 2 + 36, f, f + 40, door_h, min(door_h + 40, corridor_height - 2)),
          box("ion", -40, 40, f + 40, f + 41.5, door_h + 16, door_h + 20),
          box("amber", -door_w / 2 - 36, -door_w / 2 - 24, f + 40, f + 41, door_h, door_h + 40),
          box("amber", door_w / 2 + 24, door_w / 2 + 36, f + 40, f + 41, door_h, door_h + 40)]
    for k in range(12):
        s0 = -door_w / 2 + k * door_w / 12
        P.append(box("amber" if k % 2 == 0 else "graphite", s0, s0 + door_w / 12, f, f + 36, 0, 1.2))
    return P


# --------------------------------------------------------------------------------------------- CLI
def main(argv):
    ok = True
    for key, fn in PROXY_BUILDERS.items():
        p = fn()
        problems, (lo, hi) = check_proxy(p)
        tris = sum(len(pts) - 2 for part in p.parts for _, pts, _, _ in faces(part))
        mats = sorted({part.mat for part in p.parts})
        status = "ok  " if not problems else "FAIL"
        ok &= not problems
        print(f"{status} {p.asset:32s} env W{p.envelope[0]} H{p.envelope[1]} D{p.envelope[2]} pivot={p.pivot:9s} "
              f"bounds x[{lo[0]:.1f},{hi[0]:.1f}] y[{lo[1]:.1f},{hi[1]:.1f}] z[{lo[2]:.1f},{hi[2]:.1f}] "
              f"parts={len(p.parts)} tris={tris} mats={','.join(mats)}")
        for pr in problems:
            print("       " + pr)
    print("proxy geometry check " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
