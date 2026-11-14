"""Procedural texture generator for the ODYSSEY space experience (Earth, Moon, Mars, starfield).

All planet maps are equirectangular (2:1), sampled from 3-D noise on the unit sphere, so they have
no seam at the antimeridian and no pinching at the poles. Outputs (8-bit PNG) go to ../Textures:

  T_Earth_Albedo   sRGB   surface colour, oceans, biomes, ice
  T_Earth_Clouds   linear R = cloud cover (drifts over the surface in the material)
  T_Earth_Masks    linear R = ocean mask, G = city lights, B = land height
  T_Earth_Normal   linear tangent-space normal (DirectX / Unreal convention)
  T_Moon_Albedo / T_Moon_Normal
  T_Mars_Albedo  / T_Mars_Normal
  T_Space_Starfield  sRGB  stars + Milky Way band (inverted sky sphere)

Requires numpy + Pillow. Deterministic (fixed seeds).
    python generate_space_textures.py [--size 4096] [--only earth,moon,mars,stars]
"""
import argparse
import math
import os

import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Textures")
CHUNK = 256  # rows per noise evaluation chunk (bounds peak memory)


# ---------------------------------------------------------------- noise
class Noise3:
    """Value noise on a hashed 3-D lattice with quintic interpolation (vectorised)."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.perm = np.concatenate([rng.permutation(256)] * 2).astype(np.int32)
        self.vals = rng.random(256).astype(np.float32) * 2.0 - 1.0

    def _h(self, x, y, z):
        p = self.perm
        return self.vals[p[p[p[x & 255] + (y & 255)] + (z & 255)]]

    def __call__(self, x, y, z):
        xi, yi, zi = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32), np.floor(z).astype(np.int32)
        fx, fy, fz = x - xi, y - yi, z - zi
        u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
        v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
        w = fz * fz * fz * (fz * (fz * 6 - 15) + 10)
        h = self._h
        x0 = h(xi, yi, zi) + u * (h(xi + 1, yi, zi) - h(xi, yi, zi))
        x1 = h(xi, yi + 1, zi) + u * (h(xi + 1, yi + 1, zi) - h(xi, yi + 1, zi))
        x2 = h(xi, yi, zi + 1) + u * (h(xi + 1, yi, zi + 1) - h(xi, yi, zi + 1))
        x3 = h(xi, yi + 1, zi + 1) + u * (h(xi + 1, yi + 1, zi + 1) - h(xi, yi + 1, zi + 1))
        y0 = x0 + v * (x1 - x0)
        y1 = x2 + v * (x3 - x2)
        return y0 + w * (y1 - y0)


def fbm(n, p, freq, octaves, lac=2.03, gain=0.5, offset=(0.0, 0.0, 0.0)):
    x, y, z = p
    total = np.zeros_like(x)
    amp, norm, f = 1.0, 0.0, freq
    for i in range(octaves):
        total += amp * n(x * f + offset[0] + i * 17.31, y * f + offset[1] + i * 3.77, z * f + offset[2] + i * 9.13)
        norm += amp
        amp *= gain
        f *= lac
    return total / norm


def ridged(n, p, freq, octaves, lac=2.1, gain=0.5, offset=(0.0, 0.0, 0.0)):
    x, y, z = p
    total = np.zeros_like(x)
    amp, norm, f = 1.0, 0.0, freq
    for i in range(octaves):
        r = 1.0 - np.abs(n(x * f + offset[0] + i * 5.1, y * f + offset[1] + i * 1.9, z * f + offset[2] + i * 7.7))
        total += amp * r * r
        norm += amp
        amp *= gain
        f *= lac
    return total / norm


# ---------------------------------------------------------------- sphere helpers
def sphere_rows(w, h, r0, r1):
    """Unit-sphere points and latitude (radians) for image rows [r0, r1)."""
    v = (np.arange(r0, r1, dtype=np.float32) + 0.5) / h
    u = (np.arange(w, dtype=np.float32) + 0.5) / w
    lon = (u - 0.5) * 2.0 * math.pi
    lat = (0.5 - v) * math.pi
    lon, lat = np.meshgrid(lon, lat)
    cl = np.cos(lat)
    return (cl * np.cos(lon), cl * np.sin(lon), np.sin(lat)), lat, lon


def chunked(w, h, fn, channels):
    out = np.zeros((h, w, channels), dtype=np.float32)
    for r0 in range(0, h, CHUNK):
        r1 = min(h, r0 + CHUNK)
        p, lat, lon = sphere_rows(w, h, r0, r1)
        out[r0:r1] = fn(p, lat, lon)
    return out


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(c0, c1, t):
    t = np.asarray(t, dtype=np.float32)
    if t.ndim >= 1:
        t = t[..., None]
    return c0 + (c1 - c0) * t


def col(hexs):
    hexs = hexs.lstrip("#")
    return np.array([int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def normal_from_height(hgt, strength):
    """Tangent-space normal from an equirect height map (DirectX convention, green = image down)."""
    h, w = hgt.shape
    lat = (0.5 - (np.arange(h, dtype=np.float32) + 0.5) / h) * math.pi
    sx = np.maximum(np.cos(lat), 0.05)[:, None]
    dx = (np.roll(hgt, -1, axis=1) - np.roll(hgt, 1, axis=1)) * 0.5 / sx
    up = np.vstack([hgt[:1], hgt[:-1]])
    dn = np.vstack([hgt[1:], hgt[-1:]])
    dy = (dn - up) * 0.5
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(hgt)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l, ny / l, nz / l], axis=-1) * 0.5 + 0.5


def save(name, arr, mode="RGB"):
    os.makedirs(OUT, exist_ok=True)
    a = np.clip(arr, 0.0, 1.0)
    if mode == "L" and a.ndim == 3:
        a = a[..., 0]
    img = Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), mode)
    path = os.path.join(OUT, name + ".png")
    img.save(path, optimize=True)
    print(f"wrote {path} {img.size}")


def area_quantile(values, lat, q):
    w = np.cos(lat).ravel()
    order = np.argsort(values.ravel())
    cw = np.cumsum(w[order])
    return values.ravel()[order][np.searchsorted(cw, q * cw[-1])]


# ---------------------------------------------------------------- Earth
def earth(size):
    W, H = size, size // 2
    n1, n2, n3, n4 = Noise3(11), Noise3(23), Noise3(37), Noise3(41)

    def height(p):
        warp = fbm(n2, p, 1.3, 4)
        warp2 = fbm(n3, p, 1.3, 4, offset=(4.2, 1.7, 8.1))
        q = (p[0] + 0.55 * warp, p[1] + 0.55 * warp2, p[2] + 0.35 * warp)
        base = fbm(n1, q, 1.15, 9, gain=0.52)
        return base + 0.18 * fbm(n4, p, 0.55, 3)  # continental-scale bias

    # sea level so that ~29 % of the area is land
    lp, llat, _ = sphere_rows(512, 256, 0, 256)
    sea = area_quantile(height(lp), llat, 0.70)

    def surface(p, lat, lon):
        h = height(p)
        e = h - sea
        land = smooth(-0.004, 0.006, e)
        mount = ridged(n3, p, 4.0, 6) * smooth(0.02, 0.12, e)
        elev = np.clip(e * 1.5 + mount * 0.32, 0.0, 1.0)
        alat = np.abs(lat) * (180.0 / math.pi)
        moist = fbm(n4, p, 2.6, 6, offset=(11.0, 3.0, 5.0)) * 0.55 + 0.5
        # subtropical deserts near 20-30 deg, wetter tropics and mid-latitudes
        moist = moist + 0.28 * np.exp(-((alat - 2.0) / 12.0) ** 2) - 0.32 * np.exp(-((alat - 24.0) / 9.0) ** 2) \
            + 0.12 * np.exp(-((alat - 52.0) / 14.0) ** 2) - 0.2 * smooth(0.25, 0.7, elev)
        temp = 1.0 - alat / 80.0 - elev * 0.35 + fbm(n2, p, 3.0, 3) * 0.12

        desert, savanna = col("#B89A6E"), col("#8C7F55")
        forest, jungle = col("#2E4A24"), col("#24401C")
        steppe, tundra = col("#6F6A4B"), col("#6E6A5E")
        rock, snow = col("#6A625A"), col("#E8ECEF")
        c = mix(desert, savanna, smooth(0.30, 0.48, moist))
        c = mix(c, forest, smooth(0.46, 0.62, moist))
        c = mix(c, jungle, smooth(0.6, 0.8, moist) * smooth(0.55, 0.8, temp))
        c = mix(c, steppe, smooth(0.35, 0.15, temp) * 0.6)
        c = mix(c, tundra, smooth(0.25, 0.08, temp))
        c = mix(c, rock, smooth(0.35, 0.7, elev) * 0.75)
        detail = fbm(n1, p, 22.0, 4) * 0.08
        c = c * (1.0 + detail[..., None])
        c = mix(c, snow, smooth(0.0, -0.12, temp))

        shelf = smooth(-0.05, -0.002, e)
        deep, mid, shallow = col("#04122A"), col("#0A2848"), col("#1B5265")
        oc = mix(deep, mid, smooth(-0.18, -0.05, e))
        oc = mix(oc, shallow, shelf * 0.85)
        oc = oc * (1.0 + fbm(n2, p, 9.0, 3)[..., None] * 0.06)
        out = mix(oc, c, land)

        ice_edge = 71.0 + fbm(n3, p, 3.0, 4) * 7.0
        ice = smooth(ice_edge - 1.5, ice_edge + 1.5, alat)
        out = mix(out, col("#E3EAF0") * (0.92 + 0.08 * fbm(n4, p, 12.0, 3)[..., None]), ice)

        # city lights: coastal, temperate, populated land; none on ice, deserts, high ground
        pop = fbm(n1, p, 7.0, 5, offset=(30.0, 9.0, 2.0)) * 0.5 + 0.5
        coast = smooth(0.09, 0.0, e) * land
        habit = land * smooth(0.25, 0.45, moist) * smooth(0.12, 0.35, temp) * (1.0 - ice) * smooth(0.6, 0.25, elev)
        speck = fbm(n2, p, 140.0, 2) * 0.5 + 0.5
        lights = np.clip((pop * 0.75 + coast * 0.45) * habit, 0, 1)
        lights = smooth(0.45, 0.75, lights) * smooth(0.45, 0.8, speck) * 1.2
        masks = np.stack([1.0 - land, np.clip(lights, 0, 1), elev * land], axis=-1)
        return np.concatenate([out, masks], axis=-1)

    data = chunked(W, H, surface, 6)
    save("T_Earth_Albedo", data[..., :3])
    save("T_Earth_Masks", data[..., 3:6])
    save("T_Earth_Normal", normal_from_height(data[..., 5], 9.0 * W / 4096.0))
    del data

    def clouds(p, lat, lon):
        alat = np.abs(lat) * (180.0 / math.pi)
        # zonal stretch: weather systems are elongated east-west
        q = (p[0] * 1.0, p[1] * 1.0, p[2] * 2.4)
        warp = fbm(n2, q, 3.0, 5)
        q2 = (q[0] + warp * 0.3, q[1] - warp * 0.24, q[2] + warp * 0.18)
        c = fbm(n3, q2, 4.2, 8, gain=0.56) * 0.5 + 0.5
        band = 0.16 * np.exp(-((alat - 4.0) / 8.0) ** 2) - 0.14 * np.exp(-((alat - 24.0) / 8.0) ** 2) \
            + 0.12 * np.exp(-((alat - 55.0) / 12.0) ** 2)
        c = smooth(0.52, 0.8, c + band) * 0.92
        wisps = smooth(0.55, 0.9, ridged(n4, q2, 9.0, 4)) * 0.25
        return np.clip(c + wisps * smooth(0.3, 0.6, c), 0, 1)[..., None]

    save("T_Earth_Clouds", chunked(W, H, clouds, 1), "L")


# ---------------------------------------------------------------- craters (Moon, Mars)
def stamp_craters(hgt, alb, seed, count, rmin, rmax, depth, bright, rays_fraction):
    """Adds impact craters (angular radius in radians) to height + albedo in place."""
    H, W = hgt.shape
    rng = np.random.default_rng(seed)
    # power-law size distribution: many small, few large
    u = rng.random(count)
    radii = rmin * (rmax / rmin) ** (u ** 4.5)
    dirs = rng.normal(size=(count, 3))
    dirs /= np.linalg.norm(dirs, axis=1)[:, None]
    ages = rng.random(count)
    for (dx, dy, dz), r, age in sorted(zip(dirs, radii, ages), key=lambda t: -t[1]):
        lat0 = math.asin(dz)
        lon0 = math.atan2(dy, dx)
        ext = r * (4.0 if age > 1.0 - rays_fraction else 1.8)
        r0 = max(0, int(((0.5 - (lat0 + ext) / math.pi)) * H))
        r1 = min(H, int(((0.5 - (lat0 - ext) / math.pi)) * H) + 2)
        p, lat, lon = sphere_rows(W, H, r0, r1)
        cosd = np.clip(p[0] * dx + p[1] * dy + p[2] * dz, -1.0, 1.0)
        d = np.arccos(cosd) / r
        sel = d < (4.0 if age > 1.0 - rays_fraction else 1.8)
        if not sel.any():
            continue
        dd = d[sel]
        fresh = 0.35 + 0.65 * age
        bowl = np.where(dd < 1.0, -(1.0 - dd * dd), 0.0) * depth * r * 40.0
        rim = np.exp(-((dd - 1.0) / 0.18) ** 2) * depth * r * 18.0
        if r > rmax * 0.45:  # large craters: flat floor + central peak
            bowl = np.maximum(bowl, -depth * r * 26.0) + np.exp(-(dd / 0.16) ** 2) * depth * r * 14.0
        hgt[r0:r1][sel] += (bowl + rim) * fresh
        a = alb[r0:r1]
        shade = np.where(dd < 1.0, -0.05, 0.0) + np.exp(-((dd - 1.0) / 0.25) ** 2) * bright * fresh
        if age > 1.0 - rays_fraction:
            ang = np.arctan2(p[1][sel] * dx - p[0][sel] * dy, p[2][sel] - cosd[sel] * dz)
            rays = (np.cos(ang * (7 + int(age * 9))) * 0.5 + 0.5) ** 6
            shade += rays * np.exp(-np.maximum(dd - 1.0, 0) / 1.2) * bright * 1.4 * (dd > 0.9)
        a[sel] = a[sel] + shade[:, None]


# ---------------------------------------------------------------- Moon
def moon(size):
    W, H = size, size // 2
    n1, n2, n3 = Noise3(101), Noise3(113), Noise3(127)

    def base(p, lat, lon):
        # maria: large dark basalt plains, concentrated on the near side (+X faces Earth)
        nearside = np.clip(p[0] * 0.6 + 0.45, 0, 1)
        m = fbm(n1, (p[0] + 0.3 * fbm(n2, p, 1.5, 3), p[1], p[2]), 1.4, 6) * 0.5 + 0.5
        maria = smooth(0.52, 0.6, m * (0.75 + 0.45 * nearside))
        high = col("#9A9894") * (0.9 + 0.2 * fbm(n3, p, 6.0, 5)[..., None])
        mare = col("#4E4F52") * (0.9 + 0.15 * fbm(n2, p, 10.0, 4)[..., None])
        c = mix(high, mare, maria)
        h = (1.0 - maria) * 0.6 + fbm(n3, p, 3.0, 7) * 0.25
        return np.concatenate([c, h[..., None]], axis=-1)

    data = chunked(W, H, base, 4)
    alb, hgt = data[..., :3].copy(), data[..., 3].copy()
    del data
    stamp_craters(hgt, alb, 7, 1400, 0.003, 0.12, 0.06, 0.045, 0.03)
    hgt += 0.05 * chunked(W, H, lambda p, la, lo: fbm(n1, p, 40.0, 4)[..., None], 1)[..., 0]
    save("T_Moon_Albedo", alb)
    save("T_Moon_Normal", normal_from_height(hgt * 0.6, 14.0 * W / 4096.0))


# ---------------------------------------------------------------- Mars
def mars(size):
    W, H = size, size // 2
    n1, n2, n3, n4 = Noise3(201), Noise3(211), Noise3(223), Noise3(227)

    def gc_dist(p, a_lat, a_lon, b_lat, b_lon):
        """Angular distance from the great-circle arc a->b (radians), plus progress along it."""
        a = np.array([math.cos(a_lat) * math.cos(a_lon), math.cos(a_lat) * math.sin(a_lon), math.sin(a_lat)])
        b = np.array([math.cos(b_lat) * math.cos(b_lon), math.cos(b_lat) * math.sin(b_lon), math.sin(b_lat)])
        nrm = np.cross(a, b)
        nrm /= np.linalg.norm(nrm)
        s = p[0] * nrm[0] + p[1] * nrm[1] + p[2] * nrm[2]
        proj_a = p[0] * a[0] + p[1] * a[1] + p[2] * a[2]
        proj_b = p[0] * b[0] + p[1] * b[1] + p[2] * b[2]
        span = math.acos(float(np.clip(a @ b, -1, 1)))
        t = np.arctan2(proj_b - proj_a * math.cos(span), proj_a * math.sin(span)) / span
        return np.abs(np.arcsin(np.clip(s, -1, 1))), t

    def bump(p, lat0, lon0, rad):
        d = np.arccos(np.clip(p[0] * math.cos(lat0) * math.cos(lon0) + p[1] * math.cos(lat0) * math.sin(lon0)
                              + p[2] * math.sin(lat0), -1, 1))
        return d / rad

    D = math.pi / 180.0

    def surface(p, lat, lon):
        alat = np.abs(lat) / D
        warp = fbm(n2, p, 1.6, 4)
        q = (p[0] + 0.4 * warp, p[1] + 0.4 * warp, p[2] + 0.25 * warp)
        dark = smooth(0.08, 0.32, fbm(n1, q, 1.5, 7))
        # southern highlands are older/darker, northern plains smoother and lighter
        dichotomy = smooth(-0.15, 0.25, -p[2] + 0.25 * fbm(n3, p, 1.2, 4))
        bright = col("#C47A4A")
        mid = col("#9E5634")
        darkc = col("#4E2D20")
        c = mix(bright, mid, smooth(0.2, 0.8, dichotomy * 0.7 + fbm(n4, p, 4.0, 5) * 0.5 + 0.2))
        c = mix(c, darkc, dark * 0.85)
        c = c * (0.9 + 0.18 * fbm(n3, p, 18.0, 4)[..., None])
        h = dichotomy * 0.35 + fbm(n1, p, 3.0, 7) * 0.2

        # Tharsis-like rise with three shield volcanoes and one giant
        tharsis = np.exp(-(bump(p, 2 * D, -110 * D, 1.0) / 0.35) ** 2)
        h += tharsis * 0.6
        for la, lo, rr, k in [(18, -134, 0.10, 1.6), (-9, -121, 0.05, 0.8), (1, -113, 0.05, 0.8), (12, -105, 0.05, 0.8)]:
            d = bump(p, la * D, lo * D, rr)
            cone = np.clip(1.0 - d, 0, 1) ** 1.6 * k
            caldera = np.exp(-(d / 0.12) ** 2) * k * 0.35
            h += cone - caldera
            c = mix(c, col("#B0704A"), np.clip(1.0 - d, 0, 1) * 0.35)

        # Valles-like canyon system east of the rise
        dist, t = gc_dist(p, -6 * D, -100 * D, -10 * D, -40 * D)
        width = (2.0 + 1.4 * np.sin(np.clip(t, 0, 1) * math.pi)) * D * (0.8 + 0.5 * fbm(n2, p, 12.0, 3))
        inside = (t > -0.02) & (t < 1.02)
        canyon = np.where(inside, smooth(1.0, 0.25, dist / width), 0.0)
        h -= canyon * 0.9
        c = mix(c, col("#5E3424"), canyon * 0.7)
        c = mix(c, col("#D08F60"), np.where(inside, np.exp(-((dist / width - 1.05) / 0.25) ** 2), 0) * 0.35)

        # Hellas-like basin
        hb = bump(p, -42 * D, 70 * D, 0.28)
        h -= np.clip(1.0 - hb, 0, 1) ** 1.5 * 0.7
        c = mix(c, col("#C98A5C"), np.clip(1.0 - hb, 0, 1) * 0.6)

        # polar caps (north larger, residual south), spiral troughs from domain warp
        edge_n = 80.5 + 3.0 * fbm(n4, p, 6.0, 4) + 1.5 * np.sin(lon * 3.0 + alat * 0.6)
        edge_s = 84.0 + 2.0 * fbm(n3, p, 6.0, 4)
        cap = np.where(lat > 0, smooth(edge_n - 1.0, edge_n + 1.0, alat), smooth(edge_s - 0.7, edge_s + 0.7, alat))
        troughs = smooth(0.62, 0.8, np.sin(np.arctan2(p[1], p[0]) * 2.0 + alat * 0.9 + fbm(n1, p, 6.0, 4) * 5.0) * 0.5 + 0.5)
        cap = cap * (1.0 - 0.14 * troughs * cap)
        c = mix(c, col("#EDE6DE"), cap)
        frost = smooth(64.0, 76.0, alat) * 0.25
        c = mix(c, col("#C9A890"), frost)
        return np.concatenate([c, h[..., None]], axis=-1)

    data = chunked(W, H, surface, 4)
    alb, hgt = data[..., :3].copy(), data[..., 3].copy()
    del data
    stamp_craters(hgt, alb, 9, 500, 0.003, 0.09, 0.035, 0.05, 0.015)
    hgt += 0.04 * chunked(W, H, lambda p, la, lo: ridged(n2, p, 30.0, 4)[..., None], 1)[..., 0]
    save("T_Mars_Albedo", alb)
    save("T_Mars_Normal", normal_from_height(hgt * 0.5, 10.0 * W / 4096.0))


# ---------------------------------------------------------------- starfield
def stars(size):
    W, H = size, size // 2
    n1, n2 = Noise3(301), Noise3(311)
    # galactic plane tilted ~60 degrees to the equator
    g = np.array([0.0, math.sin(math.radians(62.0)), math.cos(math.radians(62.0))], dtype=np.float32)

    lw, lh = W // 4, H // 4

    def galaxy(p, lat, lon):
        s = p[0] * g[0] + p[1] * g[1] + p[2] * g[2]
        band = np.exp(-(s / 0.16) ** 2)
        core = np.exp(-(((p[0] - 0.75) ** 2 + (p[1] + 0.35) ** 2 + (p[2] + 0.2) ** 2) / 0.35))
        dust = smooth(0.0, 0.5, fbm(n1, p, 5.0, 6) * 0.5 + 0.5)
        cloud = fbm(n2, p, 3.0, 6) * 0.5 + 0.5
        lum = band * (0.25 + 0.75 * cloud) * (1.0 - 0.75 * dust * np.exp(-(s / 0.05) ** 2)) * (0.5 + 0.9 * core)
        tint = mix(col("#4F5F7A"), col("#C9B79A"), np.clip(core * 1.4, 0, 1))
        neb = smooth(0.62, 0.9, fbm(n1, p, 2.0, 5, offset=(9.0, 2.0, 4.0)) * 0.5 + 0.5) * band
        return tint * lum[..., None] * 0.2 + col("#1F3A55") * neb[..., None] * 0.07

    low = chunked(lw, lh, galaxy, 3)
    bg = np.zeros((H, W, 3), dtype=np.float32)
    for ch in range(3):
        bg[..., ch] = np.asarray(Image.fromarray(low[..., ch].astype(np.float32), "F").resize((W, H), Image.BICUBIC))
    del low

    rng = np.random.default_rng(5)
    count = int(42000 * (W / 4096.0) ** 2)
    d = rng.normal(size=(count, 3)).astype(np.float32)
    d /= np.linalg.norm(d, axis=1)[:, None]
    # denser toward the galactic plane
    s = np.abs(d @ g)
    keep = rng.random(count) < (0.35 + 0.65 * np.exp(-(s / 0.25) ** 2))
    d = d[keep]
    mag = rng.random(len(d)) ** 9.0  # most stars faint, a few bright
    temp = rng.random(len(d))
    tint = np.where(temp[:, None] < 0.12, col("#9DB8FF"), np.where(temp[:, None] > 0.85, col("#FFD2A0"), col("#F2F4FF")))
    lat = np.arcsin(np.clip(d[:, 2], -1, 1))
    lon = np.arctan2(d[:, 1], d[:, 0])
    px = ((lon / (2 * math.pi)) + 0.5) * W
    py = (0.5 - lat / math.pi) * H
    stretch = 1.0 / np.maximum(np.cos(lat), 0.08)
    for x, y, m, t, sx in zip(px, py, mag, tint, stretch):
        b = 0.28 + 2.8 * m
        rad = 0.6 + 1.6 * m
        rx = rad * sx
        x0, x1 = int(x - rx - 1), int(x + rx + 2)
        y0, y1 = max(0, int(y - rad - 1)), min(H, int(y + rad + 2))
        ys = np.arange(y0, y1)[:, None] + 0.5
        xs = np.arange(x0, x1)[None, :] + 0.5
        f = np.exp(-(((xs - x) / (rx * 0.6)) ** 2 + ((ys - y) / (rad * 0.6)) ** 2))
        cols = np.arange(x0, x1) % W
        bg[y0:y1][:, cols] += f[..., None] * t * b
    # tone-map softly so bright stars keep a tight core
    bg = 1.0 - np.exp(-bg * 1.15)
    save("T_Space_Starfield", bg)


def black():
    save("T_Space_BlackLinear", np.zeros((8, 8, 3), dtype=np.float32))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=4096)
    ap.add_argument("--stars-size", type=int, default=8192)
    ap.add_argument("--only", default="earth,moon,mars,stars")
    a = ap.parse_args()
    jobs = a.only.split(",")
    if "earth" in jobs:
        earth(a.size)
    if "moon" in jobs:
        moon(a.size // 2)
    if "mars" in jobs:
        mars(a.size)
    if "stars" in jobs:
        stars(a.stars_size)
    black()
