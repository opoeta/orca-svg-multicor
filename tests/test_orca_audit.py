"""
The plugin under OrcaSlicer's audit rules, in a fresh interpreter.

OrcaSlicer loads a plugin without auditing it, then audits everything its
capabilities do: a path with "conf", "cert" or "secret" in a name is refused,
and a file outside its own folders (the standard library included) needs the
user's permission. numpy cannot be imported without reading
numpy/__config__.py, so the plugin must load its libraries at load time and
read no code afterwards.
"""
import json
import os
import subprocess
import sys

from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from conftest import EXAMPLES, ROOT
from orca_svg_multicor.mesh import extrude
from orca_svg_multicor.threemf import Part, write_orca_project

SCRIPT = r'''
import json, os, re, sys
root, tmp, tray, badge = sys.argv[1:5]
sys.path[:0] = [os.path.join(root, "src"), os.path.join(root, "tests")]
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"] = tmp

import orca_stub
orca = orca_stub.make_orca(tmp)
sys.modules["orca"] = orca

# loading the plugin: not audited
import orca_svg_multicor
orca.plugin_class().register_capabilities()
page_cls = next(c for c in orca.registered if c.__name__ == "PanelPage")

audited, seen = [False], []

def hook(event, args):
    if not audited[0] or event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path = os.fsdecode(args[0])
    names = [p.lower() for p in re.split(r"[\\/]", os.path.abspath(path)) if p]
    if any(k in n for n in names for k in ("conf", "cert", "secret")):
        seen.append(["denied", path])
        raise PermissionError("Plugin attempted an audited operation without permission")
    if path.lower().endswith((".py", ".pyc", ".pyd", ".so", ".dll")):
        seen.append(["code read after load", path])

sys.addaudithook(hook)
audited[0] = True
page = page_cls()
out = os.path.join(tmp, "out")
os.makedirs(out)
page.save_config(json.dumps({"input_folder": tmp, "output_folder": out}))
page.on_message({"action": "init"})
page.on_message({"action": "analyze", "svg": badge, "options": {}})
page.on_message({"action": "generate", "svg": badge, "options": {}, "colors": []})
page.on_message({"action": "faces", "project": tray, "object_id": "3"})
faces = next((m for m in page.posted if m.get("type") == "faces"), {"default": None})
page.on_message({"action": "apply", "svg": badge, "project": tray, "object_id": "3",
                 "face_id": faces["default"], "options": {"rotation": 90}, "colors": []})
audited[0] = False
print(json.dumps({"seen": seen, "types": [m.get("type") for m in page.posted],
                  "errors": [m.get("text") for m in page.posted if m.get("type") == "error"]}))
'''


def _tray(path):
    ring = orient(Polygon(box(-20, -15, 20, 15).exterior, [box(-18, -13, 18, 13).exterior]), 1.0)
    write_orca_project(path, [Part("walls", *extrude([ring], 8.0, 2.0), "#ff00aa", 1),
                              Part("floor", *extrude([orient(box(-20, -15, 20, 15), 1.0)], 2.0, 0.0),
                                   "#ff00aa", 1)], "tray")


def test_capabilities_read_no_code_and_no_denied_path(tmp_path):
    tray = str(tmp_path / "tray.3mf")
    _tray(tray)
    run = subprocess.run([sys.executable, "-c", SCRIPT, ROOT, str(tmp_path), tray,
                          os.path.join(EXAMPLES, "badge.svg")],
                         cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[-3000:]
    result = json.loads(run.stdout.strip().splitlines()[-1])
    assert result["seen"] == []
    assert result["errors"] == []
    assert "analysis" in result["types"] and "faces" in result["types"]
    assert result["types"].count("done") == 2                # generate and apply


def test_a_refused_import_says_to_restart(monkeypatch):
    """If numpy could not be loaded at startup, the message says what to do."""
    import builtins

    import pytest

    from orca_svg_multicor import deps
    from orca_svg_multicor.errors import EngineError
    real = builtins.__import__

    def refuse(name, *a, **k):
        if name in ("engine", "orca_svg_multicor.engine") or (a and a[2] and "engine" in a[2]):
            raise PermissionError("Plugin attempted an audited operation without permission")
        return real(name, *a, **k)

    monkeypatch.delitem(sys.modules, "orca_svg_multicor.engine", raising=False)
    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(EngineError) as e:
        deps.load_engine()
    assert e.value.key == "error.deps_blocked"
