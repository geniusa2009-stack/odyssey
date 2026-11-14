"""ODYSSEY Asset Pack - reusable hard-surface details placed on Surfaces.

Every helper returns a list of Solids that sit flush on the surface (heights measured from it), so
details touch their mount and never interpenetrate it. Units cm. Surface u = viewer's right,
v = up the face, n = out of the face.
"""
from __future__ import annotations

import math

from od_core import Surface, rect, chamfer_poly, circle, clip_poly, ccw, offset_poly
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, GLASS, DISPLAY, ION, AMBER, RED, HAZARD


def screws(S: Surface, pts, r=0.55, h=0.25, mat=ALU):
    return [S.cyl(mat, u, v, r, 0, h, sides=8, bevel=0.08, label="screw") for (u, v) in pts]


def corner_screws(S, u0, u1, v0, v1, inset=2.0, h0=0.0, r=0.55):
    pts = [(u0 + inset, v0 + inset), (u1 - inset, v0 + inset), (u1 - inset, v1 - inset), (u0 + inset, v1 - inset)]
    return [S.cyl(ALU, u, v, r, h0, h0 + 0.25, sides=8, bevel=0.08, label="screw") for (u, v) in pts]


def strip(S: Surface, u0, u1, v0, v1, mat=ION, h0=0.0, channel=GRAPHITE, margin=0.5, depth=(0.4, 0.35)):
    """Emissive light bar seated in a dark channel plate."""
    out = [S.box(channel, u0 - margin, u1 + margin, v0 - margin, v1 + margin, h0, h0 + depth[0], bevel=0.15, label="strip_channel")]
    out.append(S.box(mat, u0, u1, v0, v1, h0 + depth[0], h0 + depth[0] + depth[1], bevel=0.1, label="strip"))
    return out


def vent(S: Surface, u0, u1, v0, v1, h0=0.0, depth=1.6, n=None, frame_mat=GUNMETAL, back_mat=GRAPHITE,
         slat_mat=GUNMETAL, pitch=2.2, chamfer=1.0, vertical=False, tilt=25.0):
    """Recessed vent: frame ring (real opening) + dark back plate + slats spanning the opening."""
    out = []
    fw = 1.2
    outer = rect(u0, u1, v0, v1, chamfer)
    inner = rect(u0 + fw, u1 - fw, v0 + fw, v1 - fw, max(chamfer - fw * 0.4, 0.0) if chamfer > 0 else 0.0)
    if len(outer) != len(inner):
        inner = rect(u0 + fw, u1 - fw, v0 + fw, v1 - fw, 0.3) if chamfer > 0 else inner
    out.append(S.frame(frame_mat, outer, inner, h0, h0 + depth, bevel=0.25, label="vent_frame"))
    out.append(S.prism(back_mat, offset_poly(ccw(inner), -0.05), h0, h0 + 0.3, label="vent_back"))
    span = (u1 - u0 - 2 * fw) if vertical else (v1 - v0 - 2 * fw)
    if n is None:
        n = max(2, int(span // pitch))
    step = span / n
    t = min(0.55, step * 0.3)
    clip = ccw(offset_poly(ccw(inner), -0.06))
    for i in range(n):
        c = (u0 + fw if vertical else v0 + fw) + step * (i + 0.5)
        if vertical:
            r = rect(c - t / 2, c + t / 2, v0 + fw, v1 - fw)
        else:
            r = rect(u0 + fw, u1 - fw, c - t / 2, c + t / 2)
        poly = clip_poly(ccw(r), clip)
        if len(poly) >= 3:
            out.append(S.prism(slat_mat, poly, h0 + 0.3, h0 + depth - 0.3, label="vent_slat"))
    return out


def hazard_plate(S: Surface, u0, u1, v0, v1, h0=0.0, n=None, plate=GRAPHITE, stripe=HAZARD, width=None, chamfer=0.6):
    """Graphite plate with diagonal painted hazard stripes (raised 1 mm, clipped to the plate)."""
    out = [S.box(plate, u0, u1, v0, v1, h0, h0 + 0.5, bevel=0.15, label="hazard_plate")]
    W, H = u1 - u0, v1 - v0
    m = 0.6
    clip = ccw(rect(u0 + m, u1 - m, v0 + m, v1 - m))
    sw = width or max(1.2, H * 0.45)
    pitch = sw * 2
    k = H  # 45 degree slant
    x = u0 - k
    while x < u1:
        band = [(x, v0), (x + sw, v0), (x + sw + k, v1), (x + k, v1)]
        poly = clip_poly(ccw(band), clip)
        if len(poly) >= 3 and abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                                      for i in range(len(poly)))) > 0.2:
            out.append(S.prism(stripe, poly, h0 + 0.5, h0 + 0.62, label="hazard_stripe"))
        x += pitch
    return out


def chevrons(S: Surface, u0, v0, size, count=3, mat=HAZARD, h0=0.0, gap=None):
    """'///' identity marks: slanted parallelogram bars."""
    out = []
    w = size * 0.28
    g = gap or size * 0.22
    for i in range(count):
        x = u0 + i * (w + g)
        poly = [(x, v0), (x + w, v0), (x + w + size * 0.5, v0 + size), (x + size * 0.5, v0 + size)]
        out.append(S.prism(mat, poly, h0, h0 + 0.12, label="chevron"))
    return out


def button(S: Surface, u, v, w, h, cap=ION, h0=0.0, base=GRAPHITE):
    return [S.box(base, u - w / 2 - 0.4, u + w / 2 + 0.4, v - h / 2 - 0.4, v + h / 2 + 0.4, h0, h0 + 0.4, bevel=0.12, label="button_base"),
            S.box(cap, u - w / 2, u + w / 2, v - h / 2, v + h / 2, h0 + 0.4, h0 + 1.2, bevel=0.2, label="button_cap")]


def knob(S: Surface, u, v, r, h0=0.0, ring=ION):
    """Rotary selector: emissive halo ring, gunmetal collar, knurled aluminium cap."""
    return [S.tube(ring, u, v, r + 1.0, r + 0.25, h0, h0 + 0.3, sides=28, label="knob_ring"),
            S.cyl(GUNMETAL, u, v, r + 0.2, h0, h0 + 0.8, sides=24, bevel=0.15, label="knob_collar"),
            S.cyl(ALU, u, v, r, h0 + 0.8, h0 + 0.8 + r * 0.9, sides=24, bevel=0.35, label="knob_cap"),
            S.box(GRAPHITE, u - 0.25, u + 0.25, v + r * 0.25, v + r * 0.85, h0 + 0.8 + r * 0.9, h0 + 0.9 + r * 0.9, label="knob_mark")]


def toggle(S: Surface, u, v, h0=0.0, lever=ALU, guard=True):
    """Toggle switch: plate, bushing, lever (lever tilted up the face)."""
    out = [S.box(GRAPHITE, u - 1.4, u + 1.4, v - 2.0, v + 2.0, h0, h0 + 0.35, bevel=0.1, label="toggle_plate"),
           S.cyl(GUNMETAL, u, v, 0.55, h0 + 0.35, h0 + 0.95, sides=10, label="toggle_bushing")]
    T = S.sub(u, v, h0 + 0.95).tilt(-20)
    out.append(T.cyl(lever, 0, 0, 0.28, 0.12, 2.3, sides=8, bevel=0.05, label="toggle_lever"))
    if guard:
        for s in (-1, 1):
            out.append(S.box(GUNMETAL, u + s * 1.1 - 0.15, u + s * 1.1 + 0.15, v - 1.6, v + 1.6, h0 + 0.35, h0 + 1.9, label="toggle_guard"))
    return out


def fader_slot(S: Surface, u, v, length, h0=0.0):
    """Recessed fader track (frame ring + slot floor). Returns (static solids, cap solids, cap travel)."""
    w = 1.6
    outer = rect(u - w / 2 - 0.8, u + w / 2 + 0.8, v - length / 2 - 0.8, v + length / 2 + 0.8, 0.5)
    inner = rect(u - w / 2, u + w / 2, v - length / 2, v + length / 2, 0.3)
    static = [S.frame(GUNMETAL, outer, inner, h0, h0 + 0.6, bevel=0.15, label="fader_frame"),
              S.prism(GRAPHITE, offset_poly(ccw(inner), -0.05), h0, h0 + 0.2, label="fader_floor")]
    cap = [S.box(GUNMETAL, u - 0.25, u + 0.25, v - 0.5, v + 0.5, h0 + 0.2, h0 + 0.6, label="fader_stem"),
           S.box(GRAPHITE, u - 1.6, u + 1.6, v - 1.2, v + 1.2, h0 + 0.6, h0 + 2.4, bevel=0.3, label="fader_cap"),
           S.box(ION, u - 1.2, u + 1.2, v - 0.25, v + 0.25, h0 + 2.4, h0 + 2.55, label="fader_index")]
    return static, cap


def screen(S: Surface, u0, u1, v0, v1, h0=0.0, bezel=1.6, depth=1.4, chamfer=1.6, bezel_mat=GRAPHITE):
    """Physical screen: bezel ring (real recess) around a display plate.
    Returns (bezel solids, display solids). The display plate's front face has 0..1 UVs."""
    outer = rect(u0, u1, v0, v1, chamfer)
    inner = rect(u0 + bezel, u1 - bezel, v0 + bezel, v1 - bezel, max(chamfer * 0.6, 0.4))
    bz = [S.frame(bezel_mat, outer, inner, h0, h0 + depth, bevel=0.3, label="bezel"),
          S.prism(GRAPHITE, offset_poly(ccw(inner), -0.05), h0, h0 + 0.3, label="screen_backplate")]
    # display plate inset 0.05 cm from the bezel opening so it never touches the bezel walls
    m = 0.05 + max(chamfer * 0.6, 0.4) * 0.6
    disp = [S.display(DISPLAY, u0 + bezel + m, u1 - bezel - m, v0 + bezel + m, v1 - bezel - m, h0 + 0.3, h0 + 0.6, label="display")]
    return bz, disp


def handle_bar(S: Surface, u0, u1, v, standoff=3.0, r=0.8, mat=ALU, foot_mat=GUNMETAL, h0=0.0, vertical=False):
    """Grab handle: two feet + bar. Horizontal along u (or vertical along v)."""
    out = []
    if vertical:
        a, b = sorted((u0, u1))  # here u0,u1 are v-range; v is u position
        for vv in (a, b):
            out.append(S.box(foot_mat, v - 1.4, v + 1.4, vv - 1.4, vv + 1.4, h0, h0 + standoff, bevel=0.3, label="handle_foot"))
        out.append(S.box(mat, v - r, v + r, a - 1.4, b + 1.4, h0 + standoff, h0 + standoff + 2 * r, bevel=r * 0.45, label="handle_bar"))
    else:
        for uu in (u0, u1):
            out.append(S.box(foot_mat, uu - 1.4, uu + 1.4, v - 1.4, v + 1.4, h0, h0 + standoff, bevel=0.3, label="handle_foot"))
        out.append(S.box(mat, u0 - 1.4, u1 + 1.4, v - r, v + r, h0 + standoff, h0 + standoff + 2 * r, bevel=r * 0.45, label="handle_bar"))
    return out


def recessed_handle(S: Surface, u, v, w, h, h0=0.0):
    """Flush pull: gunmetal cup ring with aluminium grip bar inside."""
    outer = rect(u - w / 2, u + w / 2, v - h / 2, v + h / 2, 0.8)
    inner = rect(u - w / 2 + 0.8, u + w / 2 - 0.8, v - h / 2 + 0.8, v + h / 2 - 0.8, 0.4)
    return [S.frame(GUNMETAL, outer, inner, h0, h0 + 1.0, bevel=0.2, label="pull_cup"),
            S.prism(GRAPHITE, offset_poly(ccw(inner), -0.05), h0, h0 + 0.2, label="pull_floor"),
            S.box(ALU, u - w / 2 + 0.8, u + w / 2 - 0.8, v - 0.5, v + 0.5, h0 + 0.2, h0 + 0.9, bevel=0.15, label="pull_grip")]


def hinge_knuckles(S: Surface, u, v0, v1, n=2, r=0.9, h0=0.0, length=5.0):
    out = []
    for i in range(n):
        vc = v0 + (v1 - v0) * (i + 0.5) / n
        out.append(S.box(GUNMETAL, u - 1.2, u + 1.2, vc - length / 2, vc + length / 2, h0, h0 + 0.4, bevel=0.1, label="hinge_leaf"))
        T = S.sub(u, vc, h0 + 0.4 + r)
        out.append(Surface(T.o, T.u, T.n, T.v).cyl(ALU, 0, 0, r, -length / 2, length / 2, sides=10, label="hinge_knuckle"))
    return out


def warning_triangle(S: Surface, u, v, size, h0=0.0):
    tri = [(u - size / 2, v - size * 0.43), (u + size / 2, v - size * 0.43), (u, v + size * 0.43)]
    inner = [(u - size * 0.3, v - size * 0.3), (u + size * 0.3, v - size * 0.3), (u, v + size * 0.22)]
    return [S.prism(HAZARD, tri, h0, h0 + 0.12, label="warn_tri"),
            S.prism(GRAPHITE, inner, h0 + 0.12, h0 + 0.18, label="warn_tri_inner")]


def led_row(S: Surface, u0, v, n, pitch, mat=ION, h0=0.0, w=0.9, h=0.5):
    return [S.box(mat, u0 + i * pitch - w / 2, u0 + i * pitch + w / 2, v - h / 2, v + h / 2, h0, h0 + 0.25, bevel=0.08, label="led")
            for i in range(n)]
