# -*- coding: utf-8 -*-
"""
High level pipeline, independent of OrcaSlicer (tests and the dev server use
it directly):

    analyze(svg, options)                      -> colors, preview, warnings
    generate(svg, out_dir, options, choices)   -> new 3MF (+ STL per color)
    apply_to_project(svg, project, object_id, out, options, choices)

`choices` is what the user decided per color:
    {"#rrggbb": {"name": str, "filament": int, "enabled": bool}}

Messages go through a Reporter as (i18n key, params), so the caller decides
the language.
"""

import math
import os
import threading

from . import colors as C
from . import geometry as G
from . import mesh as M
from .errors import Cancelled, EngineError, ProjectError, SvgError
from .geometry import Frame
from .i18n import Translator
from .options import Options, _i
from .faces import default_face, place, planar_faces, to_object
from .project3mf import Project
from .svgread import PX_TO_MM, read_svg
from .threemf import Part, write_3mf

__all__ = ["Options", "Reporter", "analyze", "generate", "apply_to_project",
           "Cancelled", "SvgError", "ProjectError", "EngineError"]


class Reporter:
    """Default reporter: collects messages, never cancels."""

    def __init__(self):
        self.messages = []

    def progress(self, fraction, key=None, **params):
        pass

    def log(self, key, **params):
        self.messages.append(("info", key, params))

    def warn(self, key, **params):
        self.messages.append(("warn", key, params))


# ----------------------------------------------------------------------------
# cache: analyzing and then generating the same file must not redo the work
# ----------------------------------------------------------------------------
_cache_lock = threading.Lock()
_doc_cache = {}
_region_cache = {}
_CACHE_MAX = 4


def _file_key(path):
    st = os.stat(path)
    return (os.path.abspath(path), st.st_mtime_ns, st.st_size)


def _remember(store, key, value):
    with _cache_lock:
        store[key] = value
        while len(store) > _CACHE_MAX:
            store.pop(next(iter(store)))


def load_document(path, include_strokes=True):
    if not path or not os.path.isfile(path):
        raise EngineError("error.no_svg")
    key = (_file_key(path), bool(include_strokes))
    with _cache_lock:
        doc = _doc_cache.get(key)
    if doc is None:
        doc = read_svg(path, include_strokes=include_strokes)
        doc.cache_key = key
        _remember(_doc_cache, key, doc)
    return doc


def scale_for(doc, opts):
    """mm per SVG pixel for the chosen size."""
    w, h = doc.size_px
    if opts.size_mode == "original":
        return PX_TO_MM
    if opts.size_mode == "height":
        return opts.size_mm / h
    return opts.size_mm / w


def process(doc, scale, opts, rep=None):
    """
    Runs the geometry for `doc` at `scale` and merges/reduces the colors.
    Returns (regions, mapping, raw_count) with regions in mm centered on 0.
    """
    rep = rep or Reporter()
    key = (getattr(doc, "cache_key", None) or ("doc", id(doc)), round(scale, 9),
           opts.include_strokes, opts.step_mm, opts.precision_mm, opts.min_area_mm2)
    with _cache_lock:
        cached = _region_cache.get(key)
    if cached is None:
        frame = Frame.for_bbox(doc.bbox, scale)
        rep.progress(0.02, "progress.reading")

        def geo_progress(f):
            rep.progress(0.05 + 0.75 * f, "progress.geometry")

        regions = G.color_regions(doc, frame, step_mm=opts.step_mm,
                                  tolerance=opts.precision_mm,
                                  min_area=opts.min_area_mm2,
                                  progress=geo_progress)
        _remember(_region_cache, key, regions)
        cached = regions
    regions = dict(cached)
    if not regions:
        raise EngineError("error.no_regions")
    raw = len(regions)
    rep.progress(0.82, "progress.colors")
    regions, map1 = C.merge_similar(regions, opts.merge_tolerance)
    regions, map2 = C.reduce_colors(regions, opts.max_colors)
    mapping = C.chain_mappings(map1, map2)
    if opts.min_detail_mm > 0:
        rep.progress(0.84, "progress.details")
        regions = G.absorb_thin(regions, opts.min_detail_mm, opts.min_area_mm2)
        if not regions:
            raise EngineError("error.no_regions")
    return regions, mapping, raw


def ordered(regions):
    """Colors by decreasing area: the dominant color usually is the base."""
    return sorted(regions, key=lambda c: -G.total_area(regions[c]))


def default_name(tr, index, color):
    return f"{index}-{tr.color_name(C.color_name_key(color))}"


def _default_filaments(order, filaments):
    """Suggested filament per color: closest known color, else 1, 2, 3..."""
    suggestion = C.match_filaments(order, filaments or [])
    count = len(filaments or [])
    out = {}
    for i, c in enumerate(order, start=1):
        if c in suggestion:
            out[c] = suggestion[c]
        else:
            n = ((i - 1) % count) + 1 if count else i
            out[c] = (n, None)
    return out


def analyze(svg_path, opts, filaments=None, tr=None, rep=None):
    """Everything the page needs to show the colors and the preview."""
    tr = tr or Translator()
    rep = rep or Reporter()
    doc = load_document(svg_path, opts.include_strokes)
    scale = scale_for(doc, opts)
    regions, mapping, raw = process(doc, scale, opts, rep)
    order = ordered(regions)
    areas = {c: G.total_area(regions[c]) for c in order}
    total = sum(areas.values()) or 1.0
    bounds = G.bounds_of(regions)
    fils = _default_filaments(order, filaments)

    colors_out = []
    for i, c in enumerate(order, start=1):
        share = areas[c] / total
        n, de = fils[c]
        colors_out.append({
            "color": c,
            "name": default_name(tr, i, c),
            "area_pct": round(100.0 * share, 2),
            "area_mm2": round(areas[c], 2),
            "shapes": len(regions[c]),
            "merged": [x for x in mapping.get(c, [c]) if x != c],
            "filament": n,
            "delta_e": de,
            "background": G.looks_like_background(regions[c], bounds, share),
        })

    layers = [(c, c, regions[c]) for c in reversed(order)]
    base = []
    if opts.base_thickness_mm > 0:
        base = G.base_plate([p for c in order for p in regions[c]],
                            opts.base_margin_mm, opts.base_shape, opts.base_corner_mm)
        layers = [("base", "#8a8f94", base)] + layers
    allb = G.bounds_of({"x": base or [p for c in order for p in regions[c]]})
    size = (allb[2] - allb[0], allb[3] - allb[1]) if allb else (0.0, 0.0)
    rep.progress(1.0, "progress.done")
    return {
        "svg": os.path.abspath(svg_path),
        "colors": colors_out,
        "raw_count": raw,
        "size_mm": [round(size[0], 2), round(size[1], 2)],
        "design_mm": [round(bounds[2] - bounds[0], 2), round(bounds[3] - bounds[1], 2)] if bounds else [0, 0],
        "original_mm": [round(x, 2) for x in doc.size_mm],
        "box_mm": [round(doc.size_px[0] * scale, 3), round(doc.size_px[1] * scale, 3)],
        "physical": doc.physical,
        "preview": G.preview_svg(layers),
        "warnings": [(k, p) for k, p in doc.warnings],
    }


# ----------------------------------------------------------------------------
# parts
# ----------------------------------------------------------------------------
def _choice(choices, color, index, tr, fils):
    ch = (choices or {}).get(color) or {}
    name = str(ch.get("name") or "").strip() or default_name(tr, index, color)
    fil = _i(ch.get("filament"), fils[color][0], 1, 64)
    enabled = ch.get("enabled", True) is not False
    return name, fil, enabled


def build_parts(regions, opts, choices, tr, rep, z0=0.0, dx=0.0, dy=0.0,
                filaments=None, with_base=False, transform=None):
    """
    Extrudes every enabled color (and the base plate) into Parts.
    `transform` maps the extruded vertices (N x 3) into the object, when the
    parts go on a face of an existing object.
    """
    order = ordered(regions)
    fils = _default_filaments(order, filaments)
    known = set((choices or {}).keys())
    if choices and not (known & set(order)):
        raise EngineError("error.stale_colors")

    selected = []
    for i, c in enumerate(order, start=1):
        name, fil, enabled = _choice(choices, c, i, tr, fils)
        if enabled:
            selected.append((i, c, name, fil))
    if not selected:
        raise EngineError("error.nothing_selected")

    parts = []
    color_z = z0
    if with_base and opts.base_thickness_mm > 0:
        polys = [p for _, c, _, _ in selected for p in regions[c]]
        base = G.base_plate(polys, opts.base_margin_mm, opts.base_shape,
                            opts.base_corner_mm)
        V, F = M.extrude(base, opts.base_thickness_mm, z0)
        if len(F):
            V[:, 0] += dx
            V[:, 1] += dy
            parts.append(Part(tr("part.base"), V, F, "#8a8f94", opts.base_filament))
        color_z = z0 + opts.base_thickness_mm

    total = len(selected)
    for k, (_index, c, name, fil) in enumerate(selected):
        rep.progress(0.85 + 0.1 * k / max(total, 1), "progress.mesh", name=name)
        V, F = M.extrude(regions[c], opts.thickness_mm, color_z)
        if not len(F):
            rep.warn("warn.empty_part", name=name)
            continue
        V[:, 0] += dx
        V[:, 1] += dy
        if transform is not None:
            V = transform(V)
        parts.append(Part(name, V, F, c, fil))
    if not parts:
        raise EngineError("error.nothing_selected")
    return parts


def report(parts):
    out = []
    for p in parts:
        out.append({"name": p.name, "color": p.color, "filament": p.extruder,
                    "faces": int(len(p.F)),
                    "volume_mm3": round(abs(M.signed_volume(p.V, p.F)), 2),
                    "watertight": M.is_watertight(p.F)})
    return out


def _safe_filename(name, fallback="part"):
    bad = '<>:"/\\|?*' + "".join(chr(i) for i in range(32))
    clean = "".join("-" if ch in bad else ch for ch in str(name)).strip(" .")
    while "--" in clean:
        clean = clean.replace("--", "-")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT")
                                               for i in range(1, 10)}
    if not clean or clean.split(".")[0].upper() in reserved:
        clean = fallback
    return clean[:80]


def generate(svg_path, out_dir, opts, choices=None, filaments=None, tr=None, rep=None):
    """Writes <svg name>_multicolor.3mf in out_dir. Returns (path, report)."""
    tr = tr or Translator()
    rep = rep or Reporter()
    doc = load_document(svg_path, opts.include_strokes)
    scale = scale_for(doc, opts)
    regions, _mapping, _raw = process(doc, scale, opts, rep)
    parts = build_parts(regions, opts, choices, tr, rep, filaments=filaments,
                        with_base=True)

    os.makedirs(out_dir, exist_ok=True)
    stem = _safe_filename(os.path.splitext(os.path.basename(svg_path))[0], "design")
    dest = os.path.join(out_dir, stem + "_multicolor.3mf")
    rep.progress(0.96, "progress.writing")
    write_3mf(dest, parts, stem, opts.output_format)
    if opts.export_stl:
        for k, p in enumerate(parts, start=1):
            M.write_stl(os.path.join(out_dir, f"{stem}_{k:02d}_{_safe_filename(p.name)}.stl"),
                        p.V, p.F)
    rep.progress(1.0, "progress.done")
    return dest, report(parts)


def list_objects(project_path):
    """{"objects": [...], "filaments": [...]} of a saved project."""
    if not project_path or not os.path.isfile(project_path):
        raise EngineError("error.no_project")
    prj = Project(project_path)
    return {"objects": [o.as_dict() for o in prj.objects()], "filaments": prj.filaments()}


def match_plate_objects(plate_items, file_objects):
    """
    For each object on the plate, the id of the same object in the saved
    project, or None. A saved project lists its objects in the plate's order,
    so the position decides; the name confirms it (and rescues the match when
    the order differs). Objects not saved yet get None.
    """
    def norm(s):
        return str(s or "").strip().lower()

    used, out = set(), []
    for i, item in enumerate(plate_items):
        oid = None
        if i < len(file_objects) and norm(file_objects[i]["name"]) == norm(item.get("name")):
            oid = file_objects[i]["id"]
        else:
            same = [f["id"] for f in file_objects
                    if norm(f["name"]) == norm(item.get("name")) and f["id"] not in used]
            if len(same) == 1:
                oid = same[0]
        if oid is not None:
            used.add(oid)
        out.append(oid)
    if len(plate_items) == len(file_objects) and all(o is None for o in out):
        # names differ (renamed without saving the name?) but the counts agree
        out = [f["id"] for f in file_objects]
    return out


def object_faces(project, obj, mesh=None):
    V, F = mesh if mesh is not None else project.object_mesh(obj.id)
    return planar_faces(V, F, world=obj.item_matrix)


def face_name(tr, face):
    """"Front", or "Front (inner)" for the inside of the front wall."""
    name = tr("face." + face.direction)
    return tr("face.inner", dir=name) if face.inner else name


def list_faces(project_path, object_id):
    """{"faces": [...], "default": id} of an object of a saved project."""
    if not project_path or not os.path.isfile(project_path):
        raise EngineError("error.no_project")
    prj = Project(project_path)
    obj = prj.object(object_id)
    faces = object_faces(prj, obj)
    best = default_face(faces)
    return {"faces": [f.as_dict() for f in faces], "default": best.id if best else None}


def _rotated_size(w, h, degrees):
    a = math.radians(degrees)
    c, s_ = abs(math.cos(a)), abs(math.sin(a))
    return w * c + h * s_, w * s_ + h * c


def apply_to_project(svg_path, project_path, object_id, out_path, opts,
                     choices=None, filaments=None, tr=None, rep=None, face_id=None):
    """
    Adds the colors as new parts of object `object_id`, on one of its flat
    faces (`face_id` from list_faces(); the largest face looking up when
    omitted): inlaid into the object or raised from the face, along its
    normal, clipped to the face outline. The source project is never
    overwritten. Returns (path, report).
    """
    tr = tr or Translator()
    rep = rep or Reporter()
    if not project_path or not os.path.isfile(project_path):
        raise EngineError("error.no_project")
    if os.path.abspath(project_path) == os.path.abspath(out_path):
        raise EngineError("error.same_output")
    doc = load_document(svg_path, opts.include_strokes)
    project = Project(project_path)
    obj = project.object(object_id)
    V_obj, F_obj = project.object_mesh(obj.id)
    faces = object_faces(project, obj, (V_obj, F_obj))
    face = None
    if face_id not in (None, ""):
        face = next((f for f in faces if str(f.id) == str(face_id)), None)
    face = face or default_face(faces)
    if face is None:
        raise EngineError("error.no_faces")

    rotation = opts.rotation
    w_px, h_px = doc.size_px
    rw, rh = _rotated_size(w_px, h_px, rotation)
    face_w, face_h = face.size
    if opts.apply_width_mm > 0:
        scale = opts.apply_width_mm / w_px
    else:
        scale = opts.apply_fraction * min(face_w / rw, face_h / rh)
    rep.log("log.face", name=obj.name, face=face_name(tr, face),
            w=f"{face_w:.2f}", h=f"{face_h:.2f}")
    if rw * scale > face_w + 1e-6 or rh * scale > face_h + 1e-6:
        rep.warn("warn.exceeds_face", w=f"{face_w:.2f}", h=f"{face_h:.2f}")
    depth = float((V_obj @ face.normal).max() - (V_obj @ face.normal).min())
    if opts.fit == "inlay" and opts.thickness_mm > depth:
        rep.warn("warn.too_thick")

    regions, _mapping, _raw = process(doc, scale, opts, rep)
    placed = place(regions, face, rotation)
    if not placed:
        raise EngineError("error.nothing_on_face")
    z0 = -opts.thickness_mm if opts.fit == "inlay" else 0.0
    project_fils = project.filaments()
    parts = build_parts(placed, opts, choices, tr, rep, z0=z0,
                        filaments=filaments or project_fils, with_base=False,
                        transform=lambda V: to_object(V, face))
    if project_fils:
        beyond = [p.name for p in parts if p.extruder > len(project_fils)]
        if beyond:
            rep.warn("warn.project_filaments", n=len(project_fils), names=", ".join(beyond))
    rep.log("log.placed_face", w=f"{rw * scale:.2f}", h=f"{rh * scale:.2f}",
            t=f"{opts.thickness_mm:.2f}")
    rep.progress(0.96, "progress.writing")
    project.add_parts(obj.id, parts)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    project.save(out_path)
    rep.progress(1.0, "progress.done")
    return out_path, report(parts)


def project_output_path(project_path, out_dir):
    stem = os.path.splitext(os.path.basename(project_path))[0]
    dest = os.path.join(out_dir, stem + "_svg.3mf")
    if os.path.abspath(dest) == os.path.abspath(project_path):
        dest = os.path.join(out_dir, stem + "_svg_2.3mf")
    return dest
