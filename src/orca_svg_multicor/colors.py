# -*- coding: utf-8 -*-
"""
Color math: parsing, perceptual distance (CIEDE2000), naming, merging similar
tones and reducing the palette to the number of filaments available.

Everything here works on "#rrggbb" strings. Distances are CIEDE2000 (Delta E),
which follows what the eye sees far better than RGB distance: two whites that
differ by 12 RGB units are ~3 Delta E apart, while a dark blue and a black that
differ by the same 12 units are much more distinct.
"""

import math

from shapely.geometry.polygon import orient
from shapely.ops import unary_union

# Named reference colors. The keys are translated through i18n ("color.<key>").
NAMED_COLORS = {
    "black": (0, 0, 0),
    "dark_gray": (64, 64, 64),
    "gray": (128, 128, 128),
    "light_gray": (192, 192, 192),
    "white": (255, 255, 255),
    "red": (220, 30, 30),
    "maroon": (128, 20, 30),
    "orange": (245, 130, 20),
    "yellow": (245, 210, 40),
    "gold": (212, 175, 55),
    "beige": (225, 200, 165),
    "brown": (120, 70, 40),
    "olive": (128, 128, 0),
    "lime": (150, 215, 50),
    "green": (40, 160, 60),
    "dark_green": (0, 90, 40),
    "teal": (0, 128, 128),
    "cyan": (40, 190, 210),
    "sky_blue": (120, 180, 235),
    "blue": (40, 80, 200),
    "navy": (20, 30, 90),
    "purple": (130, 50, 180),
    "magenta": (220, 40, 160),
    "pink": (240, 140, 180),
}


def hex_to_rgb(hexa):
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def normalize_hex(value):
    """Returns '#rrggbb' in lower case, or None if `value` is not a hex color."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if not v.startswith("#"):
        return None
    h = v[1:]
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    elif len(h) in (6, 8):
        h = h[:6]
    else:
        return None
    try:
        int(h, 16)
    except ValueError:
        return None
    return "#" + h


def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb):
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 216.0 / 24389.0 else (24389.0 / 27.0 * t + 16.0) / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


_LAB_CACHE = {}


def lab(hexa):
    v = _LAB_CACHE.get(hexa)
    if v is None:
        v = rgb_to_lab(hex_to_rgb(hexa))
        _LAB_CACHE[hexa] = v
    return v


def delta_e(lab1, lab2):
    """CIEDE2000 color difference between two Lab triples."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    cm = (c1 + c2) / 2.0
    g = 0.5 * (1.0 - math.sqrt(cm ** 7 / (cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1.0 + g) * a1, (1.0 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180.0:
            dhp -= 360.0
        elif dhp < -180.0:
            dhp += 360.0
    dHp = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2.0)

    Lpm = (L1 + L2) / 2.0
    Cpm = (c1p + c2p) / 2.0
    if c1p * c2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hpm = (h1p + h2p) / 2.0
    elif h1p + h2p < 360.0:
        hpm = (h1p + h2p + 360.0) / 2.0
    else:
        hpm = (h1p + h2p - 360.0) / 2.0

    t = (1.0 - 0.17 * math.cos(math.radians(hpm - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hpm))
         + 0.32 * math.cos(math.radians(3.0 * hpm + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hpm - 63.0)))
    d_theta = 30.0 * math.exp(-(((hpm - 275.0) / 25.0) ** 2))
    rc = 2.0 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25.0 ** 7))
    sl = 1.0 + (0.015 * (Lpm - 50.0) ** 2) / math.sqrt(20.0 + (Lpm - 50.0) ** 2)
    sc = 1.0 + 0.045 * Cpm
    sh = 1.0 + 0.015 * Cpm * t
    rt = -math.sin(math.radians(2.0 * d_theta)) * rc
    return math.sqrt((dLp / sl) ** 2 + (dCp / sc) ** 2 + (dHp / sh) ** 2
                     + rt * (dCp / sc) * (dHp / sh))


def color_distance(hex1, hex2):
    """Perceptual distance (CIEDE2000) between two '#rrggbb' colors, 0..~100."""
    return delta_e(lab(hex1), lab(hex2))


_NAMED_LAB = {k: rgb_to_lab(v) for k, v in NAMED_COLORS.items()}


def color_name_key(hexa):
    """Key of the closest named color ('black', 'sky_blue', ...)."""
    target = lab(hexa)
    return min(_NAMED_LAB, key=lambda k: delta_e(target, _NAMED_LAB[k]))


def average_color(hexes, weights=None):
    """Average of colors in linear light, which is how pigments/light mix."""
    if not hexes:
        return None
    weights = weights or [1.0] * len(hexes)
    tot = float(sum(weights)) or 1.0
    acc = [0.0, 0.0, 0.0]
    for h, w in zip(hexes, weights):
        for i, c in enumerate(hex_to_rgb(h)):
            acc[i] += _srgb_to_linear(c) * w
    out = []
    for c in acc:
        c /= tot
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055
        out.append(c * 255.0)
    return rgb_to_hex(out)


# ----------------------------------------------------------------------------
# merging colors
# ----------------------------------------------------------------------------
def _area(polys):
    return sum(p.area for p in polys)


def _fuse(regions, groups):
    """groups: {representative: [colors]} -> regions with the areas united."""
    out = {}
    for rep, members in groups.items():
        polys = []
        for c in members:
            polys.extend(regions[c])
        if len(members) > 1:
            u = unary_union(polys)
            parts = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
            polys = [orient(p, 1.0) for p in parts
                     if p.geom_type == "Polygon" and p.area > 1e-9]
        out[rep] = polys
    return out


def merge_similar(regions, tolerance):
    """
    Joins colors closer than `tolerance` (Delta E) into a single part.
    Vector exporters often leave #ffffff, #fefefe and #feffff as distinct
    colors. The color with the largest area becomes the representative.

    Returns (regions, mapping) where mapping[representative] = [colors].
    """
    if not tolerance or tolerance <= 0:
        return regions, {c: [c] for c in regions}
    order = sorted(regions, key=lambda c: -_area(regions[c]))
    mapping = {}
    for color in order:
        target = next((r for r in mapping if color_distance(r, color) <= tolerance),
                      None)
        if target is None:
            mapping[color] = [color]
        else:
            mapping[target].append(color)
    return _fuse(regions, mapping), mapping


def reduce_colors(regions, maximum, pre_tolerance=4.0):
    """
    Merges colors until at most `maximum` parts remain, so the result fits the
    printer's filaments. Returns (regions, mapping) in terms of the ORIGINAL
    colors.

    1. Collapses practically identical tones (`pre_tolerance`). Without this,
       two large identical whites never merge (neither is the smallest), and
       a legitimate color would be sacrificed instead.
    2. While there are too many parts, the SMALLEST one is merged into the
       most similar remaining color. Always merging the smallest protects the
       dominant colors: in a logo with 41% black and 0.04% brown, the brown
       disappears into something similar and the black stays black.
    """
    identity = {c: [c] for c in regions}
    if not maximum or maximum <= 0 or len(regions) <= maximum:
        return regions, identity

    map1 = identity
    if pre_tolerance:
        regions, map1 = merge_similar(regions, pre_tolerance)
        if len(regions) <= maximum:
            return regions, map1

    work = {c: [c] for c in regions}
    area = {c: _area(regions[c]) for c in regions}
    while len(work) > maximum:
        smallest = min(work, key=lambda c: area[c])
        target = min((c for c in work if c != smallest),
                     key=lambda c: (color_distance(smallest, c), -area[c]))
        work[target].extend(work.pop(smallest))
        area[target] += area.pop(smallest)

    merged = _fuse(regions, work)
    mapping = {rep: [o for m in members for o in map1.get(m, [m])]
               for rep, members in work.items()}
    return merged, mapping


def chain_mappings(first, second):
    """Composes two {rep: [members]} mappings into one on the original colors."""
    return {rep: [c for m in members for c in first.get(m, [m])]
            for rep, members in second.items()}


def match_filaments(colors, filaments):
    """
    Suggests a filament for each color.

    colors:    ["#rrggbb", ...]
    filaments: [{"n": 1, "color": "#rrggbb"}, ...] (entries without color are
               skipped)
    Returns {color: (filament_number, delta_e)}; colors are left out when no
    filament has a known color.
    """
    known = [f for f in filaments if normalize_hex(f.get("color"))]
    out = {}
    if not known:
        return out
    for c in colors:
        best = min(known, key=lambda f: color_distance(c, normalize_hex(f["color"])))
        out[c] = (int(best["n"]), round(color_distance(c, normalize_hex(best["color"])), 1))
    return out
