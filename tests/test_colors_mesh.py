"""Color math and meshes."""
import numpy as np
import pytest
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from conftest import signed_volume
from orca_svg_multicor import colors as C
from orca_svg_multicor import mesh as M


def test_delta_e_reference_values():
    # Sharma et al. CIEDE2000 test data, pair 1
    assert C.delta_e((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)) == pytest.approx(2.0425, abs=1e-4)
    assert C.color_distance("#ffffff", "#ffffff") == 0
    assert C.color_distance("#000000", "#ffffff") == pytest.approx(100, abs=0.5)


def test_near_whites_are_close_dark_colors_are_not():
    assert C.color_distance("#ffffff", "#f4f4f4") < 4
    assert C.color_distance("#000000", "#0c0c30") > 5


@pytest.mark.parametrize("hexa,key", [("#000000", "black"), ("#ffffff", "white"),
                                      ("#e63946", "red"), ("#1d3557", "navy"),
                                      ("#00ae42", "green"), ("#ff8000", "orange")])
def test_color_names(hexa, key):
    assert C.color_name_key(hexa) == key


def test_normalize_hex():
    assert C.normalize_hex("#ABC") == "#aabbcc"
    assert C.normalize_hex("#11223344") == "#112233"
    assert C.normalize_hex("red") is None and C.normalize_hex("#zzz") is None


def _reg(**areas):
    return {c.replace("_", "#"): [box(0, 0, a, 1)] for c, a in areas.items()}


def test_merge_similar_keeps_the_biggest_as_representative():
    reg = {"#ffffff": [box(0, 0, 10, 1)], "#fefefe": [box(0, 2, 30, 3)], "#000000": [box(0, 4, 5, 5)]}
    out, mapping = C.merge_similar(reg, 3)
    assert set(out) == {"#fefefe", "#000000"}
    assert sorted(mapping["#fefefe"]) == ["#fefefe", "#ffffff"]


def test_reduce_protects_dominant_colors():
    reg = {"#000000": [box(0, 0, 41, 1)], "#ffffff": [box(0, 2, 40, 3)], "#fefefe": [box(0, 4, 18, 5)],
           "#e30613": [box(0, 6, 1, 7)], "#7a4a2a": [box(0, 8, 0.04, 9)]}
    out, mapping = C.reduce_colors(reg, 3)
    assert set(out) == {"#000000", "#ffffff", "#e30613"}
    assert "#7a4a2a" in mapping["#e30613"]            # the tiny brown went to the red
    assert "#fefefe" in mapping["#ffffff"]


def test_match_filaments():
    fil = [{"n": 1, "color": "#ffffff"}, {"n": 2, "color": "#101010"}, {"n": 3, "color": ""}]
    m = C.match_filaments(["#1d3557", "#f1faee"], fil)
    assert m["#1d3557"][0] == 2 and m["#f1faee"][0] == 1


def test_average_color_in_linear_light():
    assert C.average_color(["#000000", "#ffffff"]) == "#bcbcbc"


def test_extrusion_is_watertight_outward_and_exact():
    ring = orient(Polygon(box(0, 0, 10, 10).exterior, [box(3, 3, 7, 7).exterior]), 1.0)
    V, F = M.extrude([ring], 2.0, 1.0)
    assert M.is_watertight(F)
    assert signed_volume(V, F) == pytest.approx((100 - 16) * 2.0)
    assert V[:, 2].min() == pytest.approx(1.0) and V[:, 2].max() == pytest.approx(3.0)


def test_watertight_detects_flipped_face():
    V, F = M.extrude([orient(box(0, 0, 1, 1), 1.0)], 1.0)
    F2 = F.copy()
    F2[0] = F2[0][::-1]
    assert not M.is_watertight(F2)


def test_touching_holes_still_close():
    # hole touching the outer ring at one point
    poly = orient(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                          [[(0, 5), (4, 3), (4, 7)]]), 1.0)
    if not poly.is_valid:
        pytest.skip("shapely considers this polygon invalid")
    V, F = M.extrude([poly], 1.0)
    assert signed_volume(V, F) == pytest.approx(poly.area, rel=1e-6)


def test_write_stl(tmp_path):
    V, F = M.extrude([orient(box(0, 0, 1, 1), 1.0)], 1.0)
    p = tmp_path / "x.stl"
    M.write_stl(str(p), V, F)
    data = p.read_bytes()
    assert len(data) == 84 + 50 * len(F)
    assert np.frombuffer(data[80:84], dtype="<u4")[0] == len(F)
