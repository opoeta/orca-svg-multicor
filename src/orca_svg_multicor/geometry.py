# -*- coding: utf-8 -*-
"""
Geometry: paint operations -> one clean 2D region per color, in millimeters.

Pipeline
  1. every paint operation becomes a shapely geometry, honoring its fill rule
     (nonzero or evenodd) exactly, strokes included;
  2. occlusion: each operation keeps only what is not covered by operations
     painted after it, exactly like the SVG is displayed;
  3. the visible pieces of each color are united, simplified and cleaned.

After step 2 the colors tile the plane without overlapping, so the printed
parts fit together instead of fighting over the same volume.
"""

import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import (LinearRing, LineString,
                              MultiPolygon, Polygon, box)
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from .errors import Cancelled  # noqa: F401 - re-exported
from .svgread import flatten

GRID = 1e-4          # mm; snap-rounding grid for robust overlays


class Frame:
    """
    Maps SVG pixels to printer millimeters: centered on (cx, cy), scaled by
    `scale` mm per px, Y flipped to point up.
    """

    def __init__(self, cx, cy, scale):
        self.cx, self.cy, self.scale = cx, cy, scale

    @classmethod
    def for_bbox(cls, bbox, scale):
        x0, y0, x1, y1 = bbox
        return cls((x0 + x1) / 2.0, (y0 + y1) / 2.0, scale)

    def apply(self, pts):
        out = np.empty_like(pts)
        out[:, 0] = (pts[:, 0] - self.cx) * self.scale
        out[:, 1] = -(pts[:, 1] - self.cy) * self.scale
        return out


def polygons_of(geom):
    """All polygons inside any shapely geometry."""
    if geom is None or geom.is_empty:
        return []
    t = geom.geom_type
    if t == "Polygon":
        return [geom]
    if t in ("MultiPolygon", "GeometryCollection"):
        out = []
        for g in geom.geoms:
            out.extend(polygons_of(g))
        return out
    return []


def _as_area(geom):
    polys = [p for p in polygons_of(geom) if p.area > 0]
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def _valid(poly):
    if poly.is_valid:
        return poly
    return shapely.make_valid(poly)


# ----------------------------------------------------------------------------
# fill rules
# ----------------------------------------------------------------------------
def _signed_area(pts):
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _winding(ring, px, py):
    """Winding number of the closed ring (Nx2, not repeated) around (px, py)."""
    x0, y0 = ring[:, 0], ring[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    cross = (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0)
    up = (y0 <= py) & (y1 > py) & (cross > 0)
    down = (y0 > py) & (y1 <= py) & (cross < 0)
    return int(up.sum()) - int(down.sum())


def _closed_rings(subpaths):
    rings = []
    for pts, _closed in subpaths:
        if len(pts) >= 2 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        if len(pts) < 3:
            continue
        if abs(_signed_area(pts)) < 1e-12:
            continue
        rings.append(pts)
    return rings


def fill_region(rings, rule):
    """
    Exact filled region of one SVG element.

    Rings that do not cross each other (the usual case) are resolved through a
    nesting tree: the winding number of the area inside ring i and outside its
    children is the sum of the directions of i and all its ancestors. Rings
    that cross are resolved through the planar faces of the whole drawing,
    testing the winding number at a point inside each face.
    """
    if not rings:
        return None
    polys, bad = [], False
    for r in rings:
        p = Polygon(r)
        if not p.is_valid:
            bad = True
            break
        polys.append(p)
    if not bad and len(polys) > 1:
        bounds = [LinearRing(r) for r in rings]
        tree = STRtree(bounds)
        a, b = tree.query(bounds, predicate="intersects")
        if np.any(a != b):
            bad = True
    if bad:
        return _fill_by_faces(rings, rule)
    return _fill_by_nesting(rings, polys, rule)


def _fill_by_nesting(rings, polys, rule):
    n = len(polys)
    if n == 1:
        return polys[0]
    areas = np.array([p.area for p in polys])
    dirs = [1 if _signed_area(r) > 0 else -1 for r in rings]
    tree = STRtree(polys)
    parent = [-1] * n
    for i in range(n):
        pt = shapely.points(rings[i][0])
        cands = [j for j in tree.query(pt, predicate="within") if j != i]
        if cands:
            parent[i] = min(cands, key=lambda j: areas[j])
    order = sorted(range(n), key=lambda i: -areas[i])  # parents before children
    wind = [0] * n
    depth = [0] * n
    for i in order:
        p = parent[i]
        wind[i] = (wind[p] if p >= 0 else 0) + dirs[i]
        depth[i] = (depth[p] + 1) if p >= 0 else 0
    children = [[] for _ in range(n)]
    for i, p in enumerate(parent):
        if p >= 0:
            children[p].append(i)
    faces = []
    for i in range(n):
        filled = (wind[i] != 0) if rule == "nonzero" else (depth[i] % 2 == 0)
        if not filled:
            continue
        face = polys[i]
        if children[i]:
            face = face.difference(unary_union([polys[j] for j in children[i]]),
                                   grid_size=GRID)
        faces.append(face)
    if not faces:
        return None
    return shapely.union_all(faces, grid_size=GRID)


def _fill_by_faces(rings, rule):
    lines = [LineString(np.vstack([r, r[:1]])) for r in rings]
    noded = unary_union(lines)
    filled = []
    for face in polygonize(noded):
        if face.area <= 0:
            continue
        pt = face.representative_point()
        w = sum(_winding(r, pt.x, pt.y) for r in rings)
        if (w != 0) if rule == "nonzero" else (w % 2 != 0):
            filled.append(face)
    if not filled:
        return None
    return shapely.union_all(filled, grid_size=GRID)


def stroke_region(subpaths, width, cap=2, join=2, miter=4.0):
    """Area covered by a stroke of `width` mm along every subpath."""
    parts = []
    half = width / 2.0
    for pts, closed in subpaths:
        if len(pts) < 2:
            continue
        if closed and len(pts) >= 3:
            ring = pts if np.allclose(pts[0], pts[-1]) else np.vstack([pts, pts[:1]])
            if len(ring) >= 4:
                parts.append(LinearRing(ring).buffer(half, join_style=join,
                                                     mitre_limit=miter))
                continue
        parts.append(LineString(pts).buffer(half, cap_style=cap, join_style=join,
                                            mitre_limit=miter))
    if not parts:
        return None
    return shapely.union_all(parts, grid_size=GRID)


# ----------------------------------------------------------------------------
# document -> visible region per color
# ----------------------------------------------------------------------------
def op_geometries(doc, frame, step_mm, progress=None):
    """[(color, geometry_mm), ...] in paint order."""
    step_px = step_mm / frame.scale
    out = []
    total = len(doc.ops)
    for k, op in enumerate(doc.ops):
        if progress and k % 25 == 0:
            progress(k / max(total, 1))
        subpaths = [(frame.apply(p), c) for p, c in flatten(op.path, step_px)]
        if op.kind == "fill":
            geom = fill_region(_closed_rings(subpaths), op.rule)
        else:
            width = op.width * frame.scale
            if width <= 0:
                continue
            geom = stroke_region(subpaths, width, op.cap, op.join, op.miter)
        geom = _as_area(geom) if geom is not None else None
        if geom is not None:
            geom = _as_area(_valid(geom))
        if geom is not None:
            out.append((op.color, geom))
    return out


def visible_parts(ops, progress=None):
    """
    Painter's algorithm. Each geometry loses whatever later geometries cover.
    Returns [(color, visible_geometry), ...] without empty entries.
    """
    geoms = [g for _, g in ops]
    if not geoms:
        return []
    tree = STRtree(geoms)
    out = []
    n = len(geoms)
    for i, (color, g) in enumerate(ops):
        if progress and i % 25 == 0:
            progress(i / max(n, 1))
        later = [j for j in tree.query(g, predicate="intersects") if j > i]
        if later:
            cover = shapely.union_all([geoms[j] for j in later], grid_size=GRID)
            g = g.difference(cover, grid_size=GRID)
        g = _as_area(g)
        if g is not None:
            out.append((color, g))
    return out


def clean(geom, tolerance, min_area):
    """Simplifies and drops specks/holes smaller than `min_area` mm2."""
    geom = _as_area(geom)
    if geom is None:
        return []
    if tolerance > 0:
        geom = geom.simplify(tolerance, preserve_topology=True)
    geom = _as_area(shapely.make_valid(geom)) if geom is not None else None
    if geom is None:
        return []
    out = []
    for p in polygons_of(geom):
        if p.area < max(min_area, 1e-9):
            continue
        holes = [h for h in p.interiors if Polygon(h).area >= max(min_area, 1e-9)]
        if len(holes) != len(p.interiors):
            p = Polygon(p.exterior, holes)
            if not p.is_valid:
                p = _as_area(shapely.make_valid(p))
                if p is None:
                    continue
                for q in polygons_of(p):
                    out.append(orient(q, 1.0))
                continue
        out.append(orient(p, 1.0))
    return out


def color_regions(doc, frame, step_mm=0.1, tolerance=0.02, min_area=0.02,
                  progress=None):
    """
    {color: [Polygon, ...]} in mm, colors tiling the plane without overlaps.
    `progress(fraction)` may raise Cancelled.
    """
    def stage(lo, hi):
        if not progress:
            return None
        return lambda f: progress(lo + (hi - lo) * f)

    ops = op_geometries(doc, frame, step_mm, stage(0.0, 0.5))
    vis = visible_parts(ops, stage(0.5, 0.85))
    by_color = {}
    for color, g in vis:
        by_color.setdefault(color, []).append(g)
    out = {}
    colors = list(by_color)
    for k, color in enumerate(colors):
        if progress:
            progress(0.85 + 0.15 * k / max(len(colors), 1))
        merged = shapely.union_all(by_color[color], grid_size=GRID)
        polys = clean(merged, tolerance, min_area)
        if polys:
            out[color] = polys
    return out


def total_area(polys):
    return sum(p.area for p in polys)


def absorb_thin(regions, width, min_area=0.0):
    """
    Details thinner than `width` mm cannot be printed (think of a 0.1 mm white
    line with a 0.4 mm nozzle). Each color is opened (shrunk then grown back);
    what the opening removes goes to the neighboring color that shares the
    longest border with it, so the colors keep tiling without gaps. Thin
    pieces that touch no other color stay where they are.
    """
    if not width or width <= 0 or len(regions) < 2:
        return regions
    r = width / 2.0
    kept, thin = {}, []
    for c, polys in regions.items():
        g = shapely.union_all(polys, grid_size=GRID)
        opened = g.buffer(-r, join_style=2, mitre_limit=10).buffer(r, join_style=2, mitre_limit=10)
        opened = opened.intersection(g, grid_size=GRID)
        kept[c] = opened
        rest = g.difference(opened, grid_size=GRID)
        thin.extend((c, p) for p in polygons_of(rest) if p.area > 1e-9)
    if not thin:
        return regions
    eps = max(width / 50.0, 1e-4)
    grown = {c: g.buffer(eps) for c, g in kept.items()}
    extra = {c: [] for c in regions}
    for c, piece in thin:
        best, best_len = c, 0.0
        edge = piece.exterior
        for c2, g2 in grown.items():
            if c2 == c or not g2.intersects(piece):
                continue
            shared = edge.intersection(g2).length
            if shared > best_len:
                best, best_len = c2, shared
        extra[best].append(piece)
    out = {}
    for c in regions:
        g = shapely.union_all([kept[c]] + extra[c], grid_size=GRID) if extra[c] else kept[c]
        polys = [orient(p, 1.0) for p in polygons_of(g) if p.area > max(min_area, 1e-9)]
        if polys:
            out[c] = polys
    return out


def bounds_of(regions):
    """(x0, y0, x1, y1) of every polygon in {color: [Polygon]}."""
    b = [p.bounds for ps in regions.values() for p in ps]
    if not b:
        return None
    return (min(x[0] for x in b), min(x[1] for x in b),
            max(x[2] for x in b), max(x[3] for x in b))


def looks_like_background(polys, full_bounds, share):
    """True when a color spans the whole drawing and covers a big share of it."""
    if not polys or not full_bounds:
        return False
    x0, y0, x1, y1 = bounds_of({"c": polys})
    fx0, fy0, fx1, fy1 = full_bounds
    w, h = fx1 - fx0, fy1 - fy0
    tol = 0.01 * max(w, h)
    spans = (x0 - fx0 <= tol and fx1 - x1 <= tol and y0 - fy0 <= tol
             and fy1 - y1 <= tol)
    return spans and share >= 0.25


# ----------------------------------------------------------------------------
# base plate
# ----------------------------------------------------------------------------
def base_plate(polys, margin, shape="outline", corner=2.0):
    """
    A solid plate under the design.

    shape "outline":   the silhouette of the design grown by `margin` mm,
                       inner holes filled;
    shape "rectangle": the bounding box grown by `margin`, corners rounded by
                       `corner` mm.
    """
    if not polys:
        return []
    union = shapely.union_all(polys, grid_size=GRID)
    if shape == "rectangle":
        x0, y0, x1, y1 = union.bounds
        rect = box(x0 - margin, y0 - margin, x1 + margin, y1 + margin)
        r = max(0.0, min(corner, (x1 - x0) / 2 + margin - 0.01,
                         (y1 - y0) / 2 + margin - 0.01))
        if r > 0:
            rect = rect.buffer(-r, join_style=2).buffer(r, join_style=1,
                                                        quad_segs=16)
        return [orient(p, 1.0) for p in polygons_of(rect)]
    grown = union.buffer(margin, join_style=1, quad_segs=16) if margin > 0 else union
    solid = [Polygon(p.exterior) for p in polygons_of(grown)]
    merged = shapely.union_all(solid, grid_size=GRID)
    return [orient(p, 1.0) for p in polygons_of(merged) if p.area > 1e-6]


# ----------------------------------------------------------------------------
# preview
# ----------------------------------------------------------------------------
def _ring_d(coords):
    pts = np.asarray(coords)[:-1]
    if len(pts) < 3:
        return ""
    body = " ".join(f"{x:.2f},{-y:.2f}" for x, y in pts)
    return f"M{body}Z"


def polygons_to_path_d(polys, tolerance=0.05):
    parts = []
    for p in polys:
        q = p.simplify(tolerance, preserve_topology=True) if tolerance else p
        for poly in polygons_of(q):
            parts.append(_ring_d(poly.exterior.coords))
            parts.extend(_ring_d(r.coords) for r in poly.interiors)
    return "".join(parts)


def preview_svg(layers, pad=2.0):
    """
    Small SVG drawing of the result. `layers` is a list of
    (key, color, polygons) drawn in order; each path carries data-key so the
    page can highlight it.
    """
    allp = [p for _, _, ps in layers for p in ps]
    if not allp:
        return ""
    x0, y0, x1, y1 = bounds_of({"all": allp})
    w, h = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
    vb = f"{x0 - pad:.2f} {-(y1 + pad):.2f} {w:.2f} {h:.2f}"
    tol = max(w, h) / 1500.0
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
           f'preserveAspectRatio="xMidYMid meet">']
    for key, color, polys in layers:
        d = polygons_to_path_d(polys, tol)
        if d:
            out.append(f'<path data-key="{key}" fill="{color}" fill-rule="evenodd" '
                       f'stroke="rgba(128,128,128,.6)" stroke-width="0.75" '
                       f'vector-effect="non-scaling-stroke" d="{d}"/>')
    out.append("</svg>")
    return "".join(out)
