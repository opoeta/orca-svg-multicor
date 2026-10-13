"""SVG Multicolor icon set in the main icon's design (docs/brand/icon-1254.png): navy tile,
soft 3D (extruded) shapes in orange / warm white / cyan, light from the top-left, Bezier nodes
with dashed cross-hairs.

    python tools/brand_icons.py

Writes docs/brand/icons/<id>.svg (standalone, 48x48 grid) and the three cursors there, and
puts the icons the panel uses (PANEL) and the cursors into ui/panel.html and ui/panel.css,
between their brand-icons / brand-cursors markers."""
import math
import os
import re
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "brand")
UI = os.path.join(ROOT, "src", "orca_svg_multicor", "ui")
# the icons the panel shows
PANEL = ["i-file", "i-refresh", "i-plate", "i-wand", "i-layers", "i-grid", "i-move", "i-pick", "i-brush",
         "i-bucket", "i-undo", "i-trash", "i-turn", "i-sliders", "i-view-result", "i-view-original",
         "i-view-object", "i-center", "i-fill", "i-fit", "i-apply", "i-add"]
G = 48  # drawing grid

# ---------------------------------------------------------------- tokens (measured on the main icon)
COL = {  # light, mid, dark, extrusion
    "o": ("#FFB062", "#F7801A", "#CF5C0B", "#93360A"),
    "w": ("#FFFFFF", "#ECE7E2", "#C4BCB5", "#8A8178"),
    "c": ("#86E8FA", "#18BFE3", "#0A8AB1", "#06627F"),
    "g": ("#6EDCA6", "#2FA36B", "#1E7A4E", "#14573A"),
    "a": ("#F8CB6A", "#E3A22F", "#B57B17", "#7E560F"),
    "r": ("#F48D90", "#E0555A", "#B4393E", "#82272B"),
}
DEPTH = (1.15, 1.55)
SHADOW = (1.7, 2.7)

DEFS = (
    '<linearGradient id="mc-tile" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#143562"/><stop offset=".55" stop-color="#0B2547"/><stop offset="1" stop-color="#061930"/>'
    '</linearGradient>'
    '<radialGradient id="mc-glow" cx="13" cy="7" r="30" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#FFFFFF" stop-opacity=".16"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>'
    '</radialGradient>'
    '<linearGradient id="mc-rim" x1="6" y1="4" x2="30" y2="30" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#FFFFFF" stop-opacity=".7"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>'
    '</linearGradient>'
    + "".join(
        f'<linearGradient id="mc-{k}" x1="8" y1="5" x2="40" y2="44" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{v[0]}"/><stop offset=".5" stop-color="{v[1]}"/><stop offset="1" stop-color="{v[2]}"/>'
        '</linearGradient>' for k, v in COL.items())
)


def n(v):
    t = ("%.2f" % v).rstrip("0").rstrip(".")
    return t if t not in ("-0", "") else "0"


INK = "#0A1626"


class Ic:
    def __init__(self, outline=False):
        self.parts, self.out, self.outline = [], [], outline

    def add(self, s):
        self.parts.append(s)
        return self

    # ---------------------------------------------------------------- background
    def tile(self):
        self.add('<rect x="1.5" y="1.5" width="45" height="45" rx="9" fill="url(#mc-tile)"/>')
        self.add('<rect x="1.5" y="1.5" width="45" height="45" rx="9" fill="url(#mc-glow)"/>')
        self.add('<rect x="2" y="2" width="44" height="44" rx="8.5" fill="none" stroke="#FFFFFF" stroke-opacity=".1"/>')
        return self

    # ---------------------------------------------------------------- volumes
    def solid(self, d, c, rim=True, depth=DEPTH, shadow=True):
        """A filled shape, extruded down-right, lit from the top-left."""
        ext = COL[c][3]
        if self.outline:
            self.out.append(f'<path d="{d}" fill="{INK}" stroke="{INK}" stroke-width="3.4" stroke-linejoin="round"/>')
            shadow = False
        if shadow:
            self.add(f'<path d="{d}" transform="translate({n(SHADOW[0])} {n(SHADOW[1])})" fill="#000" fill-opacity=".3"/>')
        for t in (1, .66, .33):
            self.add(f'<path d="{d}" transform="translate({n(depth[0] * t)} {n(depth[1] * t)})" fill="{ext}"/>')
        self.add(f'<path d="{d}" fill="url(#mc-{c})"/>')
        if rim:
            self.add(f'<path d="{d}" fill="none" stroke="url(#mc-rim)" stroke-width=".9" stroke-linejoin="round"/>')
        return self

    def flat(self, d, fill, opacity=None):
        o = f' fill-opacity="{n(opacity)}"' if opacity is not None else ""
        return self.add(f'<path d="{d}" fill="{fill}"{o}/>')

    def ribbon(self, d, c, w, cap="round", shine=True, depth=DEPTH, shadow=True):
        """A thick stroke (filament bead), extruded like solid()."""
        ext = COL[c][3]
        base = f'fill="none" stroke-width="{n(w)}" stroke-linecap="{cap}" stroke-linejoin="round"'
        if self.outline:
            self.out.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{n(w + 3.4)}" stroke-linecap="{cap}" '
                            f'stroke-linejoin="round"/>')
            shadow = False
        if shadow:
            self.add(f'<path d="{d}" transform="translate({n(SHADOW[0])} {n(SHADOW[1])})" {base} stroke="#000" stroke-opacity=".3"/>')
        for t in (1, .5):
            self.add(f'<path d="{d}" transform="translate({n(depth[0] * t)} {n(depth[1] * t)})" {base} stroke="{ext}"/>')
        self.add(f'<path d="{d}" {base} stroke="url(#mc-{c})"/>')
        if shine and w >= 3:
            self.add(f'<path d="{d}" transform="translate({n(-w * .14)} {n(-w * .18)})" fill="none" stroke="#FFFFFF" '
                     f'stroke-opacity=".38" stroke-width="{n(w * .26)}" stroke-linecap="round" stroke-linejoin="round"/>')
        return self

    def slab(self, cx, y, hw, hh, t, c):
        """An isometric slab: top rhombus centered at (cx, y), thickness t."""
        light, mid, dark, ext = COL[c]
        top = f"M{n(cx - hw)} {n(y)}L{n(cx)} {n(y - hh)}L{n(cx + hw)} {n(y)}L{n(cx)} {n(y + hh)}Z"
        left = f"M{n(cx - hw)} {n(y)}L{n(cx)} {n(y + hh)}V{n(y + hh + t)}L{n(cx - hw)} {n(y + t)}Z"
        right = f"M{n(cx)} {n(y + hh)}L{n(cx + hw)} {n(y)}V{n(y + t)}L{n(cx)} {n(y + hh + t)}Z"
        self.add(f'<path d="M{n(cx - hw)} {n(y + t)}L{n(cx)} {n(y + hh + t)}L{n(cx + hw)} {n(y + t)}L{n(cx + hw + 1.5)} {n(y + t + 2)}'
                 f'L{n(cx)} {n(y + hh + t + 2.6)}L{n(cx - hw + 1.5)} {n(y + t + 2)}Z" fill="#000" fill-opacity=".28"/>')
        self.add(f'<path d="{left}" fill="{mid}"/>')
        self.add(f'<path d="{right}" fill="{dark}"/>')
        self.add(f'<path d="{top}" fill="url(#mc-{c})"/>')
        self.add(f'<path d="M{n(cx - hw)} {n(y)}L{n(cx)} {n(y - hh)}L{n(cx + hw)} {n(y)}" fill="none" stroke="#FFFFFF" '
                 f'stroke-opacity=".55" stroke-width=".8" stroke-linejoin="round"/>')
        return self

    def cube(self, cx, cy, s, c):
        """An isometric cube; (cx, cy) = center of the top face."""
        return self.slab(cx, cy, s, s * .55, s * 1.05, c)

    # ---------------------------------------------------------------- details
    def sphere(self, x, y, r, c):
        light, mid, dark, ext = COL[c]
        self.add(f'<circle cx="{n(x + SHADOW[0] * .6)}" cy="{n(y + SHADOW[1] * .6)}" r="{n(r)}" fill="#000" fill-opacity=".3"/>')
        self.add(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{dark}"/>')
        self.add(f'<circle cx="{n(x - r * .12)}" cy="{n(y - r * .14)}" r="{n(r * .86)}" fill="{mid}"/>')
        self.add(f'<circle cx="{n(x - r * .3)}" cy="{n(y - r * .34)}" r="{n(r * .42)}" fill="{light}"/>')
        self.add(f'<circle cx="{n(x - r * .38)}" cy="{n(y - r * .42)}" r="{n(r * .17)}" fill="#FFFFFF" fill-opacity=".85"/>')
        return self

    def node(self, x, y, c, r=3.3):
        """Bezier node, as on the main icon: white ring, colored bead, specular dot."""
        self.add(f'<circle cx="{n(x + .8)}" cy="{n(y + 1.2)}" r="{n(r)}" fill="#000" fill-opacity=".3"/>')
        self.add(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="#F6F2EE"/>')
        self.add(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="none" stroke="#B9B1AA" stroke-width=".6"/>')
        self.add(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r * .6)}" fill="url(#mc-{c})"/>')
        self.add(f'<circle cx="{n(x - r * .22)}" cy="{n(y - r * .26)}" r="{n(r * .18)}" fill="#FFFFFF" fill-opacity=".9"/>')
        return self

    def cross(self, x, y, c, arm=7, gap=4.2):
        col = COL[c][1]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self.add(f'<path d="M{n(x + dx * gap)} {n(y + dy * gap)}L{n(x + dx * (gap + arm))} {n(y + dy * (gap + arm))}" '
                     f'stroke="{col}" stroke-width="1.4" stroke-dasharray="2.2 1.6" stroke-linecap="round"/>')
        return self

    def thin(self, d, color, w=1.4, dash=None, opacity=None):
        extra = (f' stroke-dasharray="{dash}"' if dash else "") + (f' stroke-opacity="{n(opacity)}"' if opacity else "")
        return self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{n(w)}" stroke-linecap="round" '
                        f'stroke-linejoin="round"{extra}/>')

    def head(self, x, y, ang, size, c):
        """Arrow head, tip at (x, y), pointing to `ang` degrees (screen: 0 = right, 90 = down)."""
        a = math.radians(ang)
        l, r = a + math.radians(145), a - math.radians(145)
        p = [(x, y), (x + size * math.cos(l), y + size * math.sin(l)), (x + size * math.cos(r), y + size * math.sin(r))]
        d = "M" + "L".join(f"{n(px)} {n(py)}" for px, py in p) + "Z"
        return self.solid(d, c, rim=False)

    def body(self):
        return "".join(self.out + self.parts)


# ---------------------------------------------------------------- geometry helpers
def rect(x, y, w, h, r=0):
    if not r:
        return f"M{n(x)} {n(y)}H{n(x + w)}V{n(y + h)}H{n(x)}Z"
    return (f"M{n(x + r)} {n(y)}H{n(x + w - r)}A{n(r)} {n(r)} 0 0 1 {n(x + w)} {n(y + r)}V{n(y + h - r)}"
            f"A{n(r)} {n(r)} 0 0 1 {n(x + w - r)} {n(y + h)}H{n(x + r)}A{n(r)} {n(r)} 0 0 1 {n(x)} {n(y + h - r)}"
            f"V{n(y + r)}A{n(r)} {n(r)} 0 0 1 {n(x + r)} {n(y)}Z")


def circle(x, y, r):
    return f"M{n(x - r)} {n(y)}A{n(r)} {n(r)} 0 1 0 {n(x + r)} {n(y)}A{n(r)} {n(r)} 0 1 0 {n(x - r)} {n(y)}Z"


def poly(*p):
    return "M" + "L".join(f"{n(x)} {n(y)}" for x, y in p) + "Z"


def line(*p):
    return "M" + "L".join(f"{n(x)} {n(y)}" for x, y in p)


def arc(cx, cy, r, a0, a1):
    """Arc from angle a0 to a1 (degrees, screen; a1 > a0 = clockwise). Returns (d, end point, end tangent angle)."""
    p0 = (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)))
    large = 1 if abs(a1 - a0) > 180 else 0
    sweep = 1 if a1 > a0 else 0
    d = f"M{n(p0[0])} {n(p0[1])}A{n(r)} {n(r)} 0 {large} {sweep} {n(p1[0])} {n(p1[1])}"
    tang = a1 + (90 if a1 > a0 else -90)
    return d, p1, tang


def bez(p0, p1, p2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def star(x, y, s):
    k = s * .22
    return (f"M{n(x)} {n(y - s)}Q{n(x + k)} {n(y - k)} {n(x + s)} {n(y)}Q{n(x + k)} {n(y + k)} {n(x)} {n(y + s)}"
            f"Q{n(x - k)} {n(y + k)} {n(x - s)} {n(y)}Q{n(x - k)} {n(y - k)} {n(x)} {n(y - s)}Z")


def sheet(x, y, w, h, fold):
    return f"M{n(x)} {n(y)}H{n(x + w - fold)}L{n(x + w)} {n(y + fold)}V{n(y + h)}H{n(x)}Z"


BLOB = ("M16 20C16 14.5 21.5 12.5 25 15.5C28.5 12 35 13.5 34.5 19C38.5 21 38 27.5 33.5 28.5"
        "C33.5 33.5 27.5 35 24.5 31.5C21 34.5 14.5 32.5 15.5 27.5C11.5 26.5 12 21 16 20Z")


def blob(dx=0, dy=0, k=1.0):
    """BLOB scaled by k about (25, 23.5) and moved."""
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", BLOB)]
    cmds = re.findall(r"[MCZ]", BLOB)
    out, i = [], 0
    for c in cmds:
        if c == "Z":
            out.append("Z")
            continue
        cnt = 2 if c == "M" else 6
        vals = nums[i:i + cnt]
        i += cnt
        pts = [(25 + (vals[j] - 25) * k + dx, 23.5 + (vals[j + 1] - 23.5) * k + dy) for j in range(0, cnt, 2)]
        out.append(c + " ".join(f"{n(px)} {n(py)}" for px, py in pts))
    return "".join(out)


# ---------------------------------------------------------------- the icons
ICONS = {}


def icon(fn):
    ICONS["i-" + fn.__name__.replace("_", "-")] = fn
    return fn


@icon
def file(i):
    i.solid(sheet(12, 7, 24, 33, 8), "w")
    i.flat("M28 7L36 15H30A2 2 0 0 1 28 13Z", COL["w"][2])
    i.ribbon("M16.5 31C19 19 25 37 31.5 24", "o", 3)
    i.node(16.5, 31, "o", 3).node(31.5, 24, "c", 3)


@icon
def wand(i):
    i.ribbon(line((12, 37), (27.5, 21.5)), "w", 4.6)
    i.ribbon(line((27.5, 21.5), (32.5, 16.5)), "o", 4.6)
    i.solid(star(36.5, 11.5, 5.2), "c", rim=False)
    i.solid(star(22.5, 11, 3.2), "o", rim=False)
    i.solid(star(38, 25.5, 3), "c", rim=False)


@icon
def grid(i):
    for (x, y), c in zip(((10, 10), (25, 10), (10, 25), (25, 25)), ("o", "c", "w", "o")):
        i.solid(rect(x, y, 12.5, 12.5, 3), c)


@icon
def layers(i):
    i.slab(24, 32, 14.5, 7, 3.4, "c")
    i.slab(24, 24.5, 14.5, 7, 3.4, "w")
    i.slab(24, 17, 14.5, 7, 3.4, "o")


@icon
def plate(i):
    i.slab(24, 31, 17, 7.5, 3.4, "w")
    i.cube(24, 20.5, 6.5, "o")


@icon
def refresh(i):
    d, p, a = arc(24, 24, 11, 200, 330)
    i.ribbon(d, "o", 4)
    i.head(p[0] + 2.6 * math.cos(math.radians(a)), p[1] + 2.6 * math.sin(math.radians(a)), a, 7, "o")
    d, p, a = arc(24, 24, 11, 20, 150)
    i.ribbon(d, "c", 4)
    i.head(p[0] + 2.6 * math.cos(math.radians(a)), p[1] + 2.6 * math.sin(math.radians(a)), a, 7, "c")


@icon
def sliders(i):
    for y, x, c in ((13.5, 30, "o"), (24, 18, "c"), (34.5, 27, "o")):
        i.ribbon(line((10.5, y), (37.5, y)), "w", 3, shine=False)
        i.sphere(x, y, 4.6, c)


@icon
def turn(i):
    i.solid(rect(11, 19, 19, 19, 3.5), "w")
    d, p, a = arc(21.5, 28.5, 15, -95, -5)
    i.ribbon(d, "c", 3.4)
    i.head(p[0] + 2.4 * math.cos(math.radians(a)), p[1] + 2.4 * math.sin(math.radians(a)), a, 6.5, "c")


@icon
def move(i):
    i.ribbon(line((24, 12), (24, 36)), "o", 3.6, shine=False)
    i.ribbon(line((12, 24), (36, 24)), "o", 3.6, shine=False)
    for x, y, a in ((24, 7.5, -90), (24, 40.5, 90), (7.5, 24, 180), (40.5, 24, 0)):
        i.head(x, y, a, 7.5, "o")
    i.sphere(24, 24, 4.4, "w")


@icon
def pick(i):
    i.ribbon(line((12.5, 35.5), (25.5, 22.5)), "w", 4.4)
    i.ribbon(line((10, 38), (12.5, 35.5)), "w", 2)
    i.ribbon(line((25, 23), (28.5, 19.5)), "c", 7.2, cap="butt")
    i.ribbon(line((29.5, 18.5), (34.5, 13.5)), "o", 8)
    i.solid("M8.5 39.5C8.5 41.5 9.5 43 10.8 43S13 41.5 13 39.5C13 38.3 11.6 36.6 10.8 35.6C10 36.6 8.5 38.3 8.5 39.5Z", "c",
            rim=False)


@icon
def brush(i):
    i.ribbon(line((37, 11), (26, 22)), "w", 4.6)
    i.ribbon(line((26.5, 21.5), (22.5, 25.5)), "c", 6.6, cap="butt")
    i.solid("M19.5 23.6L24.4 28.5C23 35 18 38.6 9.5 39C10 30.5 13.2 25 19.5 23.6Z", "o")


@icon
def bucket(i):
    i.thin("M15.5 18C15.5 9 30.5 9 30.5 18", COL["w"][2], 2)
    i.solid("M13 18H33L30.5 38.5C30.3 40 29 41 27.5 41H18.5C17 41 15.7 40 15.5 38.5Z", "w")
    i.flat("M13 18C13 15.8 33 15.8 33 18C33 20.2 13 20.2 13 18Z", COL["w"][3])
    i.solid("M30 17.5C35 17 38.5 21 38 27.5C37.7 31 36.2 32 35.5 32C34.5 32 34 31 34.2 28.5C34.6 23.5 33 20.5 30 20Z", "o",
            rim=False)
    i.solid("M33.5 35.5C33.5 33.8 35.3 32.6 35.3 32.6S37.1 33.8 37.1 35.5A1.8 1.8 0 0 1 33.5 35.5Z", "o", rim=False)


@icon
def undo(i):
    i.ribbon("M35 35C35 23 29.5 18 20 18H15.5", "c", 4.4)
    i.head(9, 18, 180, 8, "c")


@icon
def trash(i):
    i.solid("M14.5 17H33.5L31.5 39C31.3 40.2 30.3 41 29 41H19C17.7 41 16.7 40.2 16.5 39Z", "w")
    for x in (20.5, 24, 27.5):
        i.thin(line((x, 22), (x, 36)), COL["w"][2], 1.6)
    i.solid(rect(11.5, 11.5, 25, 4.6, 2.3), "o")
    i.solid(rect(19.5, 8, 9, 4.6, 1.8), "o", rim=False)


@icon
def fill(i):
    i.ribbon(rect(9.5, 9.5, 29, 29, 4), "w", 2.4, shine=False)
    i.solid(rect(15, 15, 18, 18, 2.5), "o")
    for x, y, a in ((13, 13, -135), (35, 13, -45), (13, 35, 135), (35, 35, 45)):
        i.head(x, y, a, 5.5, "c")


@icon
def center(i):
    i.ribbon(rect(9.5, 9.5, 29, 29, 4), "w", 2.4, shine=False)
    i.cross(24, 24, "o", arm=7.5, gap=4.6)
    i.node(24, 24, "o", 3.6)


@icon
def zoom(i):
    i.flat(circle(21, 21, 9.5), COL["c"][1], .35)
    i.ribbon(circle(21, 21, 9.5), "w", 4.2, shine=False)
    i.thin("M15.5 17.5A7 7 0 0 1 20 14", "#FFFFFF", 1.6, opacity=.8)
    i.ribbon(line((29, 29), (37.5, 37.5)), "o", 5.6)


@icon
def fit(i):
    for x, y, sx, sy in ((10, 10, 1, 1), (38, 10, -1, 1), (10, 38, 1, -1), (38, 38, -1, -1)):
        i.ribbon(line((x, y + sy * 8), (x, y), (x + sx * 8, y)), "o", 3.6, shine=False)
    i.solid(rect(17.5, 17.5, 13, 13, 2.5), "w")


@icon
def mirror(i):
    i.thin(line((24, 8), (24, 40)), COL["c"][1], 1.8, dash="3 2.2")
    i.solid(poly((20.5, 12), (20.5, 36), (8.5, 36)), "o")
    i.solid(poly((27.5, 12), (27.5, 36), (39.5, 36)), "w")


@icon
def apply(i):
    i.slab(24, 33, 17, 7.5, 3.4, "w")
    i.ribbon(line((24, 8), (24, 21)), "o", 4.8, shine=False)
    i.head(24, 30, 90, 9, "o")


@icon
def add(i):
    i.slab(22, 32, 15.5, 7, 3.2, "w")
    i.cube(22, 22.5, 6, "o")
    i.ribbon(line((36, 6.5), (36, 17.5)), "c", 3.6, shine=False)
    i.ribbon(line((30.5, 12), (41.5, 12)), "c", 3.6, shine=False)


# the design's footprint on the block's top face, next to its front-left edge
P1, P2, P3, P4 = (12, 22.3), (21, 26.2), (26.25, 23.93), (17.25, 20.03)


def block(i):
    i.slab(24, 21, 15, 6.5, 11, "w")


@icon
def inlay(i):
    # the color goes into the block: flush on top, and seen going down on the side
    block(i)
    i.flat(poly(P1, P2, P3, P4), "url(#mc-o)")
    i.flat(poly(P1, P2, (P2[0], P2[1] + 5), (P1[0], P1[1] + 5)), COL["o"][2])
    i.thin(line(P4, P1, P2), "#FFFFFF", .8, opacity=.55)


@icon
def raised(i):
    # the color stands on the block
    block(i)
    up = [(x, y - 4.5) for x, y in (P1, P2, P3, P4)]
    i.flat(poly(P1, P2, up[1], up[0]), COL["o"][1])
    i.flat(poly(P2, P3, up[2], up[1]), COL["o"][2])
    i.flat(poly(*up), "url(#mc-o)")
    i.thin(line(up[3], up[0], up[1]), "#FFFFFF", .8, opacity=.6)


@icon
def base_outline(i):
    i.solid(blob(0, 4, 1.42), "w")
    i.solid(blob(0, .5, 1.0), "o")


@icon
def base_rect(i):
    i.solid(rect(7.5, 10.5, 33, 30, 5), "w")
    i.solid(blob(0, 2, .95), "o")


@icon
def first_layer(i):
    i.slab(24, 34.5, 14.5, 6.5, 3, "o")
    i.slab(24, 28.5, 14.5, 6.5, 3, "w")
    i.slab(24, 22.5, 14.5, 6.5, 3, "w")
    i.slab(24, 16.5, 14.5, 6.5, 3, "w")


@icon
def position(i):
    for r in range(3):
        for c in range(3):
            i.solid(rect(10.5 + c * 10, 10.5 + r * 10, 7, 7, 1.8), "o" if (r, c) == (0, 0) else "w", rim=False)


@icon
def reset_color(i):
    i.solid(rect(9, 17, 20, 20, 4), "o")
    d, p, a = arc(28, 20, 9.5, 160, 380)
    i.ribbon(d, "c", 3.4, shine=False)
    i.head(p[0] + 2.4 * math.cos(math.radians(a)), p[1] + 2.4 * math.sin(math.radians(a)), a, 6.5, "c")


@icon
def view_result(i):
    cx, cy, r = 23.5, 24.5, 13.5
    for k, c in enumerate(("o", "w", "c")):
        a0, a1 = -90 + k * 120 + 4, -90 + (k + 1) * 120 - 4
        mid = math.radians((a0 + a1) / 2)
        ox, oy = cx + 2.6 * math.cos(mid), cy + 2.6 * math.sin(mid)
        p0 = (ox + r * math.cos(math.radians(a0)), oy + r * math.sin(math.radians(a0)))
        p1 = (ox + r * math.cos(math.radians(a1)), oy + r * math.sin(math.radians(a1)))
        i.solid(f"M{n(ox)} {n(oy)}L{n(p0[0])} {n(p0[1])}A{n(r)} {n(r)} 0 0 1 {n(p1[0])} {n(p1[1])}Z", c)


@icon
def view_original(i):
    p0, p1, p2, p3 = (10, 33), (17, 9), (31, 39), (38, 15)
    i.thin(line(p0, p1), COL["o"][1], 1.3, dash="2.2 1.6")
    i.thin(line(p3, p2), COL["c"][1], 1.3, dash="2.2 1.6")
    i.ribbon(f"M{n(p0[0])} {n(p0[1])}C{n(p1[0])} {n(p1[1])} {n(p2[0])} {n(p2[1])} {n(p3[0])} {n(p3[1])}", "w", 3.6)
    i.sphere(p1[0], p1[1], 2, "o").sphere(p2[0], p2[1], 2, "c")
    i.node(p0[0], p0[1], "o", 3.4).node(p3[0], p3[1], "c", 3.4)


@icon
def view_object(i):
    i.cube(24, 17.5, 12, "w")
    # the design on the cube's left face
    i.flat("M15 25.5L22 29.3V36.8L15 33Z", COL["o"][1])
    i.flat("M15 25.5L22 29.3V31.2L15 27.4Z", COL["o"][0])


def edge_icon(i, count):
    p0, p1, p2, p3 = (9, 34), (17, 9), (31, 39), (39, 14)
    i.ribbon(f"M{n(p0[0])} {n(p0[1])}C{n(p1[0])} {n(p1[1])} {n(p2[0])} {n(p2[1])} {n(p3[0])} {n(p3[1])}", "w", 3.4)
    for k in range(count):
        x, y = bez(p0, p1, p2, p3, k / (count - 1))
        i.node(x, y, "o" if k % 2 == 0 else "c", 2.9 if count > 3 else 3.3)


@icon
def edge_detailed(i):
    edge_icon(i, 5)


@icon
def edge_normal(i):
    edge_icon(i, 3)


@icon
def edge_simple(i):
    edge_icon(i, 2)


@icon
def batch(i):
    i.solid(sheet(18, 7, 21, 27, 6), "w", rim=False)
    i.solid(sheet(14, 11, 21, 27, 6), "w", rim=False)
    i.solid(sheet(10, 15, 21, 27, 6), "w")
    i.ribbon("M13.5 34C15.5 24 20 38 26 28", "o", 2.8)


@icon
def window(i):
    i.solid(rect(8, 10, 32, 28, 4), "w")
    i.solid("M12 10H36A4 4 0 0 1 40 14V17H8V14A4 4 0 0 1 12 10Z", "c", shadow=False, depth=(0, 0))
    i.solid(rect(14, 22, 11, 10, 2), "o", rim=False)


@icon
def backup(i):
    i.solid(sheet(9, 7, 22, 30, 7), "w")
    i.flat("M24 7L31 14H26A2 2 0 0 1 24 12Z", COL["w"][2])
    i.solid(circle(32, 32, 9), "o")
    i.thin(line((32, 26.5), (32, 32), (36, 34)), "#FFFFFF", 2.2)


@icon
def export(i):
    i.solid("M11 24H37V38A3 3 0 0 1 34 41H14A3 3 0 0 1 11 38Z", "w")
    i.flat("M11 24H37L34 21H14Z", COL["w"][3])
    i.ribbon(line((24, 31), (24, 14)), "o", 4.8, shine=False)
    i.head(24, 6.5, -90, 9, "o")


@icon
def ok(i):
    i.solid(circle(24, 24, 15), "g")
    i.ribbon(line((17, 24.5), (22, 29.5), (31.5, 18.5)), "w", 4, shine=False, depth=(.6, .8), shadow=False)


@icon
def warn(i):
    i.solid("M21.4 9.5C22.6 7.5 25.4 7.5 26.6 9.5L40.5 34.5C41.6 36.5 40.2 39 37.9 39H10.1C7.8 39 6.4 36.5 7.5 34.5Z", "a")
    i.ribbon(line((24, 17), (24, 28)), "w", 4, shine=False, depth=(.6, .8), shadow=False)
    i.sphere(24, 33.5, 2.4, "w")


@icon
def error(i):
    i.solid(circle(24, 24, 15), "r")
    i.ribbon(line((18, 18), (30, 30)), "w", 4, shine=False, depth=(.6, .8), shadow=False)
    i.ribbon(line((30, 18), (18, 30)), "w", 4, shine=False, depth=(.6, .8), shadow=False)


@icon
def busy(i):
    i.thin(circle(24, 24, 12), "#FFFFFF", 4, opacity=.14)
    d, p, a = arc(24, 24, 12, -90, 150)
    i.ribbon(d, "c", 4, shine=False)
    i.sphere(p[0], p[1], 3.2, "o")


# ---------------------------------------------------------------- output
def between(path, start, end, text):
    """Replaces what is between two markers of a file (the markers stay)."""
    s = open(path, encoding="utf-8").read()
    a, b = s.index(start) + len(start), s.index(end)
    open(path, "w", encoding="utf-8", newline="\n").write(s[:a] + text + s[b:])


os.makedirs(os.path.join(OUT, "icons"), exist_ok=True)
symbols = {}
for name, fn in ICONS.items():
    ic = Ic().tile()
    fn(ic)
    body = ic.body()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {G} {G}"><title>{name}</title>'
           f'<defs>{DEFS}</defs><g fill="none" stroke="none">{body}</g></svg>\n')
    open(os.path.join(OUT, "icons", name + ".svg"), "w", encoding="utf-8").write(svg)
    symbols[name] = f'<symbol id="{name}" viewBox="0 0 {G} {G}"><g fill="none" stroke="none">{body}</g></symbol>'
between(os.path.join(UI, "panel.html"), "<!-- brand-icons:start -->", "<!-- brand-icons:end -->",
        f'\n<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>{DEFS}</defs>'
        + "".join(symbols[k] for k in PANEL) + "</svg>\n")


# ---------------------------------------------------------------- cursors (no tile, dark outline, 32 px)
def cursor_pick(i):
    i.ribbon(line((12.5, 35.5), (25.5, 22.5)), "w", 4.4)
    i.ribbon(line((9.5, 38.5), (12.5, 35.5)), "w", 2)
    i.ribbon(line((25, 23), (28.5, 19.5)), "c", 7.2, cap="butt")
    i.ribbon(line((29.5, 18.5), (34.5, 13.5)), "o", 8)


CURSORS = {  # name: (draw, hotspot in the 48 grid)
    "cursor-brush": (brush, (9.5, 39)),
    "cursor-bucket": (bucket, (35.3, 37.3)),
    "cursor-eyedropper": (cursor_pick, (9.5, 38.5)),
}
notes, css = [], {}
for name, (fn, (hx, hy)) in CURSORS.items():
    ic = Ic(outline=True)
    fn(ic)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 {G} {G}"><title>{name}</title>'
           f'<defs>{DEFS}</defs><g fill="none" stroke="none">{ic.body()}</g></svg>\n')
    open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8").write(svg)
    hot = f"{round(hx * 32 / G)} {round(hy * 32 / G)}"
    notes.append(f"{name}.svg: hotspot ({hot.replace(' ', ', ')}) at 32 px")
    data = quote(re.sub(r"<title>.*?</title>", "", svg.strip()), safe=" =:/(),.-")
    css[name] = f'url("data:image/svg+xml,{data}") {hot}'
open(os.path.join(OUT, "cursor-hotspots.txt"), "w", encoding="utf-8").write("\n".join(notes) + "\n")
between(os.path.join(UI, "panel.css"), "/* brand-cursors:start */", "/* brand-cursors:end */",
        "\n#preview_place.tool-brush, #preview_place.tool-brush * { cursor: " + css["cursor-brush"] + ", crosshair; }"
        "\n#preview_place.tool-pick, #preview_place.tool-pick *,"
        "\n#preview_place.picking, #preview_place.picking * { cursor: " + css["cursor-eyedropper"] + ", copy; }"
        "\n#preview_place.tool-bucket, #preview_place.tool-bucket * { cursor: " + css["cursor-bucket"] + ", cell; }\n")
print(len(ICONS), "icons,", len(CURSORS), "cursors; panel:", len(PANEL), "icons")
