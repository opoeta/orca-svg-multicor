"""
The plugin under OrcaSlicer's permission rules (src/slic3r/plugin/PluginAuditManager.cpp),
in a fresh interpreter.

OrcaSlicer audits what a capability does: its data folder is free to read and
write; any other file, a new process or a new thread needs the user's "Yes",
which is remembered per exact target (the path, the command line, "thread").
An event with two paths (shutil.copyfile, os.rename) is judged with both
together. So the same work done twice must not ask again: a target with a new
name each time (a timestamped backup next to the project) would ask at every
use.
"""
import json
import os
import shutil
import subprocess
import sys
import time

from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from conftest import EXAMPLES, ROOT
from orca_svg_multicor.mesh import extrude
from orca_svg_multicor.threemf import Part, write_orca_project

SCRIPT = r'''
import json, os, re, sys, time
root, tmp, tray, badge, installed = sys.argv[1:6]
sys.path[:0] = [installed, os.path.join(root, "tests")]
os.environ.pop("SVGM_DATA_DIR", None)
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "elsewhere")
data_dir = os.path.join(tmp, "OrcaSlicer")          # OrcaSlicer's data_dir(): read + write

import orca_stub
orca = orca_stub.make_orca(tmp)
sys.modules["orca"] = orca
import orca_svg_multicor                            # loading: not audited
assert orca_svg_multicor.__file__.startswith(installed), orca_svg_multicor.__file__
orca.plugin_class().register_capabilities()
page_cls = next(c for c in orca.registered if c.__name__ == "PanelPage")

CATEGORY = {
    "glob.glob": "fs_read", "glob.glob/2": "fs_read", "os.listdir": "fs_read", "os.scandir": "fs_read",
    "os.walk": "fs_read", "os.fwalk": "fs_read",
    "os.rename": "fs_readwrite", "os.chmod": "fs_readwrite", "os.utime": "fs_readwrite",
    "os.truncate": "fs_readwrite", "shutil.copyfile": "fs_readwrite", "shutil.copytree": "fs_readwrite",
    "shutil.copymode": "fs_readwrite", "shutil.copystat": "fs_readwrite", "shutil.move": "fs_readwrite",
    "shutil.make_archive": "fs_readwrite", "shutil.unpack_archive": "fs_readwrite",
    "os.mkdir": "fs_create", "os.link": "fs_create", "os.symlink": "fs_create",
    "tempfile.mkstemp": "fs_create", "tempfile.mkdtemp": "fs_create",
    "os.remove": "fs_delete", "os.rmdir": "fs_delete", "shutil.rmtree": "fs_delete",
    "subprocess.Popen": "process", "os.system": "process", "os.startfile": "process",
    "os.posix_spawn": "process", "os.spawn": "process", "_winapi.CreateProcess": "process",
    "_thread.start_new_thread": "threading",
    "socket.connect": "network", "socket.getaddrinfo": "network", "urllib.Request": "network",
    "http.client.connect": "network",
}
TWO_PATHS = {"os.rename", "os.link", "os.symlink", "shutil.copyfile", "shutil.copytree", "shutil.copymode",
             "shutil.copystat", "shutil.move", "shutil.unpack_archive"}
granted, prompts, problems = {}, [], []
state = {"on": False}

def inside(path, folder):
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return path == folder or path.startswith(folder + os.sep)

def fspath(x):
    try:
        return os.fsdecode(os.fspath(x))
    except TypeError:
        return None

def hook(event, args):
    if not state["on"]:
        return
    if event == "open":
        if not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else "r"
        category = "fs_read" if mode and not any(c in mode for c in "wax+") else "fs_readwrite"
    else:
        category = CATEGORY.get(event)
        if category is None:
            return
    if category.startswith("fs_"):
        count = 2 if event in TWO_PATHS else 1
        targets = [p for p in (fspath(a) for a in args[:count]) if p]
        for p in targets:
            names = [n.lower() for n in re.split(r"[\\/]", os.path.abspath(p)) if n]
            if any(k in n for n in names for k in ("conf", "cert", "secret")):
                problems.append(["denied", event, p])
                raise PermissionError("Plugin attempted audited operation without permission: denied path")
            if p.lower().endswith((".py", ".pyc", ".pyd", ".so", ".dll")):
                problems.append(["code read after load", p])
        if targets and all(inside(p, data_dir) for p in targets):
            return
    elif category == "threading":
        targets = ["thread"]
    else:
        targets = [str(args[1] if event in ("subprocess.Popen", "_winapi.CreateProcess") else args[0])]
    have = granted.setdefault(category, set())
    new = [t for t in targets if t not in have]
    if targets and not new:
        return
    prompts.append([category, event, new])          # the user says Yes; OrcaSlicer remembers it
    have.update(new)

sys.addaudithook(hook)
state["on"] = True
page = page_cls()
out = os.path.join(tmp, "out")
page.save_config(json.dumps({"output_folder": out}))

def session():
    page.posted.clear()
    page.on_message({"action": "init"})
    page.on_message({"action": "analyze", "svg": badge, "options": {}})
    page.on_message({"action": "generate", "svg": badge, "options": {}, "colors": []})
    page.on_message({"action": "faces", "project": tray, "object_id": "3"})
    faces = next((m for m in page.posted if m.get("type") == "faces"), {"default": None})
    page.on_message({"action": "apply", "svg": badge, "project": tray, "object_id": "3",
                     "face_id": faces["default"], "options": {"rotation": 90}, "colors": []})
    page.on_message({"action": "plate"})
    return {"types": [m.get("type") for m in page.posted],
            "errors": [m.get("text") for m in page.posted if m.get("type") == "error"]}

first = session()
first_prompts = list(prompts)
time.sleep(1.1)                                     # a new second: a new backup name
second = session()
state["on"] = False
from orca_svg_multicor import host
mine = os.path.join(data_dir, "svg_multicor")
print(json.dumps({"first": first, "second": second, "problems": problems, "data_dir": data_dir,
                  "plugin_data": host.plugin_data_dir(), "backups": sorted(os.listdir(os.path.join(mine, "backups"))),
                  "settings_copy": os.path.isfile(os.path.join(mine, "settings.json")),
                  "first_prompts": first_prompts, "second_prompts": prompts[len(first_prompts):]}))
'''


def _tray(path):
    ring = orient(Polygon(box(-20, -15, 20, 15).exterior, [box(-18, -13, 18, 13).exterior]), 1.0)
    write_orca_project(path, [Part("walls", *extrude([ring], 8.0, 2.0), "#ff00aa", 1),
                              Part("floor", *extrude([orient(box(-20, -15, 20, 15), 1.0)], 2.0, 0.0),
                                   "#ff00aa", 1)], "tray")


def install(tmp_path, package=None):
    """The package where OrcaSlicer installs a wheel: <data>/orca_plugins/<wheel>/__whl_extracted__/."""
    extracted = tmp_path / "OrcaSlicer" / "orca_plugins" / "orca_svg_multicor-0-py3-none-any.whl" / "__whl_extracted__"
    shutil.copytree(package or os.path.join(ROOT, "src", "orca_svg_multicor"),
                    extracted / "orca_svg_multicor", ignore=shutil.ignore_patterns("__pycache__"))
    return str(extracted)


def run_twice(tmp_path, installed, python=sys.executable, env=None):
    projects = tmp_path / "projects"
    projects.mkdir()
    tray = str(projects / "tray.3mf")
    _tray(tray)
    run = subprocess.run([python, "-c", SCRIPT, ROOT, str(tmp_path), tray,
                          os.path.join(EXAMPLES, "badge.svg"), installed],
                         cwd=str(tmp_path), capture_output=True, text=True, timeout=300, env=env)
    assert run.returncode == 0, run.stderr[-3000:]
    return json.loads(run.stdout.strip().splitlines()[-1]), tray


def test_the_same_work_twice_asks_no_permission_again(tmp_path):
    started = time.monotonic()
    r, tray = run_twice(tmp_path, install(tmp_path))
    check(r, tray)
    assert time.monotonic() - started < 120


def check(r, tray):
    assert r["problems"] == []
    # installed, the plugin finds OrcaSlicer's data folder from where it lives
    assert r["plugin_data"] == os.path.join(r["data_dir"], "svg_multicor")
    assert len(r["backups"]) == 2 and r["settings_copy"]
    for s in (r["first"], r["second"]):
        assert s["errors"] == []
        assert s["types"].count("done") == 2                 # generate and apply
    # the first time: only the person's own files, read and written by name
    asked = {(cat, t) for cat, _event, targets in r["first_prompts"] for t in targets}
    assert {cat for cat, _t in asked} <= {"fs_read", "fs_readwrite", "fs_create"}, r["first_prompts"]
    for _cat, target in asked:
        assert not target.startswith(r["data_dir"]), target          # the data folder never asks
    assert ("fs_readwrite", tray) in asked                           # the project, written in place
    assert ("fs_read", tray) not in asked                            # one question for it, not two
    # the second time: nothing new to approve (the backup goes to the data folder)
    assert r["second_prompts"] == [], r["second_prompts"]


def test_a_project_is_read_with_one_question_for_reading_and_writing(tmp_path, monkeypatch):
    import builtins
    import stat

    import pytest

    from orca_svg_multicor.host import read_for_update
    p = tmp_path / "p.3mf"
    p.write_bytes(b"PK project")
    modes = []
    real_open = builtins.open

    def spy(path, mode="r", *a, **k):
        modes.append(mode)
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    assert read_for_update(str(p)) == b"PK project" and modes == ["r+b"]
    # a read-only file is still read
    modes.clear()
    p.chmod(stat.S_IREAD)
    try:
        assert read_for_update(str(p), 2) == b"PK" and modes == ["r+b", "rb"]
    finally:
        p.chmod(stat.S_IREAD | stat.S_IWRITE)

    # "No" to OrcaSlicer's question is not asked again as a plain read
    def refuse(path, mode="r", *a, **k):
        modes.append(mode)
        raise PermissionError('Plugin attempted audited operation "open" without permission')

    modes.clear()
    monkeypatch.setattr(builtins, "open", refuse)
    with pytest.raises(PermissionError):
        read_for_update(str(p))
    assert modes == ["r+b"]
