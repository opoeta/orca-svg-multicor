# -*- coding: utf-8 -*-
"""
Flat surfaces of a mesh, where a design can be applied.

Coplanar triangles are grouped (same normal, same distance from the origin),
each group is flattened into its own 2D frame and split into connected
regions: the floor of a tray and the ring of its rim are both "up" faces, but
two different surfaces. Where two parts of an object touch (the walls of a
tray standing on its floor), the faces pressed against each other are inside
the object and are not offered.

A face that looks at another part of the object (the inside of a tray's
wall) is "inner", and is named after where it is (the front wall) rather
than where it looks (the back).

Every face carries a right-handed frame (u, v, n): n is the outward normal,
v points "up" as seen from outside the face (+Z for walls, +Y for the top and
the bottom) and u = v x n points right. Seen from outside, the design reads
correctly on every face; on the bottom that means mirrored when seen from
above, which is what printing it on the bed needs.
"""

import numpy as np
import shapely
from shapely.affinity import rotate as _rotate
from shapely.affinity import scale as _scale
from shapely.affinity import translate as _translate
from shapely.geometry.polygon import orient

from .geometry import GRID, polygons_of

MIN_FACE_AREA = 20.0          # mm2; smaller flat bits are not offered
MAX_FACES = 24


class Face:
    __slots__ = ("id", "normal", "u", "v", "origin", "polygon", "area", "size",
                 "direction", "height", "inner")

    def as_dict(self):
        x0, y0, x1, y1 = self.polygon.bounds
        return {"id": self.id, "dir": self.direction, "inner": self.inner,
                "w": round(self.size[0], 1), "h": round(self.size[1], 1),
                "area": round(self.area, 1), "z": round(self.height, 1),
                "outline": outline_path(self.polygon),
                "bounds": [round(x0, 2), round(-y1, 2), round(x1, 2), round(-y0, 2)]}


def _frame(n):
    n = n / np.linalg.norm(n)
    up = np.array([0.0, 1.0, 0.0]) if abs(n[2]) > 0.9 else np.array([0.0, 0.0, 1.0])
    u = np.cross(up, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v, n


def _direction(n_world):
    x, y, z = n_world
    if z > 0.9:
        return "top"
    if z < -0.9:
        return "bottom"
    if abs(z) > 0.5:
        return "slanted"
    if abs(x) >= abs(y):
        return "right" if x > 0 else "left"
    return "back" if y > 0 else "front"


def planar_faces(V, F, world=None, min_area=MIN_FACE_AREA, limit=MAX_FACES):
    """
    Flat faces of the mesh (V, F), largest first.

    world: optional 4x4 matrix from object to plate coordinates, only used to
           name the faces as the user sees them (top, front...) and to report
           their height on the plate.
    """
    V = np.asarray(V, dtype=float)
    F = np.asarray(F, dtype=np.int64)
    if len(F) == 0:
        return []
    t = V[F]
    cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    norm = np.linalg.norm(cross, axis=1)
    ok = norm > 1e-12
    t, cross, norm = t[ok], cross[ok], norm[ok]
    n = cross / norm[:, None]
    area = norm / 2.0
    d = np.einsum("ij,ij->i", n, t[:, 0])
    # a tolerance of ~1 degree and 0.05 mm keeps CAD faces together
    key = np.column_stack([np.round(n / 0.02).astype(np.int64),
                           np.round(d / 0.05).astype(np.int64)])
    keys, group = np.unique(key, axis=0, return_inverse=True)
    group = group.reshape(-1)
    totals = np.bincount(group, weights=area)
    index = {tuple(k): g for g, k in enumerate(keys.tolist())}
    rot = np.asarray(world, dtype=float)[:3, :3] if world is not None else np.eye(3)
    rays = _RayCaster(t)

    cache = {}

    def flat(g):
        """(normal, u, v, plane_d, region) of group g, the region in its own frame."""
        if g not in cache:
            idx = np.nonzero(group == g)[0]
            normal = np.average(n[idx], axis=0, weights=area[idx])
            u, v, normal = _frame(normal)
            pts = t[idx]
            plane_d = float(np.average(np.einsum("ij,j->i", pts[:, 0], normal), weights=area[idx]))
            uv = np.stack([pts @ u, pts @ v], axis=-1)                 # (m, 3, 2)
            rings = np.concatenate([uv, uv[:, :1]], axis=1)            # closed
            tris = shapely.polygons(rings)
            region = shapely.union_all(tris[shapely.area(tris) > 1e-12], grid_size=GRID)
            cache[g] = (normal, u, v, plane_d, region)
        return cache[g]

    faces = []
    for g in np.argsort(-totals):
        if totals[g] < min_area:
            break
        normal, u, v, plane_d, region = flat(g)
        # the same plane looking the other way: two parts pressed together
        other = index.get(tuple(-keys[g]))
        if other is not None:
            # the opposite frame is (-u, v): mirror it into this one
            behind = _scale(flat(other)[4], xfact=-1.0, yfact=1.0, origin=(0, 0))
            region = region.difference(behind, grid_size=GRID)
        for poly in polygons_of(region):
            if poly.area < min_area:
                continue
            x0, y0, x1, y1 = poly.bounds
            cu, cv = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            f = Face()
            f.normal, f.u, f.v = normal, u, v
            f.origin = cu * u + cv * v + plane_d * normal
            f.polygon = orient(_translate(poly, -cu, -cv), 1.0)
            f.area = float(poly.area)
            f.size = (x1 - x0, y1 - y0)
            inside = poly.representative_point()
            start = inside.x * u + inside.y * v + plane_d * normal
            f.inner = rays.blocked(start + 1e-3 * normal, normal)
            world_n = rot @ normal
            world_n /= np.linalg.norm(world_n)
            f.direction = _direction(-world_n if f.inner else world_n)
            if world is not None:
                f.height = float((np.asarray(world, dtype=float) @ np.append(f.origin, 1.0))[2])
            else:
                f.height = float(f.origin[2])
            faces.append(f)
    faces.sort(key=lambda f: -f.area)
    faces = faces[:limit]
    for i, f in enumerate(faces):
        f.id = i
    return faces


class _RayCaster:
    """Does a ray hit the mesh? (Moller-Trumbore on every triangle at once)."""

    def __init__(self, tris):
        self.a = tris[:, 0]
        self.e1 = tris[:, 1] - self.a
        self.e2 = tris[:, 2] - self.a

    def blocked(self, origin, direction, eps=1e-9):
        p = np.cross(direction, self.e2)
        det = np.einsum("ij,ij->i", self.e1, p)
        ok = np.abs(det) > eps
        inv = np.zeros_like(det)
        inv[ok] = 1.0 / det[ok]
        s = origin - self.a
        bu = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, self.e1)
        bv = (q @ direction) * inv
        dist = np.einsum("ij,ij->i", self.e2, q) * inv
        hit = ok & (bu >= 0) & (bv >= 0) & (bu + bv <= 1) & (dist > 1e-6)
        return bool(hit.any())


def default_face(faces):
    """The face a design most likely goes on: the largest one facing up."""
    ups = [f for f in faces if f.direction == "top" and not f.inner]
    return (ups or faces or [None])[0]


def outline_path(poly):
    """SVG path of a face in its own frame (y flipped for SVG)."""
    parts = []
    for p in polygons_of(poly):
        for ring in [p.exterior] + list(p.interiors):
            pts = np.asarray(ring.coords)[:-1]
            if len(pts) >= 3:
                parts.append("M" + " ".join(f"{x:.2f},{-y:.2f}" for x, y in pts) + "Z")
    return "".join(parts)


def place(regions, face, rotation=0.0, clip=True):
    """
    Rotates the design (mm, centered on 0) and clips it to the face outline.
    Returns {color: [Polygon]} in the face's 2D frame.
    """
    out = {}
    for color, polys in regions.items():
        placed = []
        for p in polys:
            q = _rotate(p, rotation, origin=(0, 0)) if rotation else p
            if clip:
                q = q.intersection(face.polygon, grid_size=GRID)
            placed.extend(orient(x, 1.0) for x in polygons_of(q) if x.area > 1e-6)
        if placed:
            out[color] = placed
    return out


def to_object(V, face):
    """Maps extruded vertices from the face frame (x, y, height) to the object."""
    basis = np.stack([face.u, face.v, face.normal])          # rows
    return face.origin + V @ basis
