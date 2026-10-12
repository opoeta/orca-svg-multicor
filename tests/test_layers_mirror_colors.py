"""The file's layers, mirroring, and the project's filaments taking the parts' colors."""
import json
import os
import shutil
import zipfile

import pytest

from conftest import EXAMPLES
from orca_svg_multicor import engine as E
from orca_svg_multicor.options import Options
from orca_svg_multicor.project3mf import Project

BADGE = os.path.join(EXAMPLES, "badge.svg")
TWO_LAYERS = ('<g id="Fundo" data-name="Fundo"><rect x="0" y="0" width="100" height="100" fill="#ffffff"/></g>'
              '<g id="Logo" data-name="Logo"><rect x="60" y="20" width="30" height="30" fill="#ff0000"/></g>'
              '<circle cx="20" cy="80" r="10" fill="#0000ff"/>')


def test_the_layers_of_the_file_are_listed(svg):
    res = E.analyze(svg(TWO_LAYERS), Options(size_mode="width", size_mm=100))
    assert [(lay["name"], lay["shapes"]) for lay in res["layers"]] == [("Fundo", 1), ("Logo", 1), ("", 1)]
    assert res["layers"][-1]["key"] == "loose"           # shapes outside every layer


def test_a_hidden_layer_is_left_out_and_the_frame_stays(svg):
    path = svg(TWO_LAYERS)
    full = E.analyze(path, Options(size_mode="width", size_mm=100))
    logo_only = E.analyze(path, Options(size_mode="width", size_mm=100, hidden_layers=["0", "loose"]))
    assert [c["color"] for c in logo_only["colors"]] == ["#ff0000"]
    assert logo_only["box_mm"] == full["box_mm"]          # same size and place as with every layer
    assert logo_only["layers"] == full["layers"]          # the list still offers every layer


def test_mirror_flips_left_and_right(svg):
    path = svg(TWO_LAYERS)
    plain = E.process(E.load_document(path), 1.0, Options(min_detail_mm=0))[0]
    mirrored = E.process(E.load_document(path), 1.0, Options(min_detail_mm=0, mirror=True))[0]
    x_plain = plain["#ff0000"][0].centroid.x
    assert mirrored["#ff0000"][0].centroid.x == pytest.approx(-x_plain)
    assert mirrored["#ff0000"][0].exterior.is_ccw                # still a proper outline


def test_the_project_filaments_take_the_parts_colors(bbs_project, tmp_path):
    prj = str(tmp_path / "with_filaments.3mf")
    shutil.copy(bbs_project, prj)
    with zipfile.ZipFile(prj, "a") as z:
        z.writestr("Metadata/project_settings.config", json.dumps(
            {"filament_colour": ["#808080", "#808080", "#808080", "#808080"]}))
    obj = E.list_objects(prj)["objects"][0]["id"]
    res = E.analyze(BADGE, Options())
    choices = {c["color"]: {"filament": k + 1} for k, c in enumerate(res["colors"])}
    out = str(tmp_path / "colored.3mf")
    E.apply_to_project(BADGE, prj, obj, out, Options(project_colors=True), choices)
    colors = [f["color"] for f in Project(out).filaments()]
    assert colors == [c["color"] for c in res["colors"]][:4]
    # without the option the project keeps its colors
    E.apply_to_project(BADGE, prj, obj, out, Options(), choices)
    assert [f["color"] for f in Project(out).filaments()] == ["#808080"] * 4
