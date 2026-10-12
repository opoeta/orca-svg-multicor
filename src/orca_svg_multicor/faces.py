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
v points "up" and u = v x n points right, as seen from outside the face.
"Up" is the one of the object's edges closest to up in OrcaSlicer's own view
of that face, for the object as it sits on the plate: +Y from the top, -Y
from the bottom (its bottom view has the front of the plate up), +Z for the
walls. What is left of the object's turn on the plate (under 45 degrees) is
the face's `view` angle, so the page shows the face as OrcaSlicer does, with
the design along the object's edges. Seen from outside, the design reads
correctly on every face; on the bottom that means mirrored when seen from
above, which is what printing it on the bed needs.
"""

import math

import numpy as np
import shapely
from shapely.affinity import affine_transform as _affine
from shapely.affinity import rotate as _rotate
from shapely.affinity import scale as _scale
from shapely.affinity import translate as _translate
from shapely.geometry.polygon import orient

from .geometry import GRID, polygons_of

MIN_FACE_AREA = 20.0          # mm2; smaller flat bits are not offered
MAX_FACES = 24
# Meshes exported from CAD often have vertices a few ten-thousandths of a
# millimetre apart where they should be one: the triangles of a face then
# touch only at points, and a rounded corner came off as a separate bit too
# small to offer (a lid with its corners cut). Closing the face by this much
# joins them and moves its outline by nothing a printer can see.
HEAL = 0.01                   # mm


class Face:
    __slots__ = ("id", "normal", "u", "v", "origin", "polygon", "area", "size",
                 "direction", "height", "inner", "view", "seen", "sides")

    def as_dict(self):
        x0, y0, x1, y1 = self.polygon.bounds
        d = {"id": self.id, "dir": self.direction, "inner": self.inner,
             "w": round(self.size[0], 1), "h": round(self.size[1], 1),
             "area": round(self.area, 1), "z": round(self.height, 1),
             "view": round(self.view, 2), "seen": self.seen, "sides": self.sides,
             "outline": outline_path(self.polygon),
             "bounds": [round(x0, 2), round(-y1, 2), round(x1, 2), round(-y0, 2)]}
        return d


def _frame(n):
    n = n / np.linalg.norm(n)
    up = np.array([0.0, 1.0, 0.0]) if abs(n[2]) > 0.9 else np.array([0.0, 0.0, 1.0])
    u = np.cross(up, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v, n


def _view_up(n_world):
    """Up in OrcaSlicer's standard view of a face looking along n_world (Camera::select_view)."""
    if n_world[2] > 0.9:
        return np.array([0.0, 1.0, 0.0])               # top view
    if n_world[2] < -0.9:
        return np.array([0.0, -1.0, 0.0])              # bottom view: the front of the plate up
    up = np.array([0.0, 0.0, 1.0]) - n_world * n_world[2]
    norm = np.linalg.norm(up)
    return up / norm if norm > 1e-9 else None


def _view_turn(rot, u, v):
    """
    (k, view): turning the frame (u, v) by k quarter turns counterclockwise
    puts its "up" on the object's edge closest to up as OrcaSlicer shows the
    face; `view` (degrees, -45..45) is what is left, counterclockwise on screen.
    rot: the object's 3x3 placement on the plate.
    """
    if np.linalg.det(rot) <= 0:            # a mirrored instance: keep the object's own frame
        return 0, 0.0
    u_w, v_w = rot @ u, rot @ v
    n_w = np.cross(u_w, v_w)
    norm = np.linalg.norm(n_w)
    if norm < 1e-12:
        return 0, 0.0
    n_w /= norm
    up = _view_up(n_w)
    if up is None:
        return 0, 0.0
    right = np.cross(up, n_w)
    v_w = v_w - n_w * float(v_w @ n_w)
    theta = round(math.degrees(math.atan2(-float(v_w @ right), float(v_w @ up))), 4)
    turns = math.floor(theta / 90.0 + 0.5)
    return (-turns) % 4, theta - 90.0 * turns


def _side(vec):
    """The side of the plate a direction points to: front, back, left, right, top, bottom."""
    i = int(np.argmax(np.abs(vec)))
    return (("left", "right"), ("front", "back"), ("bottom", "top"))[i][int(vec[i] > 0)]


def _screen(rot, normal):
    """
    (seen, sides): where OrcaSlicer's camera is to see the face (its standard
    view), and the side of the plate at the top, bottom, left and right of
    that view. The page shows the face turned that way, so these are its sides.
    """
    n_w = rot @ normal
    n_w = n_w / np.linalg.norm(n_w)
    up = _view_up(n_w)
    if up is None:
        return _side(n_w), None
    right = np.cross(up, n_w)
    return _side(n_w), {"up": _side(up), "down": _side(-up), "left": _side(-right), "right": _side(right)}


def silhouettes(V, F):
    """
    silhouette(face): the whole object (V, F) seen from outside the face, in
    the face's frame: its outline, tabs and notches show where the face is
    on the object. The triangles that look toward the camera are enough to
    cover it. Faces looking the same way share one.
    """
    tris = np.asarray(V, dtype=float)[np.asarray(F, dtype=np.int64)]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    cache = {}

    def silhouette(face):
        key = (tuple(np.round(face.normal, 4)), tuple(np.round(face.u, 4)))
        if key not in cache:
            front = normals @ face.normal > 1e-6
            t = tris[front]
            uv = np.stack([t @ face.u, t @ face.v], axis=-1)
            rings = np.concatenate([uv, uv[:, :1]], axis=1)
            polys = shapely.polygons(rings)
            polys = polys[shapely.area(polys) > 1e-6]
            shape = shapely.union_all(polys, grid_size=0.01) if len(polys) else shapely.Polygon()
            cache[key] = shape.simplify(0.05)
        x, y = float(face.origin @ face.u), float(face.origin @ face.v)
        return _translate(cache[key], -x, -y)

    return silhouette


def context_dict(shape):
    """The silhouette for the page: an SVG path and its bounds (y flipped), or {}."""
    if shape is None or shape.is_empty:
        return {}
    x0, y0, x1, y1 = shape.bounds
    return {"context": outline_path(shape),
            "context_bounds": [round(x0, 2), round(-y1, 2), round(x1, 2), round(-y0, 2)]}


# counterclockwise quarter turns of a frame: (cos, sin) of k * 90 degrees
_QUARTER = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _turn(face, k):
    """Turns the face's frame by k quarter turns; its outline follows, in the new frame."""
    if not k:
        return
    c, s_ = _QUARTER[k]
    u, v = face.u, face.v
    face.u, face.v = c * u + s_ * v, -s_ * u + c * v
    # a point x u + y v has (x c + y s, -x s + y c) in the turned frame
    face.polygon = orient(_affine(face.polygon, [c, s_, -s_, c, 0.0, 0.0]), 1.0)
    if k % 2:
        face.size = (face.size[1], face.size[0])


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
            region = shapely.set_precision(region.buffer(HEAL, join_style=2).buffer(-HEAL, join_style=2), GRID)
            cache[g] = (normal, u, v, plane_d, region)
        return cache[g]

    faces = []
    for g in np.argsort(-totals):
        if totals[g] < min_area:
            break
        # groups come largest first and a face is never larger than its
        # group: once `limit` faces are larger than this whole group, no
        # face left can make the list (an object with a hundred holes has
        # thousands of small flat groups)
        if len(faces) >= limit and totals[g] < sorted((f.area for f, _s in faces), reverse=True)[limit - 1]:
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
            faces.append((f, inside.x * u + inside.y * v + plane_d * normal))
    faces.sort(key=lambda fs: -fs[0].area)
    faces = faces[:limit]
    # what the list shows, for the faces it shows: casting a ray through the
    # whole mesh is the slow part
    for i, (f, start) in enumerate(faces):
        f.id = i
        f.inner = rays.blocked(start + 1e-3 * f.normal, f.normal)
        world_n = rot @ f.normal
        world_n /= np.linalg.norm(world_n)
        f.direction = _direction(-world_n if f.inner else world_n)
        if world is not None:
            f.height = float((np.asarray(world, dtype=float) @ np.append(f.origin, 1.0))[2])
        else:
            f.height = float(f.origin[2])
        k, f.view = _view_turn(rot, f.u, f.v)
        _turn(f, k)
        f.seen, f.sides = _screen(rot, f.normal)
    return [f for f, _start in faces]


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
    """
    The face a design most likely goes on: the one lying on the bed (the
    design is then in the first layers), else the largest one facing up.
    """
    downs = [f for f in faces if f.direction == "bottom" and not f.inner]
    if downs:
        low = min(f.height for f in downs)
        return next(f for f in downs if f.height <= low + 0.05)    # faces come largest first
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


def place(regions, face, rotation=0.0, clip=True, offset=(0.0, 0.0)):
    """
    Rotates the design (mm, centered on 0), moves its center to `offset` on
    the face and clips it to the face outline: it never leaves the object.
    Returns {color: [Polygon]} in the face's 2D frame.
    """
    dx, dy = offset
    out = {}
    for color, polys in regions.items():
        placed = []
        for p in polys:
            q = _rotate(p, rotation, origin=(0, 0)) if rotation else p
            if dx or dy:
                q = _translate(q, dx, dy)
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
