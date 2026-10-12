"""Where the picker opens, settings across reinstalls, OrcaCloud installs and their notes."""
import os
import sys

from conftest import ROOT
from orca_svg_multicor import host as H
from orca_svg_multicor import service as S
from orca_svg_multicor.panel import build_settings_html
from test_engine_service import make_service

sys.path.insert(0, os.path.join(ROOT, "tools"))
import cloud_notes  # noqa: E402


def _picker(monkeypatch, svc, chosen):
    seen = []

    def pick(kind, title, initial="", patterns=(), label=""):
        seen.append(initial)
        return chosen

    monkeypatch.setattr(svc.host, "pick", pick)
    return seen


def test_the_picker_opens_where_the_person_was(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(H, "user_folders", lambda: [str(home / "Downloads"), str(home)])
    monkeypatch.setattr(S, "user_folders", H.user_folders)
    designs = tmp_path / "designs"
    designs.mkdir()
    logo = designs / "logo.svg"
    logo.write_text("<svg/>")
    svc, out, store = make_service()

    seen = _picker(monkeypatch, svc, str(logo))
    svc.handle({"action": "pick", "kind": "svg", "initial": ""})
    # the first time, Downloads: never the plugin's data folder
    assert seen == [str(home / "Downloads")]
    assert out[-1] == {"type": "picked", "kind": "svg", "path": str(logo), "cancelled": False}
    assert store["last_svg_folder"] == str(designs)

    # next time (OrcaSlicer restarted: no SVG on the page), where the last one came from
    seen = _picker(monkeypatch, svc, "")
    svc.handle({"action": "pick", "kind": "svg", "initial": ""})
    assert seen == [str(designs)]
    assert out[-1]["cancelled"] is True

    # with an SVG on the page, its folder
    other = tmp_path / "other"
    other.mkdir()
    seen = _picker(monkeypatch, svc, "")
    svc.handle({"action": "pick", "kind": "svg", "initial": str(other)})
    assert seen == [str(other)]

    # a remembered folder that is gone falls back to Downloads
    store["last_svg_folder"] = str(tmp_path / "gone")
    seen = _picker(monkeypatch, svc, "")
    svc.handle({"action": "pick", "kind": "svg", "initial": ""})
    assert seen == [str(home / "Downloads")]


def test_settings_survive_a_reinstall(tmp_path):
    # the settings someone had, copied to the data folder as they are saved
    svc, _out, store = make_service()
    svc.handle({"action": "save_settings", "settings": {"thickness_mm": 1.2, "max_colors": 6}, "quiet": True})
    assert H.read_settings_copy()["thickness_mm"] == 1.2

    # installed again (or from OrcaCloud instead of a file): an empty config
    _svc2, _out2, fresh = make_service()
    assert fresh["thickness_mm"] == 1.2 and fresh["max_colors"] == 6
    assert fresh["settings_rev"] == S.SETTINGS_REV

    # a config of its own is never replaced by the copy
    _svc3, _out3, own = make_service(cfg={"settings_rev": S.SETTINGS_REV, "thickness_mm": 0.4})
    assert own["thickness_mm"] == 0.4


def test_an_existing_config_writes_the_copy_once():
    assert H.read_settings_copy() == {}
    make_service(cfg={"settings_rev": S.SETTINGS_REV, "max_colors": 7})
    assert H.read_settings_copy()["max_colors"] == 7


def test_orcacloud_installs_are_recognized():
    sub = os.path.join("C:\\", "Users", "a", "AppData", "Roaming", "OrcaSlicer", "orca_plugins",
                       "_subscribed", "u1", "51a8", "__whl_extracted__", "orca_svg_multicor", "host.py")
    local = os.path.join("C:\\", "Users", "a", "AppData", "Roaming", "OrcaSlicer", "orca_plugins",
                         "orca_svg_multicor-3.9.1-py3-none-any.whl", "__whl_extracted__",
                         "orca_svg_multicor", "host.py")
    assert H.is_cloud_install(sub)
    assert not H.is_cloud_install(local)
    assert not H.is_cloud_install()              # this checkout


def test_the_config_tab_leaves_the_changelog_to_orcacloud():
    local = build_settings_html("pt_BR", {}, cloud=False)
    cloud = build_settings_html("pt_BR", {}, cloud=True)
    assert "## 3." in local and '"cloud": false' in local
    assert "## 3." not in cloud and '"cloud": true' in cloud


def test_orcacloud_notes_are_plain_text_in_both_languages():
    text = cloud_notes.notes("3.9.0")
    assert text.startswith("New\n\u2022 A step-by-step assistant")
    assert "Português (Brasil)" in text and "\u2022 Um assistente passo a passo" in text
    for mark in ("**", "###", "## ", "`"):
        assert mark not in text
    # one line per item: no sentence broken at 78 columns
    assert "Drawing colors in the project's filaments: when applying" in text
    assert len(text.encode("utf-8")) <= cloud_notes.LIMIT
    assert cloud_notes.notes("0.0.0-none") == ""


def test_the_data_folder_is_the_one_the_plugin_is_installed_in(tmp_path):
    portable = tmp_path / "OrcaSlicer portable" / "data"
    portable.mkdir(parents=True)
    pkg = portable / "orca_plugins" / "_subscribed" / "u1" / "51a8" / "__whl_extracted__" / "orca_svg_multicor"
    assert H.orca_data_dir(str(pkg / "host.py")) == str(portable)
    local = (portable / "orca_plugins" / "orca_svg_multicor-3.9.1-py3-none-any.whl" / "__whl_extracted__"
             / "orca_svg_multicor")
    assert H.orca_data_dir(str(local / "host.py")) == str(portable)
    assert not H.is_cloud_install(str(local / "host.py")) and H.is_cloud_install(str(pkg / "host.py"))
    # not installed: the platform's usual place, even in a folder named like OrcaSlicer's
    usual = H.orca_data_dir(os.path.join(ROOT, "src", "x.py"))
    assert H.orca_data_dir() == usual
    checkout = tmp_path / "Orca_Plugins" / "orca-svg-multicor" / "src" / "orca_svg_multicor"
    checkout.mkdir(parents=True)
    assert H.orca_data_dir(str(checkout / "host.py")) == usual
