"""3MF writing and editing saved projects."""
import re
import xml.etree.ElementTree as ET
import zipfile

import pytest

from conftest import cube
from orca_svg_multicor.errors import ProjectError
from orca_svg_multicor.project3mf import Project
from orca_svg_multicor.threemf import Part, write_orca_project, write_standard_3mf

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


def parts():
    V, F = cube(10)
    return [Part('red & "bold" <x>', V, F, "#ff0000", 2), Part("white", V + [20, 0, 0], F, "#ffffff", 1)]


def test_orca_project_layout(tmp_path):
    p = tmp_path / "o.3mf"
    write_orca_project(str(p), parts(), "design")
    z = zipfile.ZipFile(p)
    names = z.namelist()
    assert "3D/Objects/object_1.model" in names and "3D/_rels/3dmodel.model.rels" in names
    root = z.read("3D/3dmodel.model").decode()
    ET.fromstring(root)                                   # well formed, names escaped
    assert root.count('p:path="/3D/Objects/object_1.model"') == 2
    cfg = ET.fromstring(z.read("Metadata/model_settings.config"))
    part_nodes = cfg.find("object").findall("part")
    assert [pn.get("id") for pn in part_nodes] == ["1", "2"]
    ext = [m.get("value") for pn in part_nodes for m in pn.findall("metadata") if m.get("key") == "extruder"]
    assert ext == ["2", "1"]
    names = [m.get("value") for pn in part_nodes for m in pn.findall("metadata") if m.get("key") == "name"]
    assert names[0] == 'red & "bold" <x>'


def test_orca_project_reads_back_as_one_object(tmp_path):
    p = tmp_path / "o.3mf"
    write_orca_project(str(p), parts(), "design")
    objs = Project(str(p)).objects()
    assert len(objs) == 1 and objs[0].kind == "components" and objs[0].parts == 2
    assert objs[0].size == pytest.approx((30, 10, 10))


def test_standard_3mf_has_colors(tmp_path):
    p = tmp_path / "s.3mf"
    write_standard_3mf(str(p), parts(), "design")
    root = ET.fromstring(zipfile.ZipFile(p).read("3D/3dmodel.model"))
    bases = root.find(CORE + "resources").find(CORE + "basematerials").findall(CORE + "base")
    assert [b.get("displaycolor") for b in bases] == ["#FF0000FF", "#FFFFFFFF"]


def _mesh_part(name, filament, z0, height=0.6):
    from shapely.geometry import box
    from shapely.geometry.polygon import orient

    from orca_svg_multicor.mesh import extrude
    V, F = extrude([orient(box(-2, -2, 2, 2), 1.0)], height, z0)
    return Part(name, V, F, "#00ff00", filament)


def test_apply_to_bbs_project_keeps_prefixes_and_adds_parts(bbs_project, tmp_path):
    prj = Project(bbs_project)
    (obj,) = prj.objects()
    lo, hi = obj.bbox
    assert [b - a for a, b in zip(lo, hi)] == pytest.approx([20, 20, 20])
    z0 = hi[2] - 0.6                                # inlaid in the top
    assert z0 == pytest.approx(10 - 0.6)
    prj.add_parts(obj.id, [_mesh_part("logo", 3, z0), _mesh_part("text", 4, z0)])
    out = tmp_path / "out.3mf"
    prj.save(str(out))

    z = zipfile.ZipFile(out)
    root = z.read("3D/3dmodel.model").decode()
    assert "ns0:" not in root and "ns1:" not in root
    comps = re.findall(r'<component p:path="([^"]+)" objectid="(\d+)"', root)
    assert len(comps) == 3 and len({c[1] for c in comps}) == 3
    sub = z.read("3D/Objects/object_1.model").decode()
    ids = re.findall(r'<object id="(\d+)"', sub)
    assert len(ids) == 3 and len(set(ids)) == 3
    ET.fromstring(sub)
    cfg = ET.fromstring(z.read("Metadata/model_settings.config"))
    obj_node = cfg.find("object")
    names = [m.get("value") for pn in obj_node.findall("part") for m in pn.findall("metadata")
             if m.get("key") == "name"]
    assert names == ["body", "logo", "text"]
    # reading it again sees one object, three parts, same height (inlay)
    again = Project(str(out)).objects()[0]
    assert again.parts == 3 and again.size[2] == pytest.approx(20)


def test_apply_raised_grows_the_object(bbs_project, tmp_path):
    prj = Project(bbs_project)
    obj = prj.objects()[0]
    z0 = obj.bbox[1][2]                             # raised on the top
    prj.add_parts(obj.id, [_mesh_part("logo", 2, z0, 1.0)])
    out = tmp_path / "raised.3mf"
    prj.save(str(out))
    assert Project(str(out)).objects()[0].size[2] == pytest.approx(21)


def test_apply_to_legacy_inline_mesh(legacy_project, tmp_path):
    prj = Project(legacy_project)
    (obj,) = prj.objects()
    assert obj.kind == "mesh" and obj.triangles == 12
    prj.add_parts(obj.id, [_mesh_part("logo", 2, 19.4)])
    assert prj.objects()[0].size[2] == pytest.approx(20)
    out = tmp_path / "legacy_out.3mf"
    prj.save(str(out))
    z = zipfile.ZipFile(out)
    ET.fromstring(z.read("3D/3dmodel.model"))
    cfg = ET.fromstring(z.read("Metadata/model_settings.config"))
    vols = cfg.find("object").findall("volume")
    assert [(v.get("firstid"), v.get("lastid")) for v in vols] == [("0", "11"), ("12", "23")]
    assert Project(str(out)).objects()[0].triangles == 24


def test_apply_to_same_file_components(tmp_path):
    p = tmp_path / "std.3mf"
    write_standard_3mf(str(p), parts(), "design")
    prj = Project(str(p))
    obj = prj.objects()[0]
    prj.add_parts(obj.id, [_mesh_part("logo", 3, 10)])
    out = tmp_path / "std_out.3mf"
    prj.save(str(out))
    root = zipfile.ZipFile(out).read("3D/3dmodel.model").decode()
    ET.fromstring(root)
    # the new mesh object is defined before the object that references it
    new_id = re.findall(r'<component objectid="(\d+)"', root)[-1]
    assert root.index(f'<object id="{new_id}"') < root.index(f'<object id="{obj.id}"')
    assert Project(str(out)).objects()[0].parts == 3


def test_missing_object_and_bad_zip(bbs_project, tmp_path):
    with pytest.raises(ProjectError):
        Project(bbs_project).object("999")
    bad = tmp_path / "bad.3mf"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ProjectError) as e:
        Project(str(bad))
    assert e.value.key == "error.project_read"
