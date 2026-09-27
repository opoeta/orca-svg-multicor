import os
import zipfile

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLES = os.path.join(ROOT, "examples")


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path_factory, monkeypatch):
    """Tests never write into the real OrcaSlicer data folder."""
    monkeypatch.setenv("SVGM_DATA_DIR", str(tmp_path_factory.mktemp("svgm_data")))


@pytest.fixture
def svg(tmp_path):
    """svg('<rect .../>', viewBox='0 0 100 100') -> path of a new SVG file."""
    counter = {"n": 0}

    def make(body, view_box="0 0 100 100", attrs=""):
        counter["n"] += 1
        p = tmp_path / f"t{counter['n']}.svg"
        p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" '
                     f'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="{view_box}" {attrs}>'
                     f"{body}</svg>", encoding="utf-8")
        return str(p)

    return make


def cube(size=10.0, z0=0.0):
    from shapely.geometry import box
    from shapely.geometry.polygon import orient

    from orca_svg_multicor.mesh import extrude
    return extrude([orient(box(-size / 2, -size / 2, size / 2, size / 2), 1.0)], size, z0)


@pytest.fixture
def bbs_project(tmp_path):
    """A project laid out like OrcaSlicer/Bambu save it: one cube object."""
    from orca_svg_multicor.threemf import Part, write_orca_project
    V, F = cube(20.0, -10.0)          # centered like Bambu does
    p = tmp_path / "project.3mf"
    write_orca_project(str(p), [Part("body", V, F, "#808080", 1)], "cube")
    return str(p)


@pytest.fixture
def legacy_project(tmp_path):
    """Old layout: the mesh inline in 3D/3dmodel.model, no model settings."""
    from orca_svg_multicor.threemf import CONTENT_TYPES, ROOT_RELS, mesh_xml
    V, F = cube(20.0, 0.0)
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
             ' <resources>\n  <object id="1" name="block" type="model">\n'
             + mesh_xml(V, F) + "  </object>\n </resources>\n"
             ' <build>\n  <item objectid="1"/>\n </build>\n</model>\n')
    p = tmp_path / "legacy.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("3D/3dmodel.model", model)
    return str(p)


def signed_volume(V, F):
    t = V[F]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)
