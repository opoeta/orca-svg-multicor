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


def extrude(polys, height, z0=0.0):
    """
    Extrudes Polygons (exterior CCW, holes CW) between z0 and z0 + height.
    Returns (vertices Nx3 float64, faces Mx3 int64), outward normals.
    """
    V, F = [], []
    base = 0
    for poly in polys:
        pts, tris = _triangulate(poly)
        if pts is None or len(tris) == 0:
            continue
        n = len(pts)
        V.append(np.column_stack([pts, np.full(n, z0)]))
        V.append(np.column_stack([pts, np.full(n, z0 + height)]))
        F.append(tris[:, ::-1] + base)          # bottom cap, normal -Z
        F.append(tris + base + n)               # top cap, normal +Z

        offset = 0
        for ring in [poly.exterior] + list(poly.interiors):
            m = len(ring.coords) - 1
            if m < 3:
                continue
            idx = np.arange(m)
            nxt = (idx + 1) % m
            a0 = base + offset + idx
            b0 = base + offset + nxt
            a1, b1 = a0 + n, b0 + n
            F.append(np.column_stack([a0, b0, b1]))
            F.append(np.column_stack([a0, b1, a1]))
            offset += m
        base += 2 * n

    if not V:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

    V = np.concatenate(V)
    F = np.concatenate(F).astype(np.int64)

    # weld coincident vertices (touching rings share points)
    key = np.round(V, 6)
    _, first, inverse = np.unique(key, axis=0, return_index=True,
                                  return_inverse=True)
    V2 = V[first]
    F2 = inverse.reshape(-1)[F]
    ok = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
    return V2, F2[ok]


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
