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
    # the touching rings are parted by mesh.PINCH_GAP: a hundred-thousandth of a mm
    assert signed_volume(V, F) == pytest.approx(poly.area, rel=1e-4)


def test_write_stl(tmp_path):
    V, F = M.extrude([orient(box(0, 0, 1, 1), 1.0)], 1.0)
    p = tmp_path / "x.stl"
    M.write_stl(str(p), V, F)
    data = p.read_bytes()
    assert len(data) == 84 + 50 * len(F)
    assert np.frombuffer(data[80:84], dtype="<u4")[0] == len(F)


def test_reduce_keeps_a_small_distinct_color():
    """Sky blue + light cyan merge (similar) instead of the small green vanishing."""
    shares = {"#ffffff": 30.6, "#050808": 28.1, "#54bfed": 15.0, "#a75a21": 12.6,
              "#a6d6e4": 3.8, "#235ea6": 3.7, "#e7681d": 3.5, "#2c953a": 2.7}
    reg = {c: [box(0, 2 * k, a, 2 * k + 1)] for k, (c, a) in enumerate(shares.items())}
    out, mapping = C.reduce_colors(reg, 7)
    assert "#2c953a" in out                               # the green stays
    assert "#a6d6e4" in mapping["#54bfed"]                # the light cyan joined the sky blue


def test_levels_match_reduce_colors_at_every_count():
    shares = {"#ffffff": 30.6, "#050808": 28.1, "#54bfed": 15.0, "#a75a21": 12.6,
              "#a6d6e4": 3.8, "#235ea6": 3.7, "#e7681d": 3.5, "#2c953a": 2.7}
    reg = {c: [box(0, 2 * k, a, 2 * k + 1)] for k, (c, a) in enumerate(shares.items())}
    levels = C.color_levels(reg, upto=12)
    assert sorted(levels) == [2, 3, 4, 5, 6, 7, 8]
    for k, mapping in levels.items():
        _out, reduced = C.reduce_colors(reg, k, pre_tolerance=0)
        assert set(mapping.values()) == set(reduced)
        assert all(c in reduced[mapping[c]] for c in reg)


def test_pieces_touching_at_a_point_stay_closed():
    """Two squares of one color meeting at a corner: two shells, not a shared edge."""
    from orca_svg_multicor.mesh import extrude, is_watertight
    a, b = orient(box(0, 0, 5, 5), 1.0), orient(box(5, 5, 10, 10), 1.0)
    V, F = extrude([a, b], 1.0)
    assert is_watertight(F)


def test_sharp_tips_go_to_the_neighbor():
    """A 0.2 mm wide spike of black into white is cleaned; 90 degree corners stay."""
    from shapely.geometry import Polygon
    import shapely
    from orca_svg_multicor import geometry as G
    spike = Polygon([(10, 4.9), (16, 5.0), (10, 5.1)])            # needle into the white
    black = [orient(box(0, 0, 10, 10).union(spike), 1.0)]
    white = [orient(box(0, 0, 20, 10).difference(black[0]), 1.0)]
    out = G.absorb_thin({"#000000": black, "#ffffff": white}, 0.4)
    total = sum(p.area for ps in out.values() for p in ps)
    assert total == pytest.approx(200, abs=1e-3)                   # still tiling, no gap
    bx0, by0, bx1, by1 = shapely.union_all(out["#000000"]).bounds
    assert bx1 < 10.1                                              # the 6 mm needle is gone
    assert (bx0, by0, by1) == pytest.approx((0, 0, 10), abs=1e-3)  # the square kept its corners


def _non_manifold(F):
    import numpy as np
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _, count = np.unique(e, axis=0, return_counts=True)
    return int((count != 2).sum())


def test_collinear_points_keep_the_mesh_closed():
    """earcut drops a point in the middle of an edge; the walls must follow."""
    from orca_svg_multicor.mesh import extrude, is_watertight
    square = orient(Polygon([(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]), 1.0)
    V, F = extrude([square], 1.0)
    assert is_watertight(F) and _non_manifold(F) == 0


def test_rings_touching_at_a_point_keep_the_mesh_manifold():
    """A hole touching the outline at a vertex: valid, but its walls met there."""
    from orca_svg_multicor.mesh import extrude, is_watertight
    p = orient(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(0, 5), (4, 3), (4, 7)]]), 1.0)
    assert p.is_valid
    V, F = extrude([p], 1.0)
    assert is_watertight(F) and _non_manifold(F) == 0
