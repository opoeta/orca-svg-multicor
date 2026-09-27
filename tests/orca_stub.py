"""
A stand-in for the `orca` module OrcaSlicer provides to plugins: registration,
pages, script capabilities, host.ui and presets. Kept free of numpy and pytest
imports so a test can load the plugin the way OrcaSlicer does.
"""
import json
import types


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
