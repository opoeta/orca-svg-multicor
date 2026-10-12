# -*- coding: utf-8 -*-
"""
Polygons -> closed triangle meshes (extrusion), plus mesh checks.

No trimesh: triangulation is mapbox-earcut, extrusion and checks are here.
"""

import mapbox_earcut
import numpy as np


def _triangulate(poly):
    """Triangulates a Polygon with holes. Returns (points Nx2, triangles Mx3)."""
    rings, ends = [], []
    for ring in [poly.exterior] + list(poly.interiors):
        c = np.asarray(ring.coords[:-1], dtype=np.float64)   # no repeated 1st point
        if len(c) < 3:
            continue
        rings.append(c)
        ends.append(sum(len(r) for r in rings))
    if not rings:
        return None, None
    verts = np.concatenate(rings)
    tris = mapbox_earcut.triangulate_float64(verts, np.array(ends, dtype=np.uint32))
    return verts, np.asarray(tris, dtype=np.int64).reshape(-1, 3)


PINCH_GAP = 1e-5      # mm


def _unpinched(polys):
    """
    Polygons whose rings touch at a point (a hole touching another ring), or
    that touch another polygon of the part, are valid, but their extrusion is
    not manifold there: they shrink by PINCH_GAP, which parts what touches
    and nothing else.
    """
    import shapely
    from shapely.geometry.polygon import orient

    polys = list(polys)
    # pieces of the same part touching each other at a point: a slicer that
    # merges equal vertices would join their walls there
    touching = set()
    if len(polys) > 1:
        a, b = shapely.STRtree(polys).query(polys, predicate="touches")
        touching = set(a.tolist()) | set(b.tolist())
    out = []
    for k, poly in enumerate(polys):
        # rings that touch (at a vertex or in the middle of an edge) make the
        # outline a non-simple set of lines
        if k not in touching and (not poly.interiors or shapely.is_simple(poly.boundary)):
            out.append(poly)
            continue
        shrunk = poly.buffer(-PINCH_GAP, join_style=2, mitre_limit=2.0)
        parts = list(getattr(shrunk, "geoms", [shrunk]))
        out.extend(orient(q, 1.0) for q in parts if q.geom_type == "Polygon" and q.area > 0)
    return out


def extrude(polys, height, z0=0.0):
    """
    Extrudes Polygons (exterior CCW, holes CW) between z0 and z0 + height.
    Returns (vertices Nx3 float64, faces Mx3 int64), outward normals.
    Each polygon is its own closed shell: polygons of one color that touch at
    a single point would otherwise share a vertical edge, which makes the mesh
    non-manifold.
    """
    V, F = [], []
    base = 0
    for poly in _unpinched(polys):
        pts, tris = _triangulate(poly)
        if pts is None or len(tris) == 0:
            continue
        n = len(pts)
        Vp = np.concatenate([np.column_stack([pts, np.full(n, z0)]),
                             np.column_stack([pts, np.full(n, z0 + height)])])
        Fp = [tris[:, ::-1], tris + n]          # bottom cap (normal -Z), top cap (+Z)
        # earcut drops collinear and repeated points: the walls follow the
        # points the caps use, or their edges would not meet
        used = np.zeros(n, dtype=bool)
        used[np.unique(tris)] = True
        offset = 0
        for ring in [poly.exterior] + list(poly.interiors):
            m = len(ring.coords) - 1
            if m < 3:
                continue
            a0 = np.arange(offset, offset + m)
            offset += m
            a0 = a0[used[a0]]
            if len(a0) < 3:
                continue
            b0 = np.roll(a0, -1)
            a1, b1 = a0 + n, b0 + n
            Fp.append(np.column_stack([a0, b0, b1]))
            Fp.append(np.column_stack([a0, b1, a1]))
        Fp = np.concatenate(Fp).astype(np.int64)
        # weld coincident vertices inside this polygon (touching rings share points)
        _, first, inverse = np.unique(np.round(Vp, 6), axis=0, return_index=True,
                                      return_inverse=True)
        Fp = inverse.reshape(-1)[Fp]
        ok = (Fp[:, 0] != Fp[:, 1]) & (Fp[:, 1] != Fp[:, 2]) & (Fp[:, 0] != Fp[:, 2])
        V.append(Vp[first])
        F.append(Fp[ok] + base)
        base += len(first)

    if not V:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.concatenate(V), np.concatenate(F).astype(np.int64)


def is_watertight(F):
    """
    True when the mesh is closed and consistently oriented: every directed
    edge appears once and its reverse appears once.
    """
    if len(F) == 0:
        return False
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    _, count = np.unique(e, axis=0, return_counts=True)
    if np.any(count != 1):
        return False
    rev = e[:, ::-1]
    both = np.concatenate([e, rev])
    _, count2 = np.unique(both, axis=0, return_counts=True)
    return bool(np.all(count2 == 2))


def signed_volume(V, F):
    if len(F) == 0:
        return 0.0
    t = V[F]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def merge(meshes):
    """Concatenates [(V, F), ...] into one (V, F)."""
    Vs, Fs, off = [], [], 0
    for V, F in meshes:
        Vs.append(V)
        Fs.append(F + off)
        off += len(V)
    if not Vs:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.concatenate(Vs), np.concatenate(Fs)


def write_stl(path, V, F):
    """Binary STL."""
    t = V[F].astype(np.float32)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, norm, out=np.zeros_like(n), where=norm > 0).astype(np.float32)
    rec = np.zeros(len(F), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                  ("attr", "<u2")])
    rec["n"] = n
    rec["v"] = t
    with open(path, "wb") as f:
        f.write(b"orca-svg-multicor".ljust(80, b"\0"))
        f.write(np.uint32(len(F)).tobytes())
        f.write(rec.tobytes())
