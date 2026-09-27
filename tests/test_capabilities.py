"""
The OrcaSlicer glue, against a stand-in `orca` module that mirrors the host API
(registration, pages, script capabilities, host.ui, presets).
"""
import importlib
import json
import os
import shutil
import sys
import types

import pytest

from conftest import EXAMPLES


class _Result:
    def __init__(self, status, message=""):
        self.status, self.message = status, message

    @classmethod
    def success(cls, message="", data=""):
        return cls("success", message)

    @classmethod
    def skipped(cls, message=""):
        return cls("skipped", message)

    @classmethod
    def failure(cls, status, message, data=""):
        return cls("failure", message)


class _Capability:
    """What the pybind base classes give a Python subclass."""

    def __init__(self, *a, **k):
        self._config = "{}"

    def get_config(self):
        return self._config

    def save_config(self, text):
        json.loads(text)
        self._config = text
        return True


class _Progress:
    def __init__(self, cancel_at=None):
        self.values, self.closed, self.cancel_at = [], False, cancel_at

    def update(self, value, text=""):
        self.values.append((value, text))
        return not (self.cancel_at is not None and value >= self.cancel_at)

    def close(self):
        self.closed = True


class _Window:
    def __init__(self, on_message):
        self.on_message, self.posted, self.open = on_message, [], True

    def post(self, payload):
        self.posted.append(payload)

    def is_open(self):
        return self.open

    def close(self):
        self.open = False


def make_orca(tmp_path):
    orca = types.ModuleType("orca")
    orca.registered = []
    orca.plugin_class = None

    def plugin(cls):
        orca.plugin_class = cls
        return cls

    orca.plugin = plugin
    orca.base = type("base", (), {})
    orca.register_capability = orca.registered.append
    orca.PluginType = types.SimpleNamespace(Pages="Pages", Script="Script")
    orca.PluginResult = types.SimpleNamespace(RecoverableError="RecoverableError")
    orca.ExecutionResult = _Result

    class PagesBase(_Capability):
        def __init__(self, *a, **k):
            super().__init__()
            self.posted = []

        def post_message(self, payload):
            self.posted.append(payload)

    orca.pages = types.SimpleNamespace(PagesPluginCapabilityBase=PagesBase)
    orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=_Capability)

    ui = types.SimpleNamespace(PD_APP_MODAL=2, PD_AUTO_HIDE=4, PD_CAN_ABORT=1,
                               WINDOW_MODELESS=0, WINDOW_MODAL=1)
    ui.messages, ui.dialogs, ui.windows = [], [], []

    def message(text, title="OrcaSlicer", buttons="ok", icon="info"):
        ui.messages.append((title, text, icon))
        return "ok"

    def create_progress_dialog(title, message, maximum=100, style=0):
        d = _Progress()
        ui.dialogs.append(d)
        return d

    def create_window(html, title="OrcaSlicer", width=820, height=600, on_message=None,
                      on_close=None, style=0, on_submit=None):
        w = _Window(on_message)
        w.html = html
        ui.windows.append(w)
        return w

    ui.message, ui.create_progress_dialog, ui.create_window = message, create_progress_dialog, create_window

    bundle = types.SimpleNamespace(
        current_filament_preset_names=lambda: ["White PLA", "Black PLA"],
        current_filament_presets=lambda: [],
        full_config_value=lambda key: "#FFFFFF;#101010" if key == "filament_colour" else None)
    orca.host = types.SimpleNamespace(
        ui=ui, app_language=lambda: "pt_BR", preset_bundle=lambda: bundle,
        model=lambda: types.SimpleNamespace(objects=lambda: []),
        plater=lambda: types.SimpleNamespace(is_project_dirty=lambda: False))
    return orca


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    orca = make_orca(tmp_path)
    monkeypatch.setitem(sys.modules, "orca", orca)
    monkeypatch.setenv("APPDATA", str(tmp_path))          # data folder goes to tmp
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for name in [m for m in sys.modules if m.startswith("orca_svg_multicor")]:
        monkeypatch.delitem(sys.modules, name)
    pkg = importlib.import_module("orca_svg_multicor")
    orca.plugin_class().register_capabilities()
    caps = {c.__name__: c for c in orca.registered}
    yield orca, caps, pkg
    for name in [m for m in sys.modules if m.startswith("orca_svg_multicor")]:
        sys.modules.pop(name, None)


def configure(cap, tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    cap.save_config(json.dumps({"input_folder": str(inp), "output_folder": str(out)}))
    return inp, out


def test_registration(plugin):
    orca, caps, pkg = plugin
    # with plugin pages available, the window is not offered: one page, one script
    assert set(caps) == {"PanelPage", "BatchConvert"}
    names = {c().get_name() for c in caps.values()}
    assert names == {"SVG Multicolor", "SVG Multicolor - batch"}
    assert isinstance(caps["PanelPage"]().get_default_config(), dict)


def test_config_tab_pages(plugin):
    orca, caps, _ = plugin
    page = caps["PanelPage"]()
    assert page.has_config_ui() is True
    html = page.get_config_ui()
    assert "window.SVGM_CFG" in html and "/*BOOT*/" not in html
    assert '"lang": "pt_BR"' in html and "## " in html        # translated, with the changelog
    batch = caps["BatchConvert"]()
    assert batch.get_default_config() == {}
    assert "SVG Multicolor" in batch.get_config_ui()


def test_batch_uses_the_page_settings(plugin, tmp_path):
    orca, caps, _ = plugin
    page = caps["PanelPage"]()
    batch = caps["BatchConvert"]()
    page.save_config(json.dumps({"size_mm": 42}))
    assert batch._store()[0]()["size_mm"] == 42


def test_page_ui_icon_and_messages(plugin, tmp_path):
    orca, caps, _ = plugin
    page = caps["PanelPage"]()
    configure(page, tmp_path)
    html = page.get_ui()
    assert '"lang": "pt_BR"' in html                        # follows OrcaSlicer's language
    icon = page.get_icon()
    assert os.path.isfile(icon)
    assert os.path.isfile(icon[:-4] + ".svg")      # OrcaSlicer tries <name>.svg first
    page.on_message({"action": "init"})
    init = next(m for m in page.posted if m["type"] == "init")
    assert [f["color"] for f in init["filaments"]] == ["#ffffff", "#101010"]
    badge = os.path.join(EXAMPLES, "badge.svg")
    page.on_message(json.dumps({"action": "analyze", "svg": badge}))   # JSON strings too
    assert any(m["type"] == "analysis" for m in page.posted)
    page.on_message({"action": "generate", "svg": badge, "options": {}, "colors": [],
                     "reopen": True})
    done = next(m for m in page.posted if m["type"] == "done")
    assert os.path.isfile(done["path"])
    assert done["open_after"] is True        # a new object goes back to OrcaSlicer
    dlg = orca.host.ui.dialogs[-1]                         # generate runs behind the native dialog
    assert dlg.values and dlg.closed


def test_page_generate_can_be_cancelled(plugin, tmp_path):
    orca, caps, _ = plugin
    page = caps["PanelPage"]()
    configure(page, tmp_path)
    orca.host.ui.create_progress_dialog = lambda *a, **k: _Progress(cancel_at=0)
    page.on_message({"action": "generate", "svg": os.path.join(EXAMPLES, "badge.svg"),
                     "options": {}, "colors": []})
    assert page.posted[-1]["type"] == "cancelled"


def test_window_runs_heavy_work_in_a_thread(plugin, tmp_path):
    orca, caps, pkg = plugin
    win_cap = pkg._capabilities.PanelWindow()        # only registered without plugin pages
    configure(win_cap, tmp_path)
    assert win_cap.execute().status == "success"
    win = orca.host.ui.windows[-1]
    assert "SVGM_BOOT" in win.html
    win_cap.on_message({"action": "init"})
    assert win.posted[0]["type"] == "init"
    win_cap.on_message({"action": "analyze", "svg": os.path.join(EXAMPLES, "badge.svg")})
    win_cap._worker.join(60)
    assert any(m["type"] == "analysis" for m in win.posted)
    assert win_cap.execute().message == "already open"


def test_batch_converts_the_input_folder(plugin, tmp_path):
    orca, caps, _ = plugin
    page = caps["PanelPage"]()
    batch = caps["BatchConvert"]()
    inp, out = configure(page, tmp_path)
    shutil.copy(os.path.join(EXAMPLES, "badge.svg"), inp / "a.svg")
    (inp / "broken.svg").write_text("<svg", encoding="utf-8")
    result = batch.execute()
    assert result.status == "success"
    assert (out / "a_multicolor.3mf").is_file() and (out / "batch_report.txt").is_file()
    assert len(orca.host.ui.messages) == 1                   # one summary, not one box per file
    assert "1" in orca.host.ui.messages[0][1]


def test_batch_with_empty_folder_is_skipped(plugin, tmp_path):
    orca, caps, _ = plugin
    page = caps["PanelPage"]()
    batch = caps["BatchConvert"]()
    configure(page, tmp_path)
    assert batch.execute().status == "skipped"


def test_light_modules_do_not_import_numpy_or_shapely():
    import subprocess
    code = ("import sys; sys.path.insert(0, 'src');"
            "import orca_svg_multicor.service, orca_svg_multicor.panel, orca_svg_multicor.host;"
            "heavy = [m for m in ('numpy', 'shapely', 'svgelements') if m in sys.modules];"
            "print(heavy); sys.exit(1 if heavy else 0)")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_run_captured_opens_no_file_descriptor(tmp_path):
    """Pipes are opened by descriptor, which OrcaSlicer asks about without a target."""
    from orca_svg_multicor.host import run_captured
    seen = []

    def hook(event, args):
        if event == "open" and args and not isinstance(args[0], str):
            seen.append(args[0])

    sys.addaudithook(hook)       # stays installed; it only records
    out = run_captured([sys.executable, "-c", "print('picked')"], folder=str(tmp_path))
    before = len(seen)
    assert out.strip() == "picked"
    assert before == 0, seen
    assert not list(tmp_path.iterdir())      # temporary files removed


# ---------------------------------------------------------------- OrcaSlicer's audit rules
def test_nothing_shipped_or_written_trips_the_denied_words(tmp_path):
    """OrcaSlicer refuses plugins any path with "conf", "cert" or "secret" in a name."""
    from orca_svg_multicor.host import DENIED_WORDS, Log, default_folders, denied_name
    pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "src", "orca_svg_multicor")
    for _root, dirs, files in os.walk(pkg):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in dirs + files:
            assert not any(w in name.lower() for w in DENIED_WORDS), name
    for folder in default_folders(str(tmp_path)):
        assert not any(w in os.path.basename(folder).lower() for w in DENIED_WORDS), folder
    assert not any(w in os.path.basename(Log(str(tmp_path)).path) for w in DENIED_WORDS)
    assert denied_name(r"C:\Users\me\Conferencia\logo.svg") == "Conferencia"
    assert denied_name("/home/me/logos/badge.svg") is None


def test_service_explains_blocked_paths(tmp_path):
    from orca_svg_multicor.host import BaseHost
    from orca_svg_multicor.service import Service
    out = []
    svc = Service(BaseHost(), (lambda: {"language": "pt_BR"}, lambda c: True), out.append)
    folder = tmp_path / "certificados"
    folder.mkdir()
    svg = folder / "a.svg"
    shutil.copy(os.path.join(EXAMPLES, "badge.svg"), svg)
    svc.handle({"action": "analyze", "svg": str(svg)})
    err = out[-1]
    assert err["type"] == "error" and "certificados" in err["text"]
    assert err["text"] == svc.tr("error.denied_name", path=str(svg))


def test_permission_errors_get_a_clear_message(monkeypatch):
    from orca_svg_multicor import engine
    from orca_svg_multicor.host import BaseHost
    from orca_svg_multicor.service import Service
    out = []
    svc = Service(BaseHost(), (lambda: {}, lambda c: True), out.append)

    def blocked(*a, **k):
        raise PermissionError("Plugin attempted an audited operation without permission")

    monkeypatch.setattr(engine, "analyze", blocked)
    svc.handle({"action": "analyze", "svg": os.path.join(EXAMPLES, "badge.svg")})
    assert out[-1]["type"] == "error"
    assert out[-1]["text"].startswith("OrcaSlicer blocked the plugin")


def test_open_path_hands_3mf_to_orca_window_or_falls_back(monkeypatch, tmp_path):
    import types
    from orca_svg_multicor import host as H
    f = tmp_path / "result.3mf"
    f.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(H, "open_in_orca", lambda p: calls.append(("exe", p)))
    monkeypatch.setattr(H, "send_to_window", lambda hwnd, p: calls.append(("ipc", hwnd, p)))
    h = H.OrcaHost(types.SimpleNamespace(host=None))
    # outside OrcaSlicer there is no OrcaSlicer window in this process
    assert H.find_orca_window() is None
    h.open_path(str(f))
    assert calls == [("exe", str(f))]
    # inside OrcaSlicer: the window gets the file, from a thread, without a new process
    calls.clear()
    monkeypatch.setattr(H, "find_orca_window", lambda: 1234)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    h.open_path(str(f))
    for t in list(__import__("threading").enumerate()):
        if t.name == "svg-multicolor-open":
            t.join(5)
    assert calls == [("ipc", 1234, str(f))]
