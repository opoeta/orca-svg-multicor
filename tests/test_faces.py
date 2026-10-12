"""Flat faces of objects, and applying a design on the one the user picks."""
import os
import zipfile

import numpy as np
import shapely
import pytest
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from conftest import EXAMPLES, cube
from orca_svg_multicor import engine as E
from orca_svg_multicor.faces import default_face, place, planar_faces, to_object
from orca_svg_multicor.mesh import extrude, is_watertight, signed_volume
from orca_svg_multicor.options import Options
from orca_svg_multicor.project3mf import Project
from orca_svg_multicor.threemf import Part, write_orca_project

BADGE = os.path.join(EXAMPLES, "badge.svg")


def tray():
    """A 40 x 30 x 10 mm tray: 2 mm floor, 2 mm walls, open on top."""
    ring = orient(Polygon(box(-20, -15, 20, 15).exterior, [box(-18, -13, 18, 13).exterior]), 1.0)
    walls = extrude([ring], 8.0, 2.0)
    floor = extrude([orient(box(-20, -15, 20, 15), 1.0)], 2.0, 0.0)
    return walls, floor


@pytest.fixture
def tray_project(tmp_path):
    (Vw, Fw), (Vf, Ff) = tray()
    p = tmp_path / "tray.3mf"
    write_orca_project(str(p), [Part("walls", Vw, Fw, "#ff00aa", 1), Part("floor", Vf, Ff, "#ff00aa", 1)],
                       "tray")
    return str(p)


def test_cube_has_six_named_faces():
    V, F = cube(20)
    faces = planar_faces(V, F)
    assert sorted(f.direction for f in faces) == ["back", "bottom", "front", "left", "right", "top"]
    assert all(f.size == pytest.approx((20, 20)) for f in faces)
    top = next(f for f in faces if f.direction == "top")
    assert top.height == pytest.approx(20)


def test_tray_floor_and_rim_are_different_faces(tray_project):
    listing = E.list_faces(tray_project, "3")
    tops = [f for f in listing["faces"] if f["dir"] == "top"]
    assert sorted(f["z"] for f in tops) == [2.0, 10.0]           # the floor and the rim
    default = next(f for f in listing["faces"] if f["id"] == listing["default"])
    assert default["dir"] == "bottom" and default["z"] == 0.0    # the one lying on the bed
    assert all(f["outline"].startswith("M") for f in listing["faces"])


def test_faces_between_parts_are_not_offered(tray_project):
    faces = E.list_faces(tray_project, "3")["faces"]
    floor = next(f for f in faces if f["dir"] == "top" and f["z"] == 2.0)
    assert (floor["w"], floor["h"]) == (36.0, 26.0)              # only the part inside the walls
    assert [f["z"] for f in faces if f["dir"] == "bottom"] == [0.0]  # not the walls' underside


def test_the_inside_of_a_wall_is_named_after_the_wall(tray_project):
    faces = E.list_faces(tray_project, "3")["faces"]
    fronts = sorted((f for f in faces if f["dir"] == "front"), key=lambda f: f["inner"])
    assert [f["inner"] for f in fronts] == [False, True]
    assert fronts[1]["w"] == 36.0                                # inside of the front wall
    assert not any(f["inner"] for f in faces if f["dir"] in ("top", "bottom"))


def test_apply_on_the_inside_of_a_wall(tray_project, tmp_path):
    faces = E.list_faces(tray_project, "3")["faces"]
    inner = next(f for f in faces if f["dir"] == "front" and f["inner"])
    out = str(tmp_path / "inner.3mf")
    E.apply_to_project(BADGE, tray_project, "3", out, Options(fit="raised", thickness_mm=1.0),
                       face_id=inner["id"])
    V, F = Project(out).object_mesh("3")
    new = V[F[-200:]].reshape(-1, 3)
    assert new[:, 1].min() == pytest.approx(-13, abs=1e-6)     # on the inner face, y = -13
    assert new[:, 1].max() == pytest.approx(-12, abs=1e-6)     # 1 mm into the cavity


def test_face_frames_are_right_handed_and_outward():
    V, F = cube(10)
    for f in planar_faces(V, F):
        assert np.dot(np.cross(f.u, f.v), f.normal) == pytest.approx(1)
        # the face's center sits on the cube's surface, the normal points away
        assert np.dot(f.origin - np.array([0, 0, 5]), f.normal) == pytest.approx(5)


def test_extruded_part_keeps_its_orientation_on_any_face():
    V, F = cube(10)
    square = {"#ff0000": [orient(box(-2, -2, 2, 2), 1.0)]}
    for f in planar_faces(V, F):
        Vp, Fp = extrude(place(square, f)["#ff0000"], 1.0, -1.0)
        Vp = to_object(Vp, f)
        assert is_watertight(Fp) and signed_volume(Vp, Fp) == pytest.approx(16)
        # inlaid: the part is inside the cube
        assert Vp.min() >= -5 - 1e-9 and Vp[:, :2].max() <= 5 + 1e-9


def test_place_rotates_and_clips_to_the_face():
    V, F = cube(10)
    top = next(f for f in planar_faces(V, F) if f.direction == "top")
    bar = {"#000000": [orient(box(-20, -1, 20, 1), 1.0)]}     # wider than the face
    placed = place(bar, top)["#000000"]
    assert sum(p.area for p in placed) == pytest.approx(20)   # clipped to 10 mm
    turned = place(bar, top, rotation=90)["#000000"]
    x0, y0, x1, y1 = turned[0].bounds
    assert (x1 - x0, y1 - y0) == pytest.approx((2, 10))


def test_apply_on_the_bottom_of_a_tray(tray_project, tmp_path):
    listing = E.list_faces(tray_project, "3")
    bottom = next(f for f in listing["faces"] if f["dir"] == "bottom")
    out = str(tmp_path / "bottom.3mf")
    E.apply_to_project(BADGE, tray_project, "3", out, Options(fit="inlay", thickness_mm=0.6),
                       face_id=bottom["id"])
    prj = Project(out)
    obj = prj.objects()[0]
    assert obj.size == pytest.approx((40, 30, 10))            # inlaid: the tray keeps its size
    V, F = prj.object_mesh("3")
    new = V[F[-200:]].reshape(-1, 3)                        # triangles of the added parts
    assert new[:, 2].min() == pytest.approx(0, abs=1e-6)
    assert new[:, 2].max() == pytest.approx(0.6, abs=1e-6)


def test_apply_raised_on_the_front(tray_project, tmp_path):
    listing = E.list_faces(tray_project, "3")
    front = next(f for f in listing["faces"] if f["dir"] == "front" and f["w"] > 39)
    out = str(tmp_path / "front.3mf")
    E.apply_to_project(BADGE, tray_project, "3", out,
                       Options(fit="raised", thickness_mm=1.0, rotation=90), face_id=front["id"])
    obj = Project(out).objects()[0]
    lo, hi = obj.bbox
    assert lo[1] == pytest.approx(-16, abs=1e-6)             # 1 mm out of the front wall
    assert hi[2] <= 10 + 1e-6 and lo[2] >= -1e-6


def _marker_at(face, x, y):
    """Where a small mark at (x, y) of the design lands on the object (its center)."""
    mark = {"#000000": [orient(box(x - 0.5, y - 0.5, x + 0.5, y + 0.5), 1.0)]}
    Vp, _ = extrude(place(mark, face)["#000000"], 0.5, -0.5)
    return to_object(Vp, face).mean(axis=0)


def test_bottom_reads_like_orcaslicers_bottom_view():
    """
    OrcaSlicer's bottom view looks up with the front of the plate up
    (Camera::select_view): the design's right is +X and its top is -Y there.
    """
    V, F = cube(10)
    bottom = next(f for f in planar_faces(V, F) if f.direction == "bottom")
    right, top = _marker_at(bottom, 3, 0), _marker_at(bottom, 0, 3)
    assert right[0] > 2 and abs(right[1]) < 1
    assert top[1] < -2 and abs(top[0]) < 1
    assert bottom.view == 0.0


def test_the_top_and_the_walls_read_like_orcaslicers_views():
    V, F = cube(10)
    faces = {f.direction: f for f in planar_faces(V, F)}
    right, top = _marker_at(faces["top"], 3, 0), _marker_at(faces["top"], 0, 3)
    assert right[0] > 2 and top[1] > 2                       # top view: +Y up
    right, top = _marker_at(faces["front"], 3, 0), _marker_at(faces["front"], 0, 3)
    assert right[0] > 2 and top[2] > 7                       # front view: +X right, +Z up


def _turned(degrees, axis="z"):
    a = np.radians(degrees)
    c, s_ = np.cos(a), np.sin(a)
    m = np.eye(4)
    if axis == "z":
        m[:3, :3] = [[c, -s_, 0], [s_, c, 0], [0, 0, 1]]
    else:                                                     # around Y: turned over
        m[:3, :3] = [[c, 0, s_], [0, 1, 0], [-s_, 0, c]]
    return m


@pytest.mark.parametrize("degrees, view", [(0, 0.0), (90, 0.0), (30, -30.0), (-20, 20.0), (200, -20.0)])
def test_the_design_follows_the_object_turned_on_the_plate(degrees, view):
    """
    Along the object's edges, up as close as it gets to OrcaSlicer's view; the
    rest is `view`. Turned counterclockwise seen from above is clockwise seen
    from below.
    """
    V, F = cube(10)
    world = _turned(degrees)
    faces = planar_faces(V, F, world=world)
    bottom = next(f for f in faces if f.direction == "bottom")
    top = next(f for f in faces if f.direction == "top")
    assert bottom.view == pytest.approx(view)
    assert top.view == pytest.approx(-view)
    # the design's up, on the plate, is OrcaSlicer's bottom-view up (-Y) turned by `view`
    up_world = world[:3, :3] @ bottom.v
    a = np.radians(view)
    right_view, up_view = np.array([1.0, 0, 0]), np.array([0, -1.0, 0])
    expected = -np.sin(a) * right_view + np.cos(a) * up_view
    assert up_world == pytest.approx(expected, abs=1e-9)
    # and along one of the object's own edges
    assert sorted(np.round(np.abs(bottom.v), 9)) == [0.0, 0.0, 1.0]


def test_a_quarter_turn_swaps_the_size_as_seen():
    V, F = extrude([orient(box(-10, -5, 10, 5), 1.0)], 4.0, 0.0)     # 20 x 10 mm
    top = next(f for f in planar_faces(V, F, world=_turned(90)) if f.direction == "top")
    assert top.size == pytest.approx((10.0, 20.0))                    # 10 wide, 20 tall on screen
    assert top.polygon.bounds == pytest.approx((-5.0, -10.0, 5.0, 10.0))


def test_half_turn_is_never_ambiguous():
    V, F = cube(10)
    views = {round(next(f for f in planar_faces(V, F, world=_turned(d)) if f.direction == "bottom").view, 6)
             for d in (45, 45 + 1e-9, 45 - 1e-9, 135, -45)}
    assert views == {-45.0}


def test_an_object_turned_over_reads_from_below():
    """Turned over on the plate (the object's top on the bed): its top is the bottom face."""
    V, F = cube(10)
    world = _turned(180, axis="y")
    bottom = next(f for f in planar_faces(V, F, world=world) if f.direction == "bottom")
    assert np.round(bottom.normal).tolist() == [0, 0, 1]             # the object's own top
    right = world[:3, :3] @ (_marker_at(bottom, 3, 0) - bottom.origin)
    top = world[:3, :3] @ (_marker_at(bottom, 0, 3) - bottom.origin)
    assert right[0] > 2 and top[1] < -2


def test_a_mirrored_object_keeps_its_own_frame():
    V, F = cube(10)
    mirror = np.diag([-1.0, 1.0, 1.0, 1.0])
    assert all(f.view == 0.0 for f in planar_faces(V, F, world=mirror))


def test_default_face_is_the_one_on_the_bed():
    V, F = cube(10)
    faces = planar_faces(V, F)
    assert default_face(faces).direction == "bottom"
    # nothing on the bed (only the sides and the top offered): the largest facing up
    assert default_face([f for f in faces if f.direction != "bottom"]).direction == "top"
    assert default_face([]) is None


def test_faces_follow_the_object_rotation_on_the_plate():
    V, F = cube(10)
    turn = np.eye(4)
    turn[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]         # 90 degrees around Z
    names = {tuple(np.round(f.normal).astype(int)): f.direction for f in planar_faces(V, F, world=turn)}
    assert names[(0, -1, 0)] == "right"                      # object's front now faces +X


def test_face_listing_survives_a_real_project_layout(tray_project):
    with zipfile.ZipFile(tray_project) as z:
        assert "3D/Objects/object_1.model" in z.namelist()
    assert len(E.list_faces(tray_project, "3")["faces"]) >= 8


def _with_layers(path, lh, h1):
    """The tray project with print settings, as OrcaSlicer saves them."""
    import json
    import shutil
    out = path.replace(".3mf", "_layers.3mf")
    shutil.copy(path, out)
    with zipfile.ZipFile(out, "a") as z:
        z.writestr("Metadata/project_settings.config",
                   json.dumps({"layer_height": str(lh), "initial_layer_print_height": str(h1)}))
    return out


def _new_z(path):
    V, F = Project(path).object_mesh("3")
    new = V[F[-200:]].reshape(-1, 3)
    return new[:, 2].min(), new[:, 2].max()


def test_the_project_layer_heights_are_read(tray_project):
    assert Project(tray_project).layer_heights() is None
    assert Project(_with_layers(tray_project, 0.12, 0.2)).layer_heights() == {"lh": 0.12, "h1": 0.2}


@pytest.mark.parametrize("first_layer, z", [("include", (0.0, 0.44)), ("above", (0.2, 0.56))])
def test_on_the_bed_the_first_layer_is_the_choice(tray_project, tmp_path, first_layer, z):
    """3 layers of 0.12 mm, first layer 0.2 mm, inlaid in the face lying on the bed."""
    prj = _with_layers(tray_project, 0.12, 0.2)
    bottom = next(f for f in E.list_faces(prj, "3")["faces"] if f["dir"] == "bottom")
    out = str(tmp_path / "base.3mf")
    E.apply_to_project(BADGE, prj, "3", out,
                       Options(thickness_mode="layers", thickness_layers=3, first_layer=first_layer),
                       face_id=bottom["id"])
    assert _new_z(out) == pytest.approx(z, abs=1e-6)


def test_layers_away_from_the_bed_are_whole_layers(tray_project, tmp_path):
    prj = _with_layers(tray_project, 0.12, 0.2)
    floor = next(f for f in E.list_faces(prj, "3")["faces"] if f["dir"] == "top" and f["z"] == 2.0)
    out = str(tmp_path / "floor.3mf")
    E.apply_to_project(BADGE, prj, "3", out, Options(thickness_mode="layers", thickness_layers=2,
                                                     first_layer="above"), face_id=floor["id"])
    assert _new_z(out) == pytest.approx((2.0 - 0.24, 2.0), abs=1e-6)   # "above" only on the bed


def test_the_design_moves_on_the_face_and_stays_inside(tray_project, tmp_path):
    floor = next(f for f in E.list_faces(tray_project, "3")["faces"] if f["dir"] == "top" and f["z"] == 2.0)
    n0 = len(Project(tray_project).object_mesh("3")[1])

    def placed(name, **kw):
        out = str(tmp_path / name)
        E.apply_to_project(BADGE, tray_project, "3", out, Options(apply_width_mm=10, **kw),
                           face_id=floor["id"])
        V, F = Project(out).object_mesh("3")
        return V[F[n0:]].reshape(-1, 3)

    center, moved = placed("center.3mf"), placed("moved.3mf", offset_x_mm=12, offset_y_mm=-10)
    assert moved[:, 0].min() - center[:, 0].min() == pytest.approx(12, abs=0.05)   # 12 mm right
    # asked for 10 mm down: it stops against the wall, never past it
    assert -13 - 1e-6 <= moved[:, 1].min() <= -12.9


def test_layer_plan():
    o = Options(thickness_mode="layers", thickness_layers=4)
    assert E.layer_plan(o, {"lh": 0.1, "h1": 0.3}, on_bed=True) == (0.6, 0.0)
    assert E.layer_plan(o, None) == (0.8, 0.0)                     # 0.2 mm when unknown
    assert E.layer_plan(Options(thickness_mode="layers", thickness_layers=4, layer_height_mm=0.08),
                        {"lh": 0.2, "h1": 0.2}) == (0.32, 0.0)     # the page's layer height wins
    assert E.layer_plan(Options(thickness_mm=0.6, first_layer="above"), {"lh": 0.2, "h1": 0.25},
                        on_bed=True) == (0.6, 0.25)


def test_a_crack_in_the_mesh_does_not_cut_a_corner_off():
    """
    A lid exported from CAD: its rounded corner is a fan of triangles whose
    base vertex is 0.0005 mm from the vertex of the rest of the face. The
    corner touched the face only at points and was dropped as a bit too small
    to offer, so the design was cut at the corner.
    """
    gap = 0.0005
    V = np.array([[0, 0, 0], [20, 0, 0], [20, 15 - gap, 0], [15, 20, 0], [0, 20, 0],   # the face
                  [20, 15, 0], [20, 20, 0], [15, 20, 0]], dtype=float)                 # its corner
    F = np.array([[0, 1, 2], [0, 2, 3], [0, 3, 4], [5, 6, 7]])
    faces = planar_faces(V, F)
    assert len(faces) == 1
    assert faces[0].area == pytest.approx(400.0, abs=0.01)
    assert faces[0].size == pytest.approx((20.0, 20.0), abs=0.001)


def test_stopping_early_lists_the_same_largest_faces():
    """Many small flat faces (a comb): the list stops looking once nothing left can make it."""
    teeth = [box(i * 4.0, 0, i * 4.0 + 2.0, 6.0 + i) for i in range(12)]
    comb = orient(shapely.union_all([box(0, -10, 48, 0)] + teeth), 1.0)
    V, F = extrude([comb], 5.0, 0.0)
    everything = planar_faces(V, F, limit=1000)
    for limit in (3, 8, 15):
        few = planar_faces(V, F, limit=limit)
        assert [(f.area, f.direction, f.inner) for f in few] == \
               [(f.area, f.direction, f.inner) for f in everything[:limit]]


def test_each_face_says_where_it_is_seen_from_and_its_sides():
    """The page names the plate's sides around the face, as OrcaSlicer's view of it shows them."""
    V, F = cube(10)
    faces = {f.direction: f for f in planar_faces(V, F)}
    assert faces["bottom"].seen == "bottom"
    assert faces["bottom"].sides == {"up": "front", "down": "back", "left": "left", "right": "right"}
    assert faces["top"].sides == {"up": "back", "down": "front", "left": "left", "right": "right"}
    assert faces["front"].seen == "front"
    assert faces["front"].sides == {"up": "top", "down": "bottom", "left": "left", "right": "right"}
    assert faces["back"].sides == {"up": "top", "down": "bottom", "left": "right", "right": "left"}
    # turned on the plate, the view still shows the plate's sides
    turned = {f.direction: f for f in planar_faces(V, F, world=_turned(90))}
    assert turned["bottom"].sides == faces["bottom"].sides


def test_the_whole_object_is_drawn_around_the_face(tmp_path):
    """A lid with a tab: the tab is not on the bottom face, but it shows around it."""
    from orca_svg_multicor.faces import context_dict, silhouettes
    body = orient(box(-20, -15, 20, 15), 1.0)
    tab = orient(box(-3, 15, 3, 19), 1.0)                       # sticks out at the back
    V1, F1 = extrude([body], 2.0, 0.0)
    V2, F2 = extrude([tab], 1.0, 1.0)                           # above the bed: not on the bottom
    V = np.concatenate([V1, V2])
    F = np.concatenate([F1, F2 + len(V1)])
    faces = planar_faces(V, F)
    bottom = next(f for f in faces if f.direction == "bottom" and f.height == 0.0)
    assert bottom.size == pytest.approx((40.0, 30.0))
    shape = silhouettes(V, F)(bottom)
    assert shape.area == pytest.approx(40 * 30 + 6 * 4, rel=1e-3)
    # seen from below with the front up, the tab at the back is at the bottom of the view
    d = context_dict(shape)
    assert d["context_bounds"][3] == pytest.approx(19.0, abs=0.01) and d["context"].startswith("M")


def test_the_page_gets_the_object_around_a_face(tray_project):
    from test_engine_service import make_service
    svc, out, _ = make_service()
    svc.handle({"action": "faces", "project": tray_project, "object_id": "3"})
    faces = next(m for m in out if m["type"] == "faces")
    default = next(f for f in faces["faces"] if f["id"] == faces["default"])
    assert default["context"].startswith("M") and default["seen"] == "bottom"
    other = next(f for f in faces["faces"] if f["id"] != faces["default"])
    assert "context" not in other                     # asked for when chosen
    svc.handle({"action": "face_context", "project": tray_project, "object_id": "3", "face_id": other["id"]})
    ctx = out[-1]
    assert ctx["type"] == "face_context" and ctx["face_id"] == other["id"] and ctx["context"].startswith("M")
    assert ctx["mtime"] == faces["mtime"]


def test_the_size_on_a_face():
    """design_size: what the page shows and the apply makes (panel.js, placement())."""
    size = E.design_size
    # automatic: 85% of the face, in proportion
    sx, sy, rw, rh, room_x, room_y, clamped = size(100, 50, 40, 30, 0)
    assert (rw, rh) == pytest.approx((34.0, 17.0)) and sx == sy and not clamped
    assert (room_x, room_y) == pytest.approx((3.0, 6.5))
    # past the face, up to covering it and 25% more
    sx, sy, rw, rh, room_x, room_y, clamped = size(100, 50, 40, 30, 0, width_mm=60)
    assert (rw, rh) == pytest.approx((60.0, 30.0)) and not clamped
    assert (room_x, room_y) == pytest.approx((10.0, 0.0))        # it moves while it still covers
    sx, sy, rw, rh, *_rest, clamped = size(100, 50, 40, 30, 0, width_mm=200)
    assert clamped and rh == pytest.approx(30 * 1.25) and rw == pytest.approx(75.0)
    # a height of its own, turned a quarter
    sx, sy, rw, rh, *_rest, clamped = size(100, 50, 40, 30, 90, width_mm=30, height_mm=40)
    assert (sx, sy) == pytest.approx((0.3, 0.8)) and (rw, rh) == pytest.approx((40.0, 30.0)) and not clamped


def _square_svg(svg):
    return svg('<rect x="0" y="0" width="100" height="100" fill="#ff0000"/>')


def test_a_design_covering_the_face_leaves_no_edge(svg, tray_project, tmp_path):
    floor = next(f for f in E.list_faces(tray_project, "3")["faces"] if f["dir"] == "top" and f["z"] == 2.0)
    n0 = len(Project(tray_project).object_mesh("3")[1])
    out = str(tmp_path / "cover.3mf")
    # the floor is 36 x 26: a square of 36 covers it (and is cut at its edge)
    E.apply_to_project(_square_svg(svg), tray_project, "3", out, Options(apply_width_mm=36), face_id=floor["id"])
    V, F = Project(out).object_mesh("3")
    top = V[F[n0:]].reshape(-1, 3)
    assert (np.ptp(top[:, 0]), np.ptp(top[:, 1])) == pytest.approx((36.0, 26.0), abs=0.01)


def test_a_design_stretched_to_the_face(svg, tray_project, tmp_path):
    floor = next(f for f in E.list_faces(tray_project, "3")["faces"] if f["dir"] == "top" and f["z"] == 2.0)
    n0 = len(Project(tray_project).object_mesh("3")[1])
    out = str(tmp_path / "stretch.3mf")
    E.apply_to_project(_square_svg(svg), tray_project, "3", out,
                       Options(apply_width_mm=30, apply_height_mm=20), face_id=floor["id"])
    V, F = Project(out).object_mesh("3")
    part = V[F[n0:]].reshape(-1, 3)
    assert (np.ptp(part[:, 0]), np.ptp(part[:, 1])) == pytest.approx((30.0, 20.0), abs=0.01)
