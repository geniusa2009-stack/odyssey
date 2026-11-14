"""Pure-Python geometry for the ODYSSEY space experience (no Unreal dependency; testable with python3).

Meshes are dicts {slot: Section} where Section holds positions, normals, uvs (lists of tuples) and
triangles (index triples). Triangles are wound counter-clockwise around the outward normal using the
standard cross product (b - a) x (c - a); the Unreal builder reverses them (front-face convention),
exactly like odyssey_kit_geometry.faces. Units: centimetres, Unreal axes (+X forward, +Y right, +Z up).

  sphere(...)          equirectangular UV sphere (planets, atmosphere shells, inverted sky)
  transit_vehicle()    OTV-1 "Meridian" crew transit vehicle hull (nose +X, engines at -X)
  vehicle_plume()      three exhaust plumes, pivot on the nozzle exit plane, extending along -X
  vehicle_rcs()        reaction-control jets for the flip manoeuvre

    python3 odyssey_space_geometry.py      # self-check: counts, bounds, winding vs normals
"""
import math

VEHICLE_LENGTH = 6500.0     # cm, nose tip (+3150) to nozzle exit (-3350)
NOZZLE_EXIT_X = -3350.0
ENGINE_RING = 230.0         # engine centres on a circle of this radius (YZ)
ENGINE_ANGLES = (90.0, 210.0, 330.0)


class Section:
    def __init__(self):
        self.positions, self.normals, self.uvs, self.triangles = [], [], [], []

    def vert(self, p, n, uv):
        self.positions.append(tuple(p))
        self.normals.append(tuple(n))
        self.uvs.append(tuple(uv))
        return len(self.positions) - 1

    def tri(self, a, b, c):
        self.triangles.append((a, b, c))


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class Mesh:
    def __init__(self):
        self.sections = {}

    def section(self, slot):
        if slot not in self.sections:
            self.sections[slot] = Section()
        return self.sections[slot]

    def quad(self, slot, a, b, c, d, na, nb, nc, nd, uva, uvb, uvc, uvd):
        """a-b-c-d counter-clockwise around the outward normal."""
        s = self.section(slot)
        i0, i1, i2, i3 = s.vert(a, na, uva), s.vert(b, nb, uvb), s.vert(c, nc, uvc), s.vert(d, nd, uvd)
        s.tri(i0, i1, i2)
        s.tri(i0, i2, i3)

    def box(self, slot, center, size, axes=((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        """Oriented box: center, full size (sx, sy, sz) along the given orthonormal axes."""
        hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
        X, Y, Z = axes

        def P(u, v, w):
            return tuple(center[i] + X[i] * u * hx + Y[i] * v * hy + Z[i] * w * hz for i in range(3))
        faces = [((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
                 ((-1, 0, 0), [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)]),
                 ((0, 1, 0), [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)]),
                 ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
                 ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
                 ((0, 0, -1), [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)])]
        for (lx, ly, lz), corners in faces:
            n = tuple(X[i] * lx + Y[i] * ly + Z[i] * lz for i in range(3))
            pts = [P(*c) for c in corners]
            uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
            self.quad(slot, *pts, n, n, n, n, *uv)

    def lathe(self, slot, profile, segments=64, axis_offset=(0.0, 0.0), crease_deg=35.0, start_angle=0.0, sweep=360.0):
        """Surface of revolution around the X axis (shifted by axis_offset in YZ).
        profile: [(x, r), ...]; the surface faces away from the axis when x decreases along the profile
        ... so profiles are listed nose -> tail (x decreasing) for outward-facing skins."""
        rings = []  # (x, r, nx, nr, v)
        segs = []
        for i in range(len(profile) - 1):
            (x0, r0), (x1, r1) = profile[i], profile[i + 1]
            dx, dr = x1 - x0, r1 - r0
            l = math.hypot(dx, dr) or 1.0
            # outward normal in the (x, r) plane for a profile walked with x decreasing
            segs.append((dr / l, -dx / l, l))
        acc = 0.0
        for i, (x, r) in enumerate(profile):
            ns = []
            if i > 0:
                ns.append(segs[i - 1][:2])
            if i < len(segs):
                ns.append(segs[i][:2])
            if len(ns) == 2:
                cosang = ns[0][0] * ns[1][0] + ns[0][1] * ns[1][1]
                if cosang < math.cos(math.radians(crease_deg)):
                    rings.append((x, r, ns[0][0], ns[0][1], acc, True))
                    rings.append((x, r, ns[1][0], ns[1][1], acc, False))
                else:
                    nx, nr = ns[0][0] + ns[1][0], ns[0][1] + ns[1][1]
                    l = math.hypot(nx, nr) or 1.0
                    rings.append((x, r, nx / l, nr / l, acc, None))
            else:
                rings.append((x, r, ns[0][0], ns[0][1], acc, None))
            if i < len(segs):
                acc += segs[i][2]
        s = self.section(slot)
        oy, oz = axis_offset
        full = abs(sweep - 360.0) < 1e-6
        cols = segments + 1
        ids = []
        for (x, r, nx, nr, v, _) in rings:
            row = []
            for j in range(cols):
                a = math.radians(start_angle + sweep * j / segments)
                ca, sa = math.cos(a), math.sin(a)
                p = (x, oy + r * ca, oz + r * sa)
                n = _norm((nx, nr * ca, nr * sa))
                circ = 2.0 * math.pi * max(r, 1.0) * (sweep / 360.0)
                row.append(s.vert(p, n, (circ * j / segments / 100.0, v / 100.0)))
            ids.append(row)
        for k in range(len(rings) - 1):
            # skip the zero-length band between the two copies of a crease ring
            if rings[k][5] is True and rings[k + 1][5] is False:
                continue
            for j in range(segments):
                a, b = ids[k][j], ids[k][j + 1]
                c, d = ids[k + 1][j + 1], ids[k + 1][j]
                s.tri(a, b, c)
                s.tri(a, c, d)
        return s


def sphere(radius=100.0, seg_u=256, seg_v=128, inward=False, slot="Surface"):
    """UV sphere matching generate_space_textures.py: p = (cos(lat)cos(lon), cos(lat)sin(lon), sin(lat)),
    u = lon / 2pi + 0.5, v = 0.5 - lat / pi. Duplicate seam column, poles collapsed per column."""
    m = Mesh()
    s = m.section(slot)
    rows = []
    for i in range(seg_v + 1):
        v = i / seg_v
        lat = (0.5 - v) * math.pi
        row = []
        for j in range(seg_u + 1):
            u = j / seg_u
            lon = (u - 0.5) * 2.0 * math.pi
            n = (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))
            p = (n[0] * radius, n[1] * radius, n[2] * radius)
            uu = u
            if i == 0 or i == seg_v:
                uu = (j + 0.5) / seg_u  # pole vertices sit mid-cell
            row.append(s.vert(p, (-n[0], -n[1], -n[2]) if inward else n, (uu, v)))
        rows.append(row)
    for i in range(seg_v):
        for j in range(seg_u):
            a, b = rows[i][j], rows[i][j + 1]
            c, d = rows[i + 1][j + 1], rows[i + 1][j]
            # outward CCW: rows go north->south, columns west->east; (a, d, c) faces outward
            t1, t2 = (a, d, c), (a, c, b)
            if inward:
                t1, t2 = (a, c, d), (a, b, c)
            if i != 0:
                s.tri(*t2 if not inward else t2)
            if i != seg_v - 1:
                s.tri(*t1 if not inward else t1)
    _fix_winding(m)
    return m


def _fix_winding(mesh):
    """Make every triangle CCW around its vertices' normals (robust against hand-wound mistakes)."""
    for s in mesh.sections.values():
        out = []
        for (a, b, c) in s.triangles:
            pa, pb, pc = s.positions[a], s.positions[b], s.positions[c]
            fn = _cross(_sub(pb, pa), _sub(pc, pa))
            n = s.normals[a]
            nn = (n[0] + s.normals[b][0] + s.normals[c][0], n[1] + s.normals[b][1] + s.normals[c][1], n[2] + s.normals[b][2] + s.normals[c][2])
            out.append((a, b, c) if _dot(fn, nn) >= 0.0 else (a, c, b))
        s.triangles = out


# --------------------------------------------------------------------------------------------- vehicle
def _ring_band(m, slot, x0, x1, r, segs=64, offset=(0.0, 0.0)):
    """Short cylindrical band (panel joint / stripe), outward faces + chamfer-free caps."""
    m.lathe(slot, [(x0, r - 6.0), (x0, r), (x1, r), (x1, r - 6.0)], segs, offset, crease_deg=30.0)


def transit_vehicle():
    m = Mesh()
    S = 96
    # nose docking adapter + crew module (white composite), window band, ion stripe
    m.lathe("Gunmetal", [(3150, 0), (3150, 95), (3120, 112), (3070, 118)], 48, crease_deg=30)
    m.lathe("White", [(3070, 118), (3040, 170), (2980, 228), (2900, 278), (2800, 318), (2700, 346),
                      (2560, 370), (2400, 384), (2250, 390)], S)
    m.lathe("Window", [(2760, 335.5), (2700, 349.5)], S, crease_deg=10)
    _ring_band(m, "Gunmetal", 2770, 2752, 334.0, S)
    _ring_band(m, "Gunmetal", 2708, 2690, 352.0, S)
    _ring_band(m, "Ion", 2342, 2330, 389.0, S)
    # collar
    m.lathe("Gunmetal", [(2250, 390), (2250, 412), (2232, 418), (2168, 418), (2150, 412), (2150, 402)], S, crease_deg=30)
    # service module
    m.lathe("White", [(2150, 402), (1150, 402)], S)
    for x in (1900, 1650, 1400):
        _ring_band(m, "Graphite", x + 8, x - 8, 404.0, S)
    for k in range(4):  # longitudinal stringers
        a = math.radians(45 + 90 * k)
        n = (0.0, math.cos(a), math.sin(a))
        t = (0.0, -math.sin(a), math.cos(a))
        m.box("Graphite", (1650, math.cos(a) * 410, math.sin(a) * 410), (980, 22, 18), ((1, 0, 0), t, n))
    # radiator wings (+/-Y): root fairing, boom, panel with ribs
    for side in (1, -1):
        m.box("Gunmetal", (1600, side * 470, 0), (520, 120, 70))
        m.box("Gunmetal", (1600, side * 620, 0), (90, 220, 40))
        y0 = side * (730 + 450)
        m.box("Alu", (1600, y0, 0), (900, 900, 14))
        m.box("Graphite", (1600, y0, 0), (920, 910, 6))
        for i in range(7):
            m.box("Gunmetal", (1600 - 390 + i * 130, y0, 0), (10, 900, 24))
        m.box("Gunmetal", (1600, y0 + side * 455, 0), (920, 14, 30))
        # navigation light on the wing tip: red to port (-Y), ion to starboard (+Y)
        m.box("NavRed" if side < 0 else "NavIon", (1600, side * 2392, 0), (26, 22, 22))  # outer wing tip
    # high-gain antenna on the dorsal side: boom + dish (built along local X, turned to face +Z)
    m.box("Gunmetal", (1300, 0, 470), (40, 40, 140))
    before = {k: len(v.positions) for k, v in m.sections.items()}
    m.lathe("White", [(-40, 0), (-20, 80), (0, 150)], 48, crease_deg=60)     # concave face (+X)
    m.lathe("Gunmetal", [(0, 146), (-30, 70), (-46, 0)], 48, crease_deg=60)  # back shell (-X)
    for k, sec in m.sections.items():
        for i in range(before.get(k, 0), len(sec.positions)):
            x, y, z = sec.positions[i]
            nx, ny, nz = sec.normals[i]
            sec.positions[i] = (1300 + z, y, 590 + x)   # local X -> world Z (a reflection; winding fixed below)
            sec.normals[i] = (nz, ny, nx)
    # truss
    m.lathe("Graphite", [(1150, 402), (1150, 250), (650, 250), (650, 470)], S, crease_deg=30)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        for sgn in (1, -1):
            p0 = (1150, math.cos(a) * 390, math.sin(a) * 390)
            p1 = (650, math.cos(a + sgn * 0.5) * 430, math.sin(a + sgn * 0.5) * 430)
            c = tuple((p0[i] + p1[i]) / 2 for i in range(3))
            d = _norm(_sub(p1, p0))
            up = _norm(_cross(d, (1.0, 0.0, 0.0))) if abs(d[0]) < 0.99 else (0.0, 0.0, 1.0)
            side = _norm(_cross(up, d))
            L = math.dist(p0, p1)
            m.box("Gunmetal", c, (L, 26, 26), (d, side, up))
    # main propellant tank: white with aluminium domes, ring frames and the ODYSSEY band
    m.lathe("Alu", [(650, 470), (620, 468), (560, 460)], S)
    m.lathe("White", [(560, 460), (-2200, 460)], S)
    m.lathe("Alu", [(-2200, 460), (-2260, 456), (-2300, 448)], S)
    for x in (300, -300, -900, -1500, -2050):
        _ring_band(m, "Gunmetal", x + 14, x - 14, 466.0, S)
    _ring_band(m, "Ion", 452, 440, 463.0, S)
    _ring_band(m, "Graphite", 430, 300, 462.0, S)
    # thrust structure
    m.lathe("Gunmetal", [(-2300, 448), (-2380, 440), (-2600, 360), (-2650, 330), (-2650, 120)], S, crease_deg=25)
    # engines: turbopump housing, chamber, regeneratively cooled bell (outer alu, inner graphite)
    for ang in ENGINE_ANGLES:
        a = math.radians(ang)
        off = (ENGINE_RING * math.cos(a), ENGINE_RING * math.sin(a))
        m.lathe("Gunmetal", [(-2640, 0), (-2640, 92), (-2700, 92), (-2760, 78), (-2800, 72)], 40, off, crease_deg=30)
        m.lathe("Alu", [(-2800, 80), (-2900, 108), (-3050, 146), (-3200, 182), (-3350, 212)], 48, off)
        m.lathe("Graphite", [(-3350, 204), (-3200, 174), (-3050, 138), (-2900, 100), (-2800, 72)], 48, off)
        _ring_band(m, "Gunmetal", -3330, -3350, 216.0, 48, off)
    # ---- hero detail pass -----------------------------------------------------------------
    # androgynous docking ring with three guide petals on the nose adapter
    _ring_band(m, "Alu", 3160, 3150, 128.0, 64)
    for k in range(3):
        a = math.radians(30 + 120 * k)
        d = (0.0, math.cos(a), math.sin(a))
        t = (0.0, -math.sin(a), math.cos(a))
        m.box("Gunmetal", (3185, math.cos(a) * 112, math.sin(a) * 112), (50, 40, 8), (_norm((0.45, d[1], d[2])), t, _norm(_cross((0.45, d[1], d[2]), t))))
    # framed crew windows in the window band
    for k in range(8):
        a = math.radians(-70 + k * 20)
        d = (0.0, math.cos(a), math.sin(a))
        t = (0.0, -math.sin(a), math.cos(a))
        m.box("Gunmetal", (2730, math.cos(a) * 348, math.sin(a) * 348), (62, 3, 30), ((1, 0, 0), t, d))
    # gold multi-layer insulation blankets on the service module between the frames
    for x0, x1 in ((2120, 1916), (1884, 1666), (1634, 1416), (1384, 1170)):
        m.lathe("Foil", [(x0, 405.5), (x1, 405.5)], 96, start_angle=200, sweep=140, crease_deg=10)
    # hinged second radiator panel on each wing + hinge line
    for side in (1, -1):
        y0 = side * (730 + 900 + 380)
        m.box("Alu", (1600, y0, 0), (900, 740, 12))
        m.box("Graphite", (1600, y0, 0), (920, 750, 5))
        for i in range(7):
            m.box("Gunmetal", (1600 - 390 + i * 130, y0, 0), (10, 740, 22))
        m.box("Gunmetal", (1600, side * (730 + 900 + 5), 0), (920, 16, 34))
    # longitudinal panel seams on the propellant tank
    for k in range(6):
        a = math.radians(k * 60 + 15)
        t = (0.0, -math.sin(a), math.cos(a))
        d = (0.0, math.cos(a), math.sin(a))
        m.box("Graphite", (-820, math.cos(a) * 461, math.sin(a) * 461), (2700, 3, 1.2), ((1, 0, 0), t, d))
    # thrust skirt and engine gimbal actuators
    m.lathe("Gunmetal", [(-2600, 362), (-2700, 372), (-2760, 368)], 96, crease_deg=40)
    for ang in ENGINE_ANGLES:
        a = math.radians(ang)
        cy, cz = ENGINE_RING * math.cos(a), ENGINE_RING * math.sin(a)
        for off in (0.6, -0.6):
            b = a + off
            m.box("Alu", (-2700, cy + math.cos(b) * 120, cz + math.sin(b) * 120), (120, 12, 12))
    # tail strobe
    m.box("NavIon", (-2655, 0, 336), (20, 20, 14))
    # ODYSSEY hull marking band (printed, curved to the tank)
    mk = hull_marking().sections["Marking"]
    dst = m.section("Marking")
    base = len(dst.positions)
    dst.positions += mk.positions
    dst.normals += mk.normals
    dst.uvs += mk.uvs
    dst.triangles += [(a + base, b + base, c + base) for a, b, c in mk.triangles]
    # RCS quads around the crew module
    for k in range(4):
        a = math.radians(45 + 90 * k)
        m.box("Gunmetal", (2420, math.cos(a) * 395, math.sin(a) * 395), (70, 60, 60))
    _fix_winding(m)
    return m


def hull_marking():
    """Curved print band on the propellant tank for the ODYSSEY / OTV-1 MERIDIAN marking (UV 0..1:
    u along the hull toward the nose, v across). Slot "Marking"."""
    m = Mesh()
    s = m.section("Marking")
    r, x0, x1, a0, a1, seg = 461.6, -1500.0, 260.0, 62.0, 118.0, 24
    rows = []
    for i in range(2):
        x = x0 if i == 0 else x1
        row = []
        for j in range(seg + 1):
            a = math.radians(a0 + (a1 - a0) * j / seg)
            n = (0.0, math.cos(a), math.sin(a))
            row.append(s.vert((x, r * n[1], r * n[2]), n, (float(i), j / seg)))
        rows.append(row)
    for j in range(seg):
        s.tri(rows[0][j], rows[1][j], rows[1][j + 1])
        s.tri(rows[0][j], rows[1][j + 1], rows[0][j + 1])
    _fix_winding(m)
    return m


def vehicle_plume():
    """Exhaust plumes: pivot on the nozzle exit plane (x = 0), extending toward -X. U runs along the
    plume (0 at the nozzle), V around it. Core (bright, short) + sheath (wide, long) per engine."""
    m = Mesh()
    for ang in ENGINE_ANGLES:
        a = math.radians(ang)
        off = (ENGINE_RING * math.cos(a), ENGINE_RING * math.sin(a))
        for slot, prof in (("Plume", [(0, 196), (-500, 250), (-1300, 330), (-2600, 470)]),
                           ("Plume", [(0, 120), (-300, 104), (-700, 70), (-1000, 20)])):
            s = m.lathe(slot, prof, 40, off, crease_deg=80)
    # replace UVs: U = distance along the plume / plume length, V = around
    s = m.sections["Plume"]
    for i, (x, y, z) in enumerate(s.positions):
        u, v = s.uvs[i]
        s.uvs[i] = (min(1.0, -x / 2600.0), v)
    _fix_winding(m)
    return m


def vehicle_rcs():
    """Four small RCS jet cones on the crew module quads (pointing radially outward)."""
    m = Mesh()
    s = m.section("Plume")
    for k in range(4):
        a = math.radians(45 + 90 * k)
        dirv = (0.0, math.cos(a), math.sin(a))
        t1 = (1.0, 0.0, 0.0)
        t2 = _cross(dirv, t1)
        base = (2420, math.cos(a) * 425, math.sin(a) * 425)
        N = 16
        tip_len, r0, r1 = 260.0, 18.0, 70.0
        ring0, ring1 = [], []
        for j in range(N + 1):
            ang = 2 * math.pi * j / N
            c, sn = math.cos(ang), math.sin(ang)
            off0 = tuple(t1[i] * c * r0 + t2[i] * sn * r0 for i in range(3))
            off1 = tuple(t1[i] * c * r1 + t2[i] * sn * r1 for i in range(3))
            p0 = tuple(base[i] + off0[i] for i in range(3))
            p1 = tuple(base[i] + dirv[i] * tip_len + off1[i] for i in range(3))
            n = _norm(tuple(t1[i] * c + t2[i] * sn for i in range(3)))
            ring0.append(s.vert(p0, n, (0.0, j / N)))
            ring1.append(s.vert(p1, n, (1.0, j / N)))
        for j in range(N):
            s.tri(ring0[j], ring0[j + 1], ring1[j + 1])
            s.tri(ring0[j], ring1[j + 1], ring1[j])
    _fix_winding(m)
    return m


# --------------------------------------------------------------------------------------------- station / hologram
def holo_torus(R=100.0, r=0.9, seg=128, tube=8, slot="Holo"):
    """Thin ring in the XY plane (hologram orbit / selection rings)."""
    m = Mesh()
    s = m.section(slot)
    rows = []
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        ca, sa = math.cos(a), math.sin(a)
        row = []
        for j in range(tube + 1):
            b = 2 * math.pi * j / tube
            cb, sb = math.cos(b), math.sin(b)
            n = (ca * cb, sa * cb, sb)
            p = ((R + r * cb) * ca, (R + r * cb) * sa, r * sb)
            row.append(s.vert(p, n, (i / seg, j / tube)))
        rows.append(row)
    for i in range(seg):
        for j in range(tube):
            s.tri(rows[i][j], rows[i + 1][j], rows[i + 1][j + 1])
            s.tri(rows[i][j], rows[i + 1][j + 1], rows[i][j + 1])
    _fix_winding(m)
    return m


def holo_disc(R=100.0, seg=96, slot="Holo"):
    """Flat disc facing +Z, UV = polar (u = radius 0..1, v = angle) for scan-grid shading."""
    m = Mesh()
    s = m.section(slot)
    rings = 12
    ids = []
    for k in range(rings + 1):
        rr = R * k / rings
        row = []
        for j in range(seg + 1):
            a = 2 * math.pi * j / seg
            row.append(s.vert((rr * math.cos(a), rr * math.sin(a), 0.0), (0.0, 0.0, 1.0), (k / rings, j / seg)))
        ids.append(row)
    for k in range(rings):
        for j in range(seg):
            s.tri(ids[k][j], ids[k + 1][j], ids[k + 1][j + 1])
            s.tri(ids[k][j], ids[k + 1][j + 1], ids[k][j + 1])
    _fix_winding(m)
    return m


def holo_beam(R=100.0, H=100.0, seg=64, slot="Holo"):
    """Open cone: narrow at the projector (z = 0), base radius R at z = H. U = height 0..1."""
    m = Mesh()
    s = m.section(slot)
    r0 = R * 0.18
    bottom, top = [], []
    for j in range(seg + 1):
        a = 2 * math.pi * j / seg
        ca, sa = math.cos(a), math.sin(a)
        n = _norm((ca, sa, -(R - r0) / H))
        bottom.append(s.vert((r0 * ca, r0 * sa, 0.0), n, (0.0, j / seg)))
        top.append(s.vert((R * ca, R * sa, H), n, (1.0, j / seg)))
    for j in range(seg):
        s.tri(bottom[j], bottom[j + 1], top[j + 1])
        s.tri(bottom[j], top[j + 1], top[j])
    _fix_winding(m)
    return m


def holo_marker(size=100.0, slot="Holo"):
    """Octahedron marker (spacecraft / station)."""
    m = Mesh()
    s = m.section(slot)
    h = size / 2
    P = [(h, 0, 0), (-h, 0, 0), (0, h, 0), (0, -h, 0), (0, 0, h * 1.4), (0, 0, -h * 1.4)]
    for a, b, c in ((0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)):
        pa, pb, pc = P[a], P[b], P[c]
        n = _norm(_cross(_sub(pb, pa), _sub(pc, pa)))
        i0, i1, i2 = s.vert(pa, n, (0, 0)), s.vert(pb, n, (1, 0)), s.vert(pc, n, (0.5, 1))
        s.tri(i0, i1, i2)
    _fix_winding(m)
    return m


def _flat_ring(m, slot, r0, r1, z, seg=128):
    s = m.section(slot)
    a_ids, b_ids = [], []
    for j in range(seg + 1):
        a = 2 * math.pi * j / seg
        ca, sa = math.cos(a), math.sin(a)
        a_ids.append(s.vert((r0 * ca, r0 * sa, z), (0, 0, 1), (r0 * ca / 100, r0 * sa / 100)))
        b_ids.append(s.vert((r1 * ca, r1 * sa, z), (0, 0, 1), (r1 * ca / 100, r1 * sa / 100)))
    for j in range(seg):
        s.tri(a_ids[j], b_ids[j], b_ids[j + 1])
        s.tri(a_ids[j], b_ids[j + 1], a_ids[j + 1])


def _vertical_band(m, slot, r, z0, z1, outward=True, seg=128):
    s = m.section(slot)
    lo, hi = [], []
    for j in range(seg + 1):
        a = 2 * math.pi * j / seg
        ca, sa = math.cos(a), math.sin(a)
        n = (ca, sa, 0.0) if outward else (-ca, -sa, 0.0)
        lo.append(s.vert((r * ca, r * sa, z0), n, (j / seg * 2 * math.pi * r / 100, z0 / 100)))
        hi.append(s.vert((r * ca, r * sa, z1), n, (j / seg * 2 * math.pi * r / 100, z1 / 100)))
    for j in range(seg):
        s.tri(lo[j], lo[j + 1], hi[j + 1])
        s.tri(lo[j], hi[j + 1], hi[j])


def mcc_floor_inlay():
    """Floor inlay around the holo table (pivot: table centre, floor level; sits on the 2 cm floor plates)."""
    m = Mesh()
    _flat_ring(m, "Graphite", 140.0, 258.0, 2.6)
    _flat_ring(m, "Ion", 259.0, 262.0, 2.7)
    _flat_ring(m, "Gunmetal", 263.0, 300.0, 2.6)
    for k in range(24):  # radial seams
        a = 2 * math.pi * k / 24
        d = (math.cos(a), math.sin(a), 0.0)
        side = (-math.sin(a), math.cos(a), 0.0)
        m.box("Alu", (d[0] * 199, d[1] * 199, 2.7), (118, 1.2, 0.4), (d, side, (0.0, 0.0, 1.0)))
    _fix_winding(m)
    return m


def mcc_halo(ceiling_h=420.0, z=330.0, R=210.0):
    """Suspended light halo above the table: aluminium housing ring, diffuser underside, hangers."""
    m = Mesh()
    _vertical_band(m, "Alu", R + 18, z, z + 16, True)
    _vertical_band(m, "Alu", R - 18, z, z + 16, False)
    _flat_ring(m, "Gunmetal", R - 18, R + 18, z + 16)
    s_before = len(m.section("Diffuser").positions)
    _flat_ring(m, "Diffuser", R - 14, R + 14, z)
    sec = m.sections["Diffuser"]
    for i in range(s_before, len(sec.normals)):
        sec.normals[i] = (0.0, 0.0, -1.0)
    for k in range(4):
        a = 2 * math.pi * (k + 0.5) / 4
        m.box("Gunmetal", (R * math.cos(a), R * math.sin(a), (z + 16 + ceiling_h) / 2), (4, 4, ceiling_h - z - 16))
    _fix_winding(m)
    return m


def display_frame(w, h, depth=8.0, bezel=6.0):
    """Wall display: graphite bezel box with the screen plane on its front (+X) face. Pivot: back centre.
    Slots: Graphite (housing), Screen (front plane, UV 0..1)."""
    m = Mesh()
    m.box("Graphite", (depth / 2, 0.0, 0.0), (depth, w + 2 * bezel, h + 2 * bezel))
    s = m.section("Screen")
    x = depth + 0.3
    # viewed from +X, local -Y is on the viewer's right: u runs from +Y (left) to -Y (right)
    a = s.vert((x, -w / 2, -h / 2), (1, 0, 0), (1.0, 1.0))
    b = s.vert((x, w / 2, -h / 2), (1, 0, 0), (0.0, 1.0))
    c = s.vert((x, w / 2, h / 2), (1, 0, 0), (0.0, 0.0))
    d = s.vert((x, -w / 2, h / 2), (1, 0, 0), (1.0, 0.0))
    s.tri(a, b, c)
    s.tri(a, c, d)
    _fix_winding(m)
    return m


def floor_decal_plane(w, d, slot="Decal"):
    """Thin floor plane (UV 0..1) for painted markings, 3 mm above the floor plates."""
    m = Mesh()
    s = m.section(slot)
    z = 2.3
    # text top (v = 0) at local -X: placed with yaw -90 it reads left-to-right for a viewer facing +Y
    a = s.vert((-d / 2, -w / 2, z), (0, 0, 1), (1.0, 0.0))
    b = s.vert((-d / 2, w / 2, z), (0, 0, 1), (0.0, 0.0))
    c = s.vert((d / 2, w / 2, z), (0, 0, 1), (0.0, 1.0))
    e = s.vert((d / 2, -w / 2, z), (0, 0, 1), (1.0, 1.0))
    s.tri(a, b, c)
    s.tri(a, c, e)
    _fix_winding(m)
    return m


def safety_border(w, d, band=14.0, stripe=28.0):
    """Hazard border (alternating amber / graphite stripes) around a w x d rectangle on the floor."""
    m = Mesh()
    z0, z1 = 2.0, 2.6
    def strip(x0, x1, y0, y1):
        m.box("Graphite", ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))
    hx, hy = d / 2, w / 2
    for (ax, ay, bx, by) in ((-hx, -hy, hx, -hy + band), (-hx, hy - band, hx, hy), (-hx, -hy, -hx + band, hy), (hx - band, -hy, hx, hy)):
        strip(ax, bx, ay, by)
        along_x = (bx - ax) > (by - ay)
        L = (bx - ax) if along_x else (by - ay)
        n = int(L // stripe)
        for k in range(0, n, 2):
            if along_x:
                m.box("Amber", (ax + (k + 0.5) * stripe, (ay + by) / 2, z1 + 0.15), (stripe * 0.62, band - 2, 0.3), ((0.7071, 0.7071, 0), (-0.7071, 0.7071, 0), (0, 0, 1)))
            else:
                m.box("Amber", ((ax + bx) / 2, ay + (k + 0.5) * stripe, z1 + 0.15), (stripe * 0.62, band - 2, 0.3), ((0.7071, -0.7071, 0), (0.7071, 0.7071, 0), (0, 0, 1)))
    _fix_winding(m)
    return m


def stats(mesh):
    tris = sum(len(s.triangles) for s in mesh.sections.values())
    verts = sum(len(s.positions) for s in mesh.sections.values())
    lo = [min(p[i] for s in mesh.sections.values() for p in s.positions) for i in range(3)]
    hi = [max(p[i] for s in mesh.sections.values() for p in s.positions) for i in range(3)]
    return {"tris": tris, "verts": verts, "min": [round(v, 1) for v in lo], "max": [round(v, 1) for v in hi],
            "slots": sorted(mesh.sections)}


def check_winding(mesh):
    bad = 0
    for s in mesh.sections.values():
        for a, b, c in s.triangles:
            fn = _cross(_sub(s.positions[b], s.positions[a]), _sub(s.positions[c], s.positions[a]))
            if _dot(fn, s.normals[a]) < -1e-6:
                bad += 1
    return bad


if __name__ == "__main__":
    for name, mesh in (("holo torus", holo_torus()), ("holo disc", holo_disc()), ("holo beam", holo_beam()), ("holo marker", holo_marker()),
                       ("mcc inlay", mcc_floor_inlay()), ("mcc halo", mcc_halo()), ("display", display_frame(400, 160)),
                       ("safety border", safety_border(420, 380)), ("decal plane", floor_decal_plane(300, 80)),("planet sphere", sphere(100, 384, 192)), ("sky sphere", sphere(100, 128, 64, inward=True)),
                       ("vehicle", transit_vehicle()), ("marking", hull_marking()), ("plume", vehicle_plume()), ("rcs", vehicle_rcs())):
        st = stats(mesh)
        print(f"{name:14s} {st['tris']:7d} tris {st['verts']:7d} verts  bounds {st['min']} .. {st['max']}  slots {st['slots']}  bad winding {check_winding(mesh)}")
