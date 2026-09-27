"""Engine pipeline and the page <-> plugin service."""
import os
import zipfile
import xml.etree.ElementTree as ET

import pytest

from conftest import EXAMPLES
from orca_svg_multicor import engine as E
from orca_svg_multicor.errors import EngineError
from orca_svg_multicor.host import BaseHost
from orca_svg_multicor.options import Options
from orca_svg_multicor.service import Service

BADGE = os.path.join(EXAMPLES, "badge.svg")


def test_analyze_badge():
    res = E.analyze(BADGE, Options())
    assert res["raw_count"] == 5 and len(res["colors"]) == 4
    first = res["colors"][0]
    assert first["color"] == "#1d3557" and first["background"] is True
    assert res["size_mm"] == pytest.approx([100, 100], abs=0.05)
    assert res["preview"].startswith("<svg")
    assert sum(c["area_pct"] for c in res["colors"]) == pytest.approx(100, abs=0.05)


def test_size_modes():
    doc = E.load_document(BADGE)
    assert E.scale_for(doc, Options(size_mode="height", size_mm=50)) * doc.size_px[1] == pytest.approx(50)
    orig = E.analyze(BADGE, Options(size_mode="original"))
    # width="80mm" for a 200 unit canvas; the drawing itself spans 192 units
    assert orig["size_mm"] == pytest.approx([76.8, 76.8], abs=0.05)


def test_generate_with_choices_and_base(tmp_path):
    res = E.analyze(BADGE, Options())
    choices = {c["color"]: {"name": f"P{i}", "filament": i + 1, "enabled": i != 1}
               for i, c in enumerate(res["colors"])}
    dest, report = E.generate(BADGE, str(tmp_path), Options(base_thickness_mm=1.0, base_filament=4),
                              choices)
    assert os.path.basename(dest) == "badge_multicolor.3mf"
    assert [r["name"] for r in report] == ["base", "P0", "P2", "P3"]
    assert [r["filament"] for r in report] == [4, 1, 3, 4]
    assert all(r["watertight"] for r in report)
    cfg = ET.fromstring(zipfile.ZipFile(dest).read("Metadata/model_settings.config"))
    assert len(cfg.find("object").findall("part")) == 4


def test_generate_errors(tmp_path):
    res = E.analyze(BADGE, Options())
    none = {c["color"]: {"enabled": False} for c in res["colors"]}
    with pytest.raises(EngineError) as e:
        E.generate(BADGE, str(tmp_path), Options(), none)
    assert e.value.key == "error.nothing_selected"
    with pytest.raises(EngineError) as e:
        E.generate(BADGE, str(tmp_path), Options(), {"#abcdef": {"name": "x"}})
    assert e.value.key == "error.stale_colors"
    with pytest.raises(EngineError):
        E.generate(str(tmp_path / "missing.svg"), str(tmp_path), Options())


def test_apply_never_overwrites_source(bbs_project, tmp_path):
    with pytest.raises(EngineError) as e:
        E.apply_to_project(BADGE, bbs_project, "2", bbs_project, Options())
    assert e.value.key == "error.same_output"
    out = E.project_output_path(bbs_project, os.path.dirname(bbs_project))
    assert out != bbs_project


def test_apply_places_design_on_top_face(bbs_project, tmp_path):
    rep = E.Reporter()
    dest, report = E.apply_to_project(BADGE, bbs_project, "2", str(tmp_path / "a.3mf"),
                                      Options(fit="inlay", thickness_mm=0.6), rep=rep)
    from orca_svg_multicor.project3mf import Project
    obj = Project(dest).objects()[0]
    assert obj.parts == 1 + len(report)
    assert obj.size == pytest.approx((20, 20, 20))          # 85% of the face, inlay keeps height
    assert any(k == "log.placed" for _lvl, k, _p in rep.messages)


def test_options_are_validated():
    o = Options(size_mm="abc", thickness_mm=-3, max_colors=999, fit="weird", size_mode="x")
    assert o.size_mm == 100 and o.thickness_mm == 0.01 and o.max_colors == 64
    assert o.fit == "inlay" and o.size_mode == "width"
    assert Options(include_strokes="false").include_strokes is False


# ---------------------------------------------------------------- service
class FakeHost(BaseHost):
    def __init__(self, lang="en"):
        self.lang = lang

    def language(self):
        return self.lang

    def filaments(self):
        return {"source": "test", "filaments": [{"n": 1, "name": "White", "color": "#ffffff"},
                                                {"n": 2, "name": "Black", "color": "#000000"}]}


def make_service(lang="en", cfg=None):
    store = dict(cfg or {})
    out = []

    def get():
        return dict(store)

    def save(c):
        store.clear()
        store.update(c)
        return True

    return Service(FakeHost(lang), (get, save), out.append, mode="dev"), out, store


def test_service_init_and_language_switch():
    svc, out, store = make_service("pt_BR")
    svc.handle({"action": "init"})
    init = next(m for m in out if m["type"] == "init")
    assert init["lang"] == "pt_BR" and init["catalog"]["out.add_plate"] != "Add to the plate"
    assert any(l["code"] == "en" for l in init["languages"])
    svc.handle({"action": "set_language", "lang": "en"})
    msg = out[-1]
    assert msg["type"] == "i18n" and msg["catalog"]["out.add_plate"] == "Add to the plate"
    assert store["language"] == "en"


def test_service_errors_are_translated():
    svc, out, _ = make_service("pt_BR")
    svc.handle({"action": "analyze", "svg": "nope.svg"})
    err = out[-1]
    assert err["type"] == "error" and err["action"] == "analyze"
    assert err["text"] == svc.tr("error.no_svg") and err["text"] != "error.no_svg"


def test_service_analyze_and_generate(tmp_path):
    svc, out, _ = make_service("en", {"output_folder": str(tmp_path)})
    svc.handle({"action": "analyze", "svg": BADGE, "options": {"max_colors": 4}})
    an = next(m for m in out if m["type"] == "analysis")
    assert an["original"] and len(an["colors"]) == 4
    assert an["colors"][0]["filament"] == 2          # navy -> black filament
    colors = [{"color": c["color"], "name": c["name"], "filament": c["filament"], "enabled": True}
              for c in an["colors"]]
    svc.handle({"action": "generate", "svg": BADGE, "options": {}, "colors": colors})
    done = next(m for m in out if m["type"] == "done")
    assert os.path.isfile(done["path"]) and done["folder"] == str(tmp_path)
    assert any(m["type"] == "progress" for m in out)


def test_service_upload_and_unknown_action(tmp_path):
    svc, out, _ = make_service("en", {"input_folder": str(tmp_path)})
    svc.handle({"action": "upload", "kind": "svg", "name": "../../evil name?.svg",
                "data": '<svg xmlns="http://www.w3.org/2000/svg"/>'})
    picked = next(m for m in out if m["type"] == "picked")
    assert os.path.dirname(picked["path"]) == str(tmp_path)
    assert os.path.basename(picked["path"]) == "evil name_.svg"
    svc.handle({"action": "rm_rf"})
    assert out[-1]["type"] == "error"


def test_service_save_settings_filters_keys():
    svc, out, store = make_service()
    svc.handle({"action": "save_settings", "settings": {"size_mm": 42, "evil": 1, "language": "xx"}})
    assert store == {"size_mm": 42}
    assert out[-1]["type"] in ("saved", "log")


def test_project_filaments_are_read_and_checked(bbs_project, tmp_path):
    import json
    import shutil
    prj = str(tmp_path / "two_filaments.3mf")
    shutil.copy(bbs_project, prj)
    with zipfile.ZipFile(prj, "a") as z:
        z.writestr("Metadata/project_settings.config",
                   json.dumps({"filament_colour": ["#0086D6", "#FFFFFF"],
                               "filament_settings_id": ["PLA A", "PLA B"]}))
    listing = E.list_objects(prj)
    assert [f["color"] for f in listing["filaments"]] == ["#0086d6", "#ffffff"]
    res = E.analyze(BADGE, Options())
    choices = {c["color"]: {"filament": i + 1} for i, c in enumerate(res["colors"])}
    rep = E.Reporter()
    E.apply_to_project(BADGE, prj, "2", str(tmp_path / "out.3mf"), Options(), choices, rep=rep)
    warns = [p for lvl, k, p in rep.messages if k == "warn.project_filaments"]
    assert warns and warns[0]["n"] == 2
