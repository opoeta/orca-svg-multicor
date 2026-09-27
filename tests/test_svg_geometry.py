"""SVG reading and geometry, including every bug fixed in 3.0."""
import math

import pytest

from orca_svg_multicor import geometry as G
from orca_svg_multicor.errors import SvgError
from orca_svg_multicor.svgread import PX_TO_MM, read_svg


def areas(path, strokes=True, scale=1.0):
    doc = read_svg(path, include_strokes=strokes)
    reg = G.color_regions(doc, G.Frame.for_bbox(doc.bbox, scale), step_mm=0.05,
                          tolerance=0.0, min_area=0.0)
    return {c: G.total_area(p) for c, p in reg.items()}, doc


def test_occlusion_later_shapes_cut_earlier_ones(svg):
    a, _ = areas(svg('<rect width="100" height="100" fill="#000"/>'
                     '<circle cx="50" cy="50" r="30" fill="#fff"/>'))
    circle = math.pi * 30 ** 2
    assert a["#ffffff"] == pytest.approx(circle, rel=2e-3)
    assert a["#000000"] == pytest.approx(10000 - circle, rel=2e-3)
    assert sum(a.values()) == pytest.approx(10000, rel=1e-6)


def test_open_path_keeps_its_first_point(svg):
    a, _ = areas(svg('<path d="M0,0 L100,0 L100,100" fill="#f00"/>'))
    assert a["#ff0000"] == pytest.approx(5000, rel=1e-6)


def test_nonzero_island_inside_hole(svg):
    a, _ = areas(svg('<path fill="#0a0" d="M0,0 L100,0 L100,100 L0,100 Z '
                     'M20,20 L20,80 L80,80 L80,20 Z M40,40 L60,40 L60,60 L40,60 Z"/>'))
    assert a["#00aa00"] == pytest.approx(10000 - 3600 + 400, rel=1e-6)


def test_nonzero_same_direction_rings_do_not_make_holes(svg):
    a, _ = areas(svg('<path fill="#123456" d="M0,0 L100,0 L100,100 L0,100 Z '
                     'M20,20 L80,20 L80,80 L20,80 Z"/>'))
    assert a["#123456"] == pytest.approx(10000, rel=1e-6)


def test_evenodd_overlap_is_a_hole(svg):
    a, _ = areas(svg('<path fill="#f80" fill-rule="evenodd" '
                     'd="M0,0 L60,0 L60,60 L0,60 Z M40,40 L100,40 L100,100 L40,100 Z"/>'))
    assert a["#ff8800"] == pytest.approx(3600 * 2 - 2 * 400, rel=1e-6)


def test_self_intersecting_nonzero_star(svg):
    # a pentagram: nonzero fills the center, evenodd leaves it empty
    d = "M50,0 L79,90 L2,35 L98,35 L21,90 Z"
    nz, _ = areas(svg(f'<path fill="#f00" d="{d}"/>'))
    eo, _ = areas(svg(f'<path fill="#f00" fill-rule="evenodd" d="{d}"/>'))
    assert nz["#ff0000"] > eo["#ff0000"] * 1.2


def test_gradient_uses_average_of_stops_and_warns(svg):
    a, doc = areas(svg('<defs><linearGradient id="g"><stop offset="0" stop-color="#ff0000"/>'
                       '<stop offset="1" stop-color="#0000ff"/></linearGradient></defs>'
                       '<rect width="100" height="100" fill="url(#g)"/>'))
    (color,) = a
    assert color not in ("#000000", "#ff0000", "#0000ff")
    assert "warn.gradient" in [k for k, _ in doc.warnings]


def test_gradient_href_inherits_stops(svg):
    a, _ = areas(svg('<defs><linearGradient id="a"><stop offset="0" stop-color="#00ff00"/></linearGradient>'
                     '<linearGradient id="b" xlink:href="#a" x1="0" x2="1"/></defs>'
                     '<rect width="10" height="10" fill="url(#b)"/>'))
    assert list(a) == ["#00ff00"]


def test_invisible_shapes_are_skipped(svg):
    a, _ = areas(svg('<rect width="50" height="50" fill="#f00"/>'
                     '<rect x="50" width="50" height="50" fill="#0f0" opacity="0"/>'
                     '<rect y="50" width="50" height="50" fill="#00f" fill-opacity="0"/>'
                     '<rect x="50" y="50" width="50" height="50" fill="#ff0" style="display:none"/>'
                     '<rect x="50" y="50" width="50" height="50" fill="#0ff" visibility="hidden"/>'
                     '<rect x="60" y="60" width="10" height="10" fill="rgba(0,0,0,0)"/>'))
    assert set(a) == {"#ff0000"}


def test_strokes_become_area_and_tile_the_plane(svg):
    a, _ = areas(svg('<rect width="100" height="100" fill="#fff"/>'
                     '<path d="M10,50 L90,50" stroke="#000" stroke-width="10" fill="none"/>'
                     '<circle cx="50" cy="50" r="30" fill="none" stroke="#f00" stroke-width="4"/>'))
    assert set(a) == {"#ffffff", "#000000", "#ff0000"}
    assert sum(a.values()) == pytest.approx(10000, rel=1e-6)


def test_strokes_can_be_turned_off(svg):
    a, _ = areas(svg('<path d="M10,50 L90,50" stroke="#000" stroke-width="10" fill="none"/>'
                     '<rect width="20" height="20" fill="#fff"/>'), strokes=False)
    assert set(a) == {"#ffffff"}


def test_css_classes_grouped_selectors_and_rgb(svg):
    a, _ = areas(svg('<style>.a,.b{fill:#ff0000}.c{fill:rgb(0, 0, 255)}</style>'
                     '<rect class="a" width="40" height="40"/><rect class="b" x="50" width="40" height="40"/>'
                     '<rect class="c" y="50" width="40" height="40"/>'))
    assert a == {"#ff0000": pytest.approx(3200), "#0000ff": pytest.approx(1600)}


def test_coreldraw_cdata_style_and_physical_size(svg):
    p = svg('<defs><style type="text/css"><![CDATA[ .fil0 {fill:#FEFEFE} .fil1 {fill:#E30613} ]]></style></defs>'
            '<rect class="fil0" width="10000" height="5000"/>'
            '<path class="fil1" d="M1000 1000 L4000 1000 L4000 4000 L1000 4000 Z"/>',
            view_box="0 0 10000 5000", attrs='width="100mm" height="50mm"')
    doc = read_svg(p)
    assert doc.physical
    w, h = doc.size_mm
    assert w == pytest.approx(100, rel=1e-3) and h == pytest.approx(50, rel=1e-3)
    assert set(doc.colors()) == {"#fefefe", "#e30613"}


def test_transforms_are_applied(svg):
    a, doc = areas(svg('<g transform="translate(50 0) scale(2)"><rect width="10" height="10" fill="#f00"/></g>'
                       '<rect width="10" height="10" fill="#0f0"/>'))
    assert a["#ff0000"] == pytest.approx(400)
    assert doc.bbox == pytest.approx((0, 0, 70, 20))


def test_use_elements(svg):
    a, _ = areas(svg('<defs><rect id="r" width="10" height="10" fill="#123456"/></defs>'
                     '<use href="#r" x="20"/><use href="#r" x="40"/>'))
    assert a["#123456"] == pytest.approx(200)


def test_text_and_images_warn(svg):
    doc = read_svg(svg('<rect width="10" height="10" fill="#f00"/><text x="0" y="20">Hi</text>'
                       '<image href="x.png" width="5" height="5"/>'))
    keys = [k for k, _ in doc.warnings]
    assert "warn.text" in keys and "warn.image" in keys


def test_tiny_viewbox_is_sampled_in_millimeters(svg):
    # a 0..1 viewBox scaled to 100 mm must keep its circles round
    doc = read_svg(svg('<circle cx="0.5" cy="0.5" r="0.4" fill="#f00"/>', view_box="0 0 1 1"))
    scale = 100.0 / doc.size_px[0]
    reg = G.color_regions(doc, G.Frame.for_bbox(doc.bbox, scale), step_mm=0.1,
                          tolerance=0.02, min_area=0.0)
    r_mm = 0.4 * scale
    assert G.total_area(reg["#ff0000"]) == pytest.approx(math.pi * r_mm ** 2, rel=2e-3)


def test_empty_and_shapeless_svgs_raise(svg, tmp_path):
    empty = tmp_path / "empty.svg"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SvgError) as e:
        read_svg(str(empty))
    assert e.value.key == "error.svg_empty"
    with pytest.raises(SvgError) as e:
        read_svg(svg('<rect width="10" height="10" fill="none"/>'))
    assert e.value.key == "error.svg_no_shapes"


def test_px_to_mm():
    assert PX_TO_MM == pytest.approx(25.4 / 96)


def test_absorb_thin_hands_slivers_to_neighbors():
    from shapely.geometry import box
    # white 0.1 mm line between two black halves
    regions = {"#000000": [box(0, 0, 10, 10), box(10.1, 0, 20, 10)],
               "#ffffff": [box(10, 0, 10.1, 10)]}
    out = G.absorb_thin(regions, 0.3)
    assert "#ffffff" not in out
    assert G.total_area(out["#000000"]) == pytest.approx(200, rel=1e-6)


def test_absorb_thin_keeps_wide_features():
    from shapely.geometry import box
    regions = {"#000000": [box(0, 0, 10, 10)], "#ffffff": [box(10, 0, 20, 10)]}
    out = G.absorb_thin(regions, 0.3)
    assert G.total_area(out["#ffffff"]) == pytest.approx(100)


def test_base_plate_shapes():
    from shapely.geometry import Polygon, box
    ring = Polygon(box(0, 0, 10, 10).exterior, [box(3, 3, 7, 7).exterior])
    outline = G.base_plate([ring], 1.0, "outline")
    assert len(outline) == 1 and not outline[0].interiors       # holes are filled
    assert outline[0].area == pytest.approx(144, rel=0.02)
    rect = G.base_plate([box(0, 0, 10, 4)], 2.0, "rectangle", corner=1.0)
    assert rect[0].bounds == pytest.approx((-2, -2, 12, 6), abs=1e-6)


def test_preview_svg_contains_every_layer():
    from shapely.geometry import box
    s = G.preview_svg([("#ff0000", "#ff0000", [box(0, 0, 10, 10)]),
                       ("#00ff00", "#00ff00", [box(2, 2, 4, 4)])])
    assert s.startswith("<svg") and s.count("<path") == 2 and 'data-key="#00ff00"' in s
