# -*- coding: utf-8 -*-
"""
SVG reading: turns an SVG file into an ORDERED list of paint operations.

Order matters. SVG is painted like a canvas: what comes later covers what came
before. Keeping every fill and stroke in document order is what lets the
geometry stage cut away the parts of each color that are hidden under others.

Coordinates stay in SVG user units converted to CSS pixels by svgelements
(96 px per inch), Y pointing down. `PX_TO_MM` converts them to millimeters when
the file declares a physical size.
"""

import math
import re
import xml.etree.ElementTree as ET

import numpy as np
from svgelements import (SVG, Close, Color, Line, Move, Path, Shape, Text,
                         Use, SVGImage)

from .colors import average_color, normalize_hex
from .errors import SvgError

PX_TO_MM = 25.4 / 96.0

_JOIN = {"miter": 2, "miter-clip": 2, "arcs": 1, "round": 1, "bevel": 3}
_CAP = {"butt": 2, "round": 1, "square": 3}


class PaintOp:
    """One fill or one stroke of one SVG element, in paint order."""

    __slots__ = ("order", "color", "kind", "path", "rule", "width", "cap",
                 "join", "miter", "element_id")

    def __init__(self, order, color, kind, path, rule="nonzero", width=0.0,
                 cap=2, join=2, miter=4.0, element_id=None):
        self.order = order
        self.color = color
        self.kind = kind          # "fill" or "stroke"
        self.path = path          # svgelements Path, transform already applied
        self.rule = rule          # "nonzero" or "evenodd" (fills only)
        self.width = width        # stroke width in px (strokes only)
        self.cap = cap            # shapely cap_style
        self.join = join          # shapely join_style
        self.miter = miter
        self.element_id = element_id


class SvgDocument:
    """Result of reading an SVG: paint operations plus what the user must know."""

    def __init__(self, path, ops, bbox, warnings, physical):
        self.path = path
        self.ops = ops
        self.bbox = bbox          # (x0, y0, x1, y1) in px, strokes included
        self.warnings = warnings  # [(i18n_key, params), ...] without repeats
        self.physical = physical  # True when width/height carry real units

    @property
    def size_px(self):
        x0, y0, x1, y1 = self.bbox
        return (x1 - x0, y1 - y0)

    @property
    def size_mm(self):
        w, h = self.size_px
        return (w * PX_TO_MM, h * PX_TO_MM)

    def colors(self):
        seen = []
        for op in self.ops:
            if op.color not in seen:
                seen.append(op.color)
        return seen


# ----------------------------------------------------------------------------
# gradients and patterns: svgelements paints them black, which is never right
# ----------------------------------------------------------------------------
_RE_URL = re.compile(r"url\(\s*['\"]?#([^)'\"\s]+)['\"]?\s*\)\s*(.*)$", re.I)
_RE_STOP_STYLE = re.compile(r"stop-color\s*:\s*([^;]+)", re.I)
_RE_STOP_OPACITY = re.compile(r"stop-opacity\s*:\s*([^;]+)", re.I)


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _href(el):
    for k, v in el.attrib.items():
        if k.endswith("href") and v.startswith("#"):
            return v[1:]
    return None


def _parse_color(text):
    if text is None:
        return None
    text = text.strip()
    if not text or text.lower() in ("none", "transparent", "currentcolor",
                                    "inherit"):
        return None
    try:
        c = Color(text)
    except Exception:
        return None
    if c.value is None:
        return None
    return normalize_hex(c.hex)


def _gradient_table(raw):
    """
    {id: '#rrggbb'} for every gradient and pattern in the file. A gradient is
    represented by the average of its visible stops; gradients that only
    reference another gradient (href) inherit its stops.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {}
    stops, links, patterns = {}, {}, {}
    for el in root.iter():
        name = _local(el.tag)
        gid = el.get("id")
        if not gid:
            continue
        if name in ("linearGradient", "radialGradient"):
            cols = []
            for st in el:
                if _local(st.tag) != "stop":
                    continue
                style = st.get("style") or ""
                m = _RE_STOP_STYLE.search(style)
                col = _parse_color(m.group(1) if m else st.get("stop-color", "#000"))
                mo = _RE_STOP_OPACITY.search(style)
                op = mo.group(1) if mo else st.get("stop-opacity", "1")
                try:
                    op = float(op)
                except ValueError:
                    op = 1.0
                if col and op > 0:
                    cols.append(col)
            stops[gid] = cols
            ref = _href(el)
            if ref:
                links[gid] = ref
        elif name == "pattern":
            # the first solid fill found inside the pattern is a fair stand-in
            for sub in el.iter():
                col = _parse_color(sub.get("fill"))
                if col:
                    patterns[gid] = col
                    break
    table = {}
    for gid in stops:
        seen, cur = set(), gid
        while not stops.get(cur) and cur in links and cur not in seen:
            seen.add(cur)
            cur = links[cur]
        cols = stops.get(cur) or []
        if cols:
            table[gid] = average_color(cols)
    table.update(patterns)
    return table


def _paint_color(el, attr, gradients, warn):
    """
    Resolves the paint of `fill` or `stroke`: '#rrggbb', or None when there is
    nothing to paint. Gradients become the average of their stops.
    """
    raw = el.values.get(attr)
    if isinstance(raw, str) and "url(" in raw:
        m = _RE_URL.search(raw.strip())
        if m:
            ref, fallback = m.group(1), m.group(2).strip()
            if ref in gradients:
                warn("warn.gradient")
                return gradients[ref]
            col = _parse_color(fallback)
            if col:
                return col
        warn("warn.unknown_paint")
        return None
    paint = el.fill if attr == "fill" else el.stroke
    if paint is None or paint.value is None:
        return None
    try:
        if paint.alpha == 0:
            return None
    except Exception:
        pass
    return normalize_hex(paint.hex)


def _number(value, default=1.0):
    if value is None:
        return default
    try:
        s = str(value).strip()
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        return float(s)
    except ValueError:
        return default


def read_svg(path, include_strokes=True):
    """
    Reads the SVG at `path` and returns an SvgDocument.

    Hidden things are skipped (display:none, visibility:hidden, opacity 0,
    fully transparent paints). Things that cannot be turned into geometry
    (text, embedded images) produce warnings instead of silent losses.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if not raw.strip():
        raise SvgError("error.svg_empty")
    try:
        svg = SVG.parse(path, reify=True)
    except Exception as e:  # svgelements raises many kinds of errors
        raise SvgError("error.svg_parse", detail=str(e)[:200]) from e

    gradients = _gradient_table(raw)
    warnings, seen = [], set()

    def warn(key, **params):
        if key not in seen:
            seen.add(key)
            warnings.append((key, params))

    if re.search(rb"clip-path\s*[=:]|<clipPath\b|<mask\b", raw):
        warn("warn.clip_mask")
    if re.search(rb"stroke-dasharray\s*[=:]\s*['\"]?\s*[0-9.]", raw) and include_strokes:
        warn("warn.dashes")

    ops = []
    order = 0
    for el in svg.elements():
        if isinstance(el, Text):
            if (el.text or "").strip():
                warn("warn.text")
            continue
        if isinstance(el, SVGImage):
            warn("warn.image")
            continue
        if not isinstance(el, Shape) or isinstance(el, Use):
            continue
        vals = el.values
        if str(vals.get("visibility", "")).lower() in ("hidden", "collapse"):
            continue
        if str(vals.get("display", "")).lower() == "none":
            continue
        opacity = _number(vals.get("opacity"), 1.0)
        if opacity <= 0:
            continue
        if opacity < 1:
            warn("warn.transparency")

        try:
            path_el = abs(Path(el))   # bakes the transform into the points
        except Exception:
            continue
        if len(path_el) == 0:
            continue

        fill = _paint_color(el, "fill", gradients, warn)
        fill_op = _number(vals.get("fill-opacity"), 1.0)
        if fill and fill_op > 0:
            if fill_op < 1:
                warn("warn.transparency")
            rule = str(vals.get("fill-rule", "nonzero")).strip().lower()
            ops.append(PaintOp(order, fill, "fill", path_el,
                               rule="evenodd" if rule == "evenodd" else "nonzero",
                               element_id=el.id))
            order += 1

        if not include_strokes:
            continue
        stroke = _paint_color(el, "stroke", gradients, warn)
        stroke_op = _number(vals.get("stroke-opacity"), 1.0)
        if stroke and stroke_op > 0:
            width = float(getattr(el, "implicit_stroke_width", None)
                          or el.stroke_width or 0.0)
            if width > 0:
                if stroke_op < 1:
                    warn("warn.transparency")
                ops.append(PaintOp(
                    order, stroke, "stroke", path_el, width=width,
                    cap=_CAP.get(str(vals.get("stroke-linecap", "butt")).lower(), 2),
                    join=_JOIN.get(str(vals.get("stroke-linejoin", "miter")).lower(), 2),
                    miter=max(1.0, _number(vals.get("stroke-miterlimit"), 4.0)),
                    element_id=el.id))
                order += 1

    if not ops:
        raise SvgError("error.svg_no_shapes")

    bbox = _bbox(ops)
    if bbox is None or bbox[2] - bbox[0] <= 0 or bbox[3] - bbox[1] <= 0:
        raise SvgError("error.svg_no_area")
    physical = _has_physical_size(raw)
    return SvgDocument(path, ops, bbox, warnings, physical)


def _bbox(ops):
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    for op in ops:
        try:
            b = op.path.bbox()
        except Exception:
            b = None
        if not b:
            continue
        pad = op.width / 2.0 if op.kind == "stroke" else 0.0
        x0 = min(x0, b[0] - pad)
        y0 = min(y0, b[1] - pad)
        x1 = max(x1, b[2] + pad)
        y1 = max(y1, b[3] + pad)
    if x0 is math.inf:
        return None
    return (x0, y0, x1, y1)


_RE_ROOT = re.compile(rb"<svg\b[^>]*>", re.S)
_RE_UNIT = re.compile(rb"\b(width|height)\s*=\s*['\"]\s*[0-9.]+\s*(mm|cm|in|pt|pc)\s*['\"]")


def _has_physical_size(raw):
    m = _RE_ROOT.search(raw)
    return bool(m and _RE_UNIT.search(m.group(0)))


# ----------------------------------------------------------------------------
# flattening curves into point lists
# ----------------------------------------------------------------------------
def flatten(path, step):
    """
    Splits `path` into subpaths and samples each one.

    Returns [(points Nx2 float array, closed bool), ...]. `step` is the maximum
    chord length in px. The starting point of every subpath is kept: an open
    path such as "M0,0 L10,0 L10,10" is a filled triangle in SVG, and dropping
    its first point used to turn it into nothing.
    """
    out = []
    for sub in path.as_subpaths():
        pts = []
        closed = False
        for seg in sub:
            if isinstance(seg, Move):
                if seg.end is not None:
                    pts.append((seg.end.x, seg.end.y))
            elif isinstance(seg, Close):
                closed = True
                if seg.end is not None:
                    pts.append((seg.end.x, seg.end.y))
            elif isinstance(seg, Line):
                pts.append((seg.end.x, seg.end.y))
            else:
                try:
                    length = seg.length(error=1e-3)
                except Exception:
                    length = 0.0
                n = int(math.ceil(length / step)) if length and step > 0 else 8
                n = max(2, min(n, 4000))
                ts = np.linspace(0.0, 1.0, n + 1)[1:]
                try:
                    arr = np.asarray(seg.npoint(ts), dtype=float)
                    pts.extend(map(tuple, arr))
                except Exception:
                    for t in ts:
                        p = seg.point(t)
                        pts.append((p.x, p.y))
        if len(pts) < 2:
            continue
        a = np.asarray(pts, dtype=float)
        # drop consecutive duplicates
        keep = np.ones(len(a), dtype=bool)
        keep[1:] = np.any(np.abs(np.diff(a, axis=0)) > 1e-9, axis=1)
        a = a[keep]
        if len(a) >= 2:
            out.append((a, closed))
    return out
