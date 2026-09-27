# -*- coding: utf-8 -*-
"""
OrcaSlicer capabilities. Imported only inside OrcaSlicer.

  SVG Multicolor                 (Pages)  the panel as a page inside OrcaSlicer
  SVG Multicolor - window        (Script) the same panel in its own window
  SVG Multicolor - batch         (Script) converts every SVG of the input folder

Capability names are identifiers: OrcaSlicer keys their config and on/off
state by name, so they are NOT translated.

Threading, as the host API documents it:
  - Pages.on_message runs on the UI thread and has no documented thread-safe
    way to answer later, so the work runs right there, behind OrcaSlicer's
    native (cancellable) progress dialog.
  - UiWindow.post() may be called from any thread, so the window capability
    runs heavy work on a worker thread and keeps OrcaSlicer responsive.
"""

import base64
import json
import os
import threading
import traceback

import orca

from . import i18n
from .host import OrcaHost, config_store_for
from .panel import build_html
from .service import Service, settings_defaults

NAME_PAGE = "SVG Multicolor"
NAME_WINDOW = "SVG Multicolor - window"
NAME_BATCH = "SVG Multicolor - batch"
# OrcaSlicer drops the extension and tries <name>.svg before <name>.png, so the
# crisp icon.svg next to icon.png is the one shown on the page tab.
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
ICON_SVG_PATH = ICON_PATH[:-4] + ".svg"
_PLUGIN_TYPE = getattr(orca, "PluginType", None)


def _type(name):
    return getattr(_PLUGIN_TYPE, name, None) if _PLUGIN_TYPE is not None else None


def _normalize(*a, **k):
    """on_message data may arrive as a dict, a JSON string or inside kwargs."""
    for c in list(a) + list(k.values()):
        if isinstance(c, dict):
            return c
        if isinstance(c, (str, bytes)):
            try:
                d = json.loads(c)
            except Exception:
                continue
            if isinstance(d, dict):
                return d
    return {}


def _deliver(fn, payload):
    """Sends a payload to the page, as a dict first and as JSON if refused."""
    for attempt in (payload, json.dumps(payload)):
        try:
            fn(attempt)
            return True
        except Exception:
            continue
    print("[svg multicolor] could not answer the page:", str(payload)[:160])
    return False


def _try_calls(fn, attempts):
    err = None
    for args, kwargs in attempts:
        try:
            return fn(*args, **kwargs), None
        except TypeError as e:
            err = e
        except Exception as e:
            return None, e
    return None, err


class _Common:
    """Config shared by every capability (each keeps its own copy)."""

    def get_default_config(self):
        return settings_defaults()

    def _store(self):
        return config_store_for(self, settings_defaults())

    def _language(self, host):
        lang = self._store()[0]().get("language") or "auto"
        return host.language() if lang == "auto" else lang

    def _icon(self):
        mode = "path"
        try:
            mode = self._store()[0]().get("icon_mode") or "path"
        except Exception:
            pass
        if mode == "svg":
            try:
                with open(ICON_SVG_PATH, encoding="utf-8") as f:
                    return f.read()
            except OSError:
                return ""
        if mode in ("data_uri", "base64"):
            try:
                with open(ICON_PATH, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
            except OSError:
                return ""
            return b64 if mode == "base64" else "data:image/png;base64," + b64
        return ICON_PATH


# ----------------------------------------------------------------------------
# page inside OrcaSlicer
# ----------------------------------------------------------------------------
_PagesBase = getattr(getattr(orca, "pages", None), "PagesPluginCapabilityBase", None)

if _PagesBase is not None:

    class PanelPage(_Common, _PagesBase):

        def get_name(self):
            return NAME_PAGE

        def get_type(self):
            return _type("Pages")

        def get_icon(self):
            return self._icon()

        def get_ui(self):
            host = OrcaHost(orca)
            return build_html(self._language(host), mode="page")

        def _service(self):
            svc = getattr(self, "_svc", None)
            if svc is None:
                svc = Service(OrcaHost(orca), self._store(),
                              lambda p: _deliver(self.post_message, p), mode="page")
                self._svc = svc
            return svc

        def on_message(self, *a, **k):
            msg = _normalize(*a, **k)
            if not msg:
                return None
            svc = self._service()
            if not svc.is_heavy(msg):
                svc.handle(msg)
                return None
            svc.preflight(msg)
            big = msg.get("action") in ("generate", "apply") or _is_big(msg.get("svg"))
            if big:
                with svc.host.progress(NAME_PAGE, svc.tr("progress.starting")) as dlg:
                    svc.handle(msg, progress_dialog=dlg)
            else:
                svc.handle(msg)
            return None
else:
    PanelPage = None


def _is_big(path, limit=2 * 1024 * 1024):
    try:
        return bool(path) and os.path.getsize(path) > limit
    except OSError:
        return False


# ----------------------------------------------------------------------------
# the same panel in a window
# ----------------------------------------------------------------------------
class PanelWindow(_Common, orca.script.ScriptPluginCapabilityBase):

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.window = None
        self._svc = None
        self._worker = None

    def get_name(self):
        return NAME_WINDOW

    def get_type(self):
        return _type("Script")

    def on_close(self, *a, **k):
        self.window = None
        return None

    def _post(self, payload):
        win = self.window
        if win is None:
            return
        try:
            if win.is_open():
                _deliver(win.post, payload)
        except Exception:
            pass

    def on_message(self, *a, **k):
        msg = _normalize(*a, **k)
        if not msg or self.window is None:
            return None
        if msg.get("action") == "close":
            try:
                self.window.close()
            except Exception:
                pass
            return None
        svc = self._svc
        if not svc.is_heavy(msg):
            svc.handle(msg)          # UI thread: host handles are valid here
            return None
        if self._worker is not None and self._worker.is_alive():
            svc.error(msg.get("action"), svc.tr("error.busy"))
            return None
        svc.preflight(msg)           # permission prompts belong to the UI thread

        def work():
            try:
                svc.handle(msg)
            except BaseException as e:  # noqa: BLE001 - not even MemoryError goes silent
                traceback.print_exc()
                svc.error(msg.get("action"), f"{type(e).__name__}: {e}")

        self._worker = threading.Thread(target=work, name="svg-multicolor", daemon=True)
        self._worker.start()
        return None

    def execute(self, *a, **k):
        try:
            if self.window is not None:
                try:
                    if self.window.is_open():
                        return orca.ExecutionResult.success("already open")
                except Exception:
                    pass
            host = OrcaHost(orca, native_ui=False)
            self._svc = Service(host, self._store(), self._post, mode="window")
            ui = getattr(orca.host, "ui", None)
            fn = getattr(ui, "create_window", None)
            if fn is None:
                OrcaHost(orca).message(self._svc.tr("error.no_window"), NAME_WINDOW, "warning")
                return orca.ExecutionResult.skipped("create_window unavailable")
            html = build_html(self._svc.tr.lang, mode="window")
            full = {"html": html, "title": NAME_WINDOW, "width": 1200, "height": 820,
                    "on_message": self.on_message, "on_close": self.on_close,
                    "on_submit": self.on_message,
                    "style": getattr(ui, "WINDOW_MODELESS", 0)}
            reduced = {k2: v for k2, v in full.items() if k2 not in ("style", "on_submit")}
            win, err = _try_calls(fn, [((), full), ((), reduced),
                                       ((), {"html": html, "title": NAME_WINDOW})])
            if win is None:
                print(f"[svg multicolor] create_window failed: {err}")
                return orca.ExecutionResult.skipped(f"create_window failed: {err}")
            self.window = win
            return orca.ExecutionResult.success("")
        except Exception as e:
            traceback.print_exc()
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError,
                                                 f"{type(e).__name__}: {e}")


# ----------------------------------------------------------------------------
# batch: every SVG of the input folder, no interface
# ----------------------------------------------------------------------------
class BatchConvert(_Common, orca.script.ScriptPluginCapabilityBase):

    def get_name(self):
        return NAME_BATCH

    def get_type(self):
        return _type("Script")

    def execute(self, *a, **k):
        import glob
        from . import engine
        from .errors import Cancelled, UserError
        from .options import Options

        host = OrcaHost(orca)
        get, _save = self._store()
        cfg = get()
        tr = i18n.Translator(self._language(host))
        inp = cfg.get("input_folder") or settings_defaults()["input_folder"]
        out = cfg.get("output_folder") or settings_defaults()["output_folder"]
        try:
            files = sorted(glob.glob(os.path.join(inp, "*.svg")))
            if not files:
                host.message(tr("batch.empty", folder=inp), NAME_BATCH, "warning")
                return orca.ExecutionResult.skipped("empty input folder")
            try:
                fil = host.filaments()["filaments"]
            except Exception:
                fil = []
            opts = Options.from_dict(cfg)
            lines, ok, failed = [], 0, 0
            with host.progress(NAME_BATCH, tr("progress.starting")) as dlg:

                class Rep(engine.Reporter):
                    def __init__(self, k, n, name):
                        super().__init__()
                        self.k, self.n, self.name = k, n, name

                    def progress(self, fraction, key=None, **params):
                        pct = int(100 * (self.k + fraction) / self.n)
                        if not dlg.update(pct, tr("batch.file", name=self.name,
                                                  k=self.k + 1, n=self.n)):
                            raise Cancelled()

                for kk, svg in enumerate(files):
                    name = os.path.basename(svg)
                    try:
                        dest, rep = engine.generate(svg, out, opts, filaments=fil, tr=tr,
                                                    rep=Rep(kk, len(files), name))
                        ok += 1
                        lines.append(tr("batch.ok", name=name, path=dest, parts=len(rep)))
                    except Cancelled:
                        lines.append(tr("status.cancelled"))
                        break
                    except UserError as e:
                        failed += 1
                        lines.append(tr("batch.failed", name=name,
                                        detail=tr(e.key, **e.params)))
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        traceback.print_exc()
                        lines.append(tr("batch.failed", name=name, detail=f"{type(e).__name__}: {e}"))
            summary = tr("batch.summary", ok=ok, failed=failed, folder=out)
            text = summary + "\n\n" + "\n".join(lines)
            try:
                with open(os.path.join(out, "batch_report.txt"), "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            except OSError:
                pass
            host.message(text[:3000], NAME_BATCH, "warning" if failed else "info")
            return orca.ExecutionResult.success(summary)
        except Exception as e:
            traceback.print_exc()
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError,
                                                f"{type(e).__name__}: {e}")


def register_all(orca_module):
    if PanelPage is not None:
        orca_module.register_capability(PanelPage)
    orca_module.register_capability(PanelWindow)
    orca_module.register_capability(BatchConvert)
