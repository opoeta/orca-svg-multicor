# -*- coding: utf-8 -*-
"""Conversion options, validated. No heavy imports here."""


def _f(value, default, lo=None, hi=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _i(value, default, lo=None, hi=None):
    return int(round(_f(value, default, lo, hi)))


class Options:
    """All knobs. Build it from the page's JSON with from_dict()."""

    DEFAULTS = {
        "size_mode": "width",        # width | height | original
        "size_mm": 100.0,
        "thickness_mm": 0.6,
        "max_colors": 4,             # 0 = no limit
        "merge_tolerance": 0.0,      # Delta E; 0 = off
        "include_strokes": True,
        "precision_mm": 0.02,        # simplification tolerance
        "min_area_mm2": 0.02,        # specks smaller than this are dropped
        "min_detail_mm": 0.0,        # thinner details go to the neighbor color; 0 = off
        "base_thickness_mm": 0.0,    # 0 = no base plate
        "base_margin_mm": 2.0,
        "base_shape": "outline",     # outline | rectangle
        "base_corner_mm": 2.0,
        "base_filament": 1,
        "output_format": "orca",     # orca | standard
        "export_stl": False,
        "fit": "inlay",              # inlay | raised
        "apply_width_mm": 0.0,       # 0 = automatic
        "apply_fraction": 0.85,
        "rotation": 0.0,             # degrees, counterclockwise as seen on the face
    }

    def __init__(self, **kw):
        d = dict(self.DEFAULTS)
        d.update({k: v for k, v in kw.items() if k in self.DEFAULTS and v is not None})
        self.size_mode = d["size_mode"] if d["size_mode"] in ("width", "height", "original") else "width"
        self.size_mm = _f(d["size_mm"], 100.0, 1.0, 5000.0)
        self.thickness_mm = _f(d["thickness_mm"], 0.6, 0.01, 500.0)
        self.max_colors = _i(d["max_colors"], 4, 0, 64)
        self.merge_tolerance = _f(d["merge_tolerance"], 0.0, 0.0, 100.0)
        self.include_strokes = _bool(d["include_strokes"])
        self.precision_mm = _f(d["precision_mm"], 0.02, 0.0, 2.0)
        self.min_area_mm2 = _f(d["min_area_mm2"], 0.02, 0.0, 100.0)
        self.min_detail_mm = _f(d["min_detail_mm"], 0.0, 0.0, 10.0)
        self.base_thickness_mm = _f(d["base_thickness_mm"], 0.0, 0.0, 500.0)
        self.base_margin_mm = _f(d["base_margin_mm"], 2.0, 0.0, 500.0)
        self.base_shape = d["base_shape"] if d["base_shape"] in ("outline", "rectangle") else "outline"
        self.base_corner_mm = _f(d["base_corner_mm"], 2.0, 0.0, 500.0)
        self.base_filament = _i(d["base_filament"], 1, 1, 64)
        self.output_format = "standard" if d["output_format"] == "standard" else "orca"
        self.export_stl = _bool(d["export_stl"])
        self.fit = "raised" if d["fit"] == "raised" else "inlay"
        self.apply_width_mm = _f(d["apply_width_mm"], 0.0, 0.0, 5000.0)
        self.apply_fraction = _f(d["apply_fraction"], 0.85, 0.05, 1.0)
        self.rotation = _f(d["rotation"], 0.0, -3600.0, 3600.0) % 360.0

    @classmethod
    def from_dict(cls, d):
        return cls(**(d or {}))

    def as_dict(self):
        return {k: getattr(self, k) for k in self.DEFAULTS}

    @property
    def step_mm(self):
        """Curve sampling step, fine enough for the simplification to matter."""
        return max(0.03, min(0.25, self.precision_mm * 5 if self.precision_mm else 0.1))


def _bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)
