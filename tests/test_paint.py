"""Painting on the face: a brush stroke or a bare area filled with the color next to it."""
import pytest
from shapely.geometry import box

from orca_svg_multicor import engine as E
from orca_svg_multicor.faces import free_area, paint
from orca_svg_multicor.options import Options
from orca_svg_multicor.project3mf import Project
from test_faces import tray_project  # noqa: F401  (fixture)

RED, BLUE = "#ff0000", "#0000ff"
TWO = ('<rect x="0" y="0" width="70" height="100" fill="#ff0000"/>'
       '<rect x="70" y="0" width="30" height="100" fill="#0000ff"/>')


class _Face:
    polygon = box(-18, -13, 18, 13)


def _placed():
    return {RED: [box(-10, -10, 4, 10)], BLUE: [box(4, -10, 10, 10)]}


def test_a_brush_stroke_takes_its_color_over_the_others():
    stroke = {"kind": "brush", "color": RED, "width": 2.0, "points": [[0, 0], [8, 0]]}
    out = paint(_placed(), _Face(), [stroke])
    red = sum(p.area for p in out[RED])
    blue = sum(p.area for p in out[BLUE])
    assert red > 14 * 20 and blue < 6 * 20                      # red took a band of blue
    assert red + blue == pytest.approx(20 * 20)                  # inside the design: nothing added
    # past the design's edge, it also paints the bare face
    out = paint(_placed(), _Face(), [dict(stroke, points=[[0, 0], [14, 0]])])
    assert sum(p.area for ps in out.values() for p in ps) == pytest.approx(400 + 2 * 4 + 3.1416 / 2, rel=0.002)
    # it never leaves the face, and a color not in the design is ignored
    far = {"kind": "brush", "color": RED, "width": 4.0, "points": [[0, 0], [40, 0]]}
    assert max(p.bounds[2] for p in paint(_placed(), _Face(), [far])[RED]) == pytest.approx(18.0)
    assert paint(_placed(), _Face(), [dict(stroke, color="#00ff00")]) == paint(_placed(), _Face(), [])


def test_the_bucket_fills_the_bare_area_with_the_color_next_to_it():
    rings, color = free_area(_placed(), _Face(), (15, 0))
    assert color == RED                                          # touches 3 sides of red, 3 of blue
    filled = paint(_placed(), _Face(), [{"kind": "area", "color": color, "rings": rings}])
    total = sum(p.area for ps in filled.values() for p in ps)
    assert total == pytest.approx(36 * 26, rel=1e-6)            # nothing of the face left bare
    assert free_area(_placed(), _Face(), (0, 0)) is None          # on the design: nothing to fill


def _floor(project):
    return next(f for f in E.list_faces(project, "3")["faces"] if f["dir"] == "top" and f["z"] == 2.0)


def test_painted_areas_are_printed_in_the_same_layers(svg, tray_project, tmp_path):  # noqa: F811
    floor = _floor(tray_project)
    n0 = len(Project(tray_project).object_mesh("3")[1])
    path = svg(TWO)
    opts = Options(apply_width_mm=20, thickness_mode="layers", thickness_layers=3)
    stroke = {"kind": "brush", "color": RED, "width": 3.0, "points": [[0, 0], [9, 0]]}
    plain, painted = str(tmp_path / "plain.3mf"), str(tmp_path / "painted.3mf")
    _p, rep_plain = E.apply_to_project(path, tray_project, "3", plain, opts, face_id=floor["id"])
    _p, rep_painted = E.apply_to_project(path, tray_project, "3", painted, opts, face_id=floor["id"],
                                         paint_ops=[stroke])
    vol = lambda report: {r["color"]: r["volume_mm3"] for r in report}  # noqa: E731
    assert vol(rep_painted)[RED] > vol(rep_plain)[RED] and vol(rep_painted)[BLUE] < vol(rep_plain)[BLUE]
    V, F = Project(painted).object_mesh("3")
    z = V[F[n0:]].reshape(-1, 3)[:, 2]
    assert (z.min(), z.max()) == pytest.approx((2.0 - 0.6, 2.0), abs=1e-6)   # 3 layers, like the rest


def test_the_page_asks_where_the_bucket_fills(svg, tray_project):  # noqa: F811
    from test_engine_service import make_service
    svc, out, _ = make_service()
    floor = _floor(tray_project)
    msg = {"action": "paint_fill", "svg": svg(TWO), "project": tray_project, "object_id": "3",
           "face_id": floor["id"], "options": {"apply_width_mm": 20}, "colors": []}
    svc.handle(dict(msg, point=[15, 0]))
    found = out[-1]
    assert found["type"] == "paint_fill" and found["ok"] and found["op"]["color"] == RED
    assert found["op"]["kind"] == "area" and len(found["op"]["rings"][0]) >= 4
    svc.handle(dict(msg, point=[0, 0]))
    assert out[-1]["ok"] is False and out[-1]["text"]
