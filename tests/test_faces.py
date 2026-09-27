"""Flat faces of objects, and applying a design on the one the user picks."""
import os
import zipfile

import numpy as np
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
    assert default["dir"] == "top" and default["z"] == 2.0       # the floor, not the rim
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


def test_bottom_reads_correctly_from_below():
    """On the bottom, the design's right goes to -X: mirrored seen from above."""
    V, F = cube(10)
    bottom = next(f for f in planar_faces(V, F) if f.direction == "bottom")
    marker = {"#000000": [orient(box(2, -1, 4, 1), 1.0)]}     # right of center
    Vp, _ = extrude(place(marker, bottom)["#000000"], 0.5, -0.5)
    assert to_object(Vp, bottom)[:, 0].max() < 0


def test_default_face_prefers_up():
    V, F = cube(10)
    assert default_face(planar_faces(V, F)).direction == "top"
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
