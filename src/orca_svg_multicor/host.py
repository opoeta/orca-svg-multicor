# -*- coding: utf-8 -*-
"""
Everything that talks to the outside world: OrcaSlicer's host API, native file
pickers, the data folder and the log file.

`OrcaHost` wraps `orca.host`; `BaseHost` holds what does not depend on
OrcaSlicer, and is what the tests and the dev server use.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading

from .colors import normalize_hex

APP_DIR_NAME = "OrcaSlicer"
PLUGIN_DIR_NAME = "svg_multicor"
LOG_MAX_BYTES = 1024 * 1024
PICKER_TIMEOUT = 600


def orca_data_dir():
    """OrcaSlicer's data folder (plugins may write there without a prompt)."""
    try:
        if sys.platform == "win32":
            root = os.environ.get("APPDATA") or os.path.expanduser("~")
            base = os.path.join(root, APP_DIR_NAME)
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/" + APP_DIR_NAME)
        else:
            base = os.path.join(os.environ.get("XDG_CONFIG_HOME")
                                or os.path.expanduser("~/.config"), APP_DIR_NAME)
        if os.path.isdir(base):
            return base
    except Exception:
        pass
    return os.path.expanduser("~")


def plugin_data_dir():
    return os.path.join(orca_data_dir(), PLUGIN_DIR_NAME)


def default_folders(base=None):
    """
    (input, output) folders. Version 2 used Portuguese names; if they exist
    they are kept so nobody loses track of their files.
    """
    base = base or plugin_data_dir()
    old_in, old_out = os.path.join(base, "svg_entrada"), os.path.join(base, "3mf_saida")
    if os.path.isdir(old_in) or os.path.isdir(old_out):
        return old_in, old_out
    return os.path.join(base, "svg_input"), os.path.join(base, "3mf_output")


class Log:
    """Appends to <data>/svg_multicor/plugin.log, rotating at 1 MB."""

    def __init__(self, folder=None):
        self.path = os.path.join(folder or plugin_data_dir(), "plugin.log")
        self._lock = threading.Lock()

    def write(self, level, text):
        line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} [{level}] {text}\n"
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                if os.path.isfile(self.path) and os.path.getsize(self.path) > LOG_MAX_BYTES:
                    old = self.path + ".1"
                    if os.path.exists(old):
                        os.remove(old)
                    os.replace(self.path, old)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass


# ----------------------------------------------------------------------------
# native pickers, run as separate processes: OrcaSlicer forbids GUI toolkits
# inside its own process, but asking the system is fine (the audit hook asks
# the user once, then remembers the answer)
# ----------------------------------------------------------------------------
_PS_PICK = r"""
$ErrorActionPreference = 'Stop'
$result = ''
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false; Width = 1; Height = 1; StartPosition = 'CenterScreen'}
$owner.Show(); $owner.Hide()
try {
  if ($env:SVGM_KIND -eq 'folder') {
    $d = New-Object System.Windows.Forms.FolderBrowserDialog
    $d.Description = $env:SVGM_TITLE
    $d.ShowNewFolderButton = $true
    if ($env:SVGM_INITIAL -and (Test-Path -LiteralPath $env:SVGM_INITIAL)) { $d.SelectedPath = $env:SVGM_INITIAL }
    if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $result = $d.SelectedPath }
  } else {
    $d = New-Object System.Windows.Forms.OpenFileDialog
    $d.Title = $env:SVGM_TITLE
    $d.Filter = $env:SVGM_FILTER
    $d.CheckFileExists = $true
    if ($env:SVGM_INITIAL -and (Test-Path -LiteralPath $env:SVGM_INITIAL -PathType Container)) { $d.InitialDirectory = $env:SVGM_INITIAL }
    if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $result = $d.FileName }
  }
} finally { $owner.Dispose() }
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::Out.Write($result)
"""


def _picker_command(kind, title, initial, patterns, label):
    """Command line for the platform's picker, or None."""
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-NonInteractive", "-STA",
                "-ExecutionPolicy", "Bypass", "-Command", _PS_PICK]
    if sys.platform == "darwin":
        if kind == "folder":
            script = f'POSIX path of (choose folder with prompt "{title}")'
        else:
            types = ", ".join(f'"{p.lstrip("*.")}"' for p in patterns)
            script = f'POSIX path of (choose file with prompt "{title}" of type {{{types}}})'
        return ["osascript", "-e", "try", "-e", script, "-e", "on error",
                "-e", 'return ""', "-e", "end try"]
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", f"--title={title}"]
        if kind == "folder":
            cmd.append("--directory")
        else:
            cmd.append(f"--file-filter={label} | {' '.join(patterns)}")
        if initial:
            cmd.append(f"--filename={initial.rstrip('/')}/")
        return cmd
    if shutil.which("kdialog"):
        if kind == "folder":
            return ["kdialog", "--getexistingdirectory", initial or os.path.expanduser("~")]
        return ["kdialog", "--getopenfilename", initial or os.path.expanduser("~"),
                " ".join(patterns)]
    return None


def native_pick(kind, title, initial="", patterns=(), label=""):
    """
    Opens the system picker. Returns the chosen path, "" when cancelled.
    Raises RuntimeError when no picker is available.
    """
    cmd = _picker_command(kind, title, initial, patterns, label)
    if cmd is None:
        raise RuntimeError("no native picker (install zenity or kdialog)")
    env = dict(os.environ)
    env["SVGM_KIND"] = kind
    env["SVGM_TITLE"] = title
    env["SVGM_INITIAL"] = initial or ""
    env["SVGM_FILTER"] = f"{label} ({';'.join(patterns)})|{';'.join(patterns)}"
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    r = subprocess.run(cmd, capture_output=True, env=env, timeout=PICKER_TIMEOUT, **kw)
    out = (r.stdout or b"").decode("utf-8", "replace").strip().strip('"')
    if not out:
        return ""
    if kind == "folder" and not os.path.isdir(out):
        raise RuntimeError(f"not a folder: {out[:200]}")
    if kind != "folder" and not os.path.isfile(out):
        raise RuntimeError(f"not a file: {out[:200]}")
    return out


def open_with_system(path):
    """Opens a file (OrcaSlicer is associated with .3mf) or a folder."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


# ----------------------------------------------------------------------------
# hosts
# ----------------------------------------------------------------------------
class BaseHost:
    """Host without OrcaSlicer: no filaments, no plate, pickers still work."""

    name = "base"
    native_ui = False

    def language(self):
        return None

    def filaments(self):
        return {"filaments": [], "source": "none"}

    def plate(self):
        return {"objects": [], "dirty": None, "project": ""}

    def pick(self, kind, title, initial="", patterns=(), label=""):
        return native_pick(kind, title, initial, patterns, label)

    def open_path(self, path):
        open_with_system(path)

    def message(self, text, title, icon="info"):
        print(f"[svg multicolor] {title}: {text}")

    def progress(self, title, message=""):
        return NullProgress()


class NullProgress:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def update(self, value, text=""):
        return True

    def close(self):
        pass


def _member(obj, name, default=None):
    """Reads a host member that may be a property or a method."""
    try:
        v = getattr(obj, name)
    except Exception:
        return default
    if callable(v):
        try:
            v = v()
        except Exception:
            return default
    return v


_RE_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _hexes(value):
    """#rrggbb values inside a config value that may be a str or a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_hexes(v))
        return out
    return [normalize_hex(h) for h in _RE_HEX.findall(str(value))]


def _try_calls(fn, attempts):
    """Calls fn with several argument sets until one is accepted."""
    err = None
    for args, kwargs in attempts:
        try:
            return fn(*args, **kwargs), None
        except TypeError as e:
            err = e
        except Exception as e:
            return None, e
    return None, err


class OrcaHost(BaseHost):
    """The real thing, inside OrcaSlicer."""

    name = "orca"

    def __init__(self, orca, native_ui=True):
        self.orca = orca
        self.native_ui = native_ui
        self.ui = getattr(getattr(orca, "host", None), "ui", None)

    def language(self):
        fn = getattr(getattr(self.orca, "host", None), "app_language", None)
        if fn is None:
            return None
        try:
            return str(fn() if callable(fn) else fn) or None
        except Exception:
            return None

    def filaments(self):
        """Filaments loaded now: number, preset name and color. Read only."""
        pb = self.orca.host.preset_bundle()
        names = [str(x) for x in (_member(pb, "current_filament_preset_names") or [])]
        presets = list(_member(pb, "current_filament_presets") or [])
        if not names and presets:
            names = [str(_member(p, "name", "")) for p in presets]
        colors, source = [], "none"
        for key in ("filament_colour", "filament_color", "default_filament_colour"):
            try:
                colors = _hexes(pb.full_config_value(key))
            except Exception:
                colors = []
            if colors:
                source = f"bundle:{key}"
                break
        if not colors and presets:
            per = []
            for pr in presets:
                found = ""
                for key in ("filament_colour", "filament_color", "default_filament_colour"):
                    try:
                        h = _hexes(pr.config_value(key))
                    except Exception:
                        h = []
                    if h:
                        found = h[0]
                        break
                per.append(found)
            if any(per):
                colors, source = per, "preset"
        total = max(len(names), len(colors))
        out = [{"n": i + 1,
                "name": names[i] if i < len(names) else f"#{i + 1}",
                "color": colors[i] if i < len(colors) and colors[i] else ""}
               for i in range(total)]
        return {"filaments": out, "source": source}

    def plate(self):
        """Objects on the plate now and the project they came from. Read only."""
        model = self.orca.host.model()
        items = []
        for i, obj in enumerate(_member(model, "objects", []) or []):
            bb = _member(obj, "bounding_box")
            size = None
            if bb is not None and _member(bb, "defined", True):
                s = _member(bb, "size")
                if s:
                    size = [float(s[0]), float(s[1]), float(s[2])]
            items.append({
                "index": i,
                "name": str(_member(obj, "name", f"#{i}")),
                "size": size,
                "parts": int(_member(obj, "volume_count", 0) or 0),
                "file": str(_member(obj, "input_file", "") or ""),
                "painted": bool(_member(obj, "is_mm_painted", False)),
            })
        dirty = None
        try:
            dirty = bool(_member(self.orca.host.plater(), "is_project_dirty"))
        except Exception:
            pass
        project = ""
        for it in items:
            f = it["file"]
            if f.lower().endswith(".3mf") and os.path.isfile(f):
                project = f
                break
        return {"objects": items, "dirty": dirty, "project": project}

    def message(self, text, title, icon="info"):
        fn = getattr(self.ui, "message", None)
        if fn is None or not self.native_ui:
            return super().message(text, title, icon)
        _try_calls(fn, [((), {"text": text, "title": title, "buttons": "ok", "icon": icon}),
                        ((text,), {"title": title}), ((text,), {})])

    def progress(self, title, message=""):
        fn = getattr(self.ui, "create_progress_dialog", None)
        if fn is None or not self.native_ui:
            return NullProgress()
        style = (getattr(self.ui, "PD_APP_MODAL", 2) | getattr(self.ui, "PD_AUTO_HIDE", 4)
                 | getattr(self.ui, "PD_CAN_ABORT", 1))
        dlg, _err = _try_calls(fn, [((title, message or title), {"maximum": 100, "style": style}),
                                    ((title, message or title), {"maximum": 100}),
                                    ((title, message or title), {})])
        if dlg is None or not hasattr(dlg, "update"):
            return NullProgress()
        return _ProgressWrap(dlg)

    def open_path(self, path):
        open_with_system(path)


class _ProgressWrap:
    def __init__(self, dlg):
        self.dlg = dlg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False

    def update(self, value, text=""):
        try:
            return self.dlg.update(int(value), str(text)[:120]) is not False
        except Exception:
            return True

    def close(self):
        try:
            self.dlg.close()
        except Exception:
            pass


def config_store_for(capability, defaults):
    """get/save helpers around a capability's JSON config."""

    def get():
        cfg = dict(defaults)
        try:
            stored = json.loads(capability.get_config() or "{}")
            if isinstance(stored, dict):
                cfg.update(stored)
        except Exception:
            pass
        return cfg

    def save(cfg):
        try:
            return bool(capability.save_config(json.dumps(cfg)))
        except Exception:
            return False

    return get, save
