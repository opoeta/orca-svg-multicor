# -*- coding: utf-8 -*-
"""
The bridge between the web page and the engine.

The page sends {"action": ..., ...}; the service answers with one or more
{"type": ..., ...} messages through `respond`. All user-facing text is
translated here, in the language chosen in the page (or OrcaSlicer's).

Actions are split in two groups:
  QUICK  - touch the host (plate, filaments, dialogs) and must run on
           OrcaSlicer's UI thread;
  HEAVY  - geometry work, may run on a worker thread (window mode) or on the UI
           thread behind a native progress dialog (page mode).
"""

import base64
import glob
import os
import time
import traceback

from . import i18n
from ._version import __version__
from .errors import Cancelled, EngineError, UserError
from .host import Log, default_folders, plugin_data_dir
from .options import Options

QUICK = {"init", "set_language", "filaments", "plate", "pick", "upload", "inputs",
         "save_settings", "open_path", "reset_settings"}
HEAVY = {"analyze", "generate", "apply", "objects"}
UPLOAD_LIMIT = 64 * 1024 * 1024
ORIGINAL_PREVIEW_LIMIT = 4 * 1024 * 1024


def settings_defaults():
    inp, out = default_folders()
    d = {"language": "auto", "input_folder": inp, "output_folder": out,
         "open_after": False, "icon_mode": "path"}
    d.update(Options.DEFAULTS)
    return d


def _safe_name(name):
    base = os.path.basename(str(name or "")).strip()
    bad = '<>:"/\\|?*' + "".join(chr(i) for i in range(32))
    base = "".join("_" if c in bad else c for c in base).strip(" .")
    return base[:120]


class ServiceReporter:
    """Translates engine messages, feeds the page and the native dialog."""

    def __init__(self, service, progress_dialog=None):
        self.s = service
        self.dialog = progress_dialog
        self._last = (-1, None, 0.0)

    def progress(self, fraction, key=None, **params):
        pct = int(max(0, min(100, round(100 * fraction))))
        text = self.s.tr(key, **params) if key else ""
        last_pct, last_text, last_t = self._last
        now = time.monotonic()
        if pct == last_pct and text == last_text:
            return
        if text == last_text and pct - last_pct < 2 and now - last_t < 0.25 and pct < 100:
            return
        self._last = (pct, text, now)
        self.s.send({"type": "progress", "pct": pct, "text": text})
        if self.dialog is not None and not self.dialog.update(pct, text):
            raise Cancelled()

    def log(self, key, **params):
        self.s.info(self.s.tr(key, **params))

    def warn(self, key, **params):
        self.s.warn(self.s.tr(key, **params))


class Service:
    """
    host:    host.OrcaHost or host.BaseHost
    config:  (get, save) callables for the persistent settings
    respond: callable(dict) delivering a message to the page
    mode:    "page", "window" or "dev" (informational, for the page)
    """

    def __init__(self, host, config, respond, mode="page"):
        self.host = host
        self.get_config, self.save_config = config
        self.respond = respond
        self.mode = mode
        self.log_file = Log()
        self.tr = i18n.Translator(self._language_setting())

    # ------------------------------------------------------------ helpers
    def _language_setting(self):
        cfg = self.get_config()
        lang = cfg.get("language") or "auto"
        if lang == "auto":
            return self.host.language() or "en"
        return lang

    def settings(self):
        d = settings_defaults()
        d.update({k: v for k, v in self.get_config().items() if k in d})
        return d

    def send(self, msg):
        try:
            self.respond(msg)
        except Exception:
            traceback.print_exc()

    def info(self, text):
        self.log_file.write("INFO", text)
        self.send({"type": "log", "level": "info", "text": text})

    def warn(self, text):
        self.log_file.write("WARN", text)
        self.send({"type": "log", "level": "warn", "text": text})

    def error(self, action, text):
        self.log_file.write("ERROR", f"{action}: {text}")
        self.send({"type": "error", "action": action, "text": text})

    def folders(self):
        s = self.settings()
        inp = s.get("input_folder") or default_folders()[0]
        out = s.get("output_folder") or default_folders()[1]
        for f in (inp, out):
            try:
                os.makedirs(f, exist_ok=True)
            except Exception:
                pass
        return inp, out

    @staticmethod
    def is_heavy(msg):
        return (msg or {}).get("action") in HEAVY

    # ------------------------------------------------------------ dispatch
    def handle(self, msg, progress_dialog=None):
        if not isinstance(msg, dict):
            return
        action = msg.get("action")
        fn = getattr(self, "do_" + str(action), None) if action in QUICK | HEAVY else None
        if fn is None:
            self.error(action, self.tr("error.unknown_action", action=action))
            return
        try:
            if action in HEAVY:
                return fn(msg, ServiceReporter(self, progress_dialog))
            return fn(msg)
        except Exception as e:  # noqa: BLE001 - everything must reach the page
            if isinstance(e, Cancelled):
                self.send({"type": "cancelled", "action": action,
                           "text": self.tr("status.cancelled")})
                return
            if isinstance(e, UserError):
                self.error(action, self.tr(e.key, **e.params))
                return
            self.log_file.write("ERROR", traceback.format_exc())
            traceback.print_exc()
            self.error(action, self.tr("error.unexpected",
                                       detail=f"{type(e).__name__}: {e}"))

    def preflight(self, msg):
        """
        Touches the files a heavy action will use, on the calling (UI) thread,
        so OrcaSlicer's permission prompt, if any, shows up where it can.
        """
        for key in ("svg", "project"):
            p = msg.get(key)
            if p and os.path.isfile(p):
                try:
                    with open(p, "rb") as f:
                        f.read(1)
                except Exception:
                    pass
        if msg.get("action") in ("generate", "apply"):
            out = self._out_dir(msg)
            try:
                os.makedirs(out, exist_ok=True)
                probe = os.path.join(out, ".svg_multicor_probe")
                with open(probe, "w") as f:
                    f.write("ok")
                os.remove(probe)
            except Exception:
                pass

    # ------------------------------------------------------------ quick
    def _inputs(self):
        inp, _ = self.folders()
        svgs = sorted(glob.glob(os.path.join(inp, "*.svg")))
        prjs = sorted(glob.glob(os.path.join(inp, "*.3mf")))
        return {"type": "inputs", "folder": inp, "svgs": svgs, "projects": prjs}

    def _filaments(self):
        try:
            return self.host.filaments()
        except Exception as e:
            return {"filaments": [], "source": f"error: {e}"}

    def do_init(self, msg):
        s = self.settings()
        fil = self._filaments()
        self.send({
            "type": "init", "version": __version__, "mode": self.mode,
            "lang": self.tr.lang, "lang_setting": s.get("language", "auto"),
            "host_lang": self.host.language(), "languages": i18n.available(),
            "catalog": self.tr.catalog(), "settings": s,
            "filaments": fil["filaments"], "filament_source": fil["source"],
            "data_dir": plugin_data_dir(),
        })
        self.send(self._inputs())

    def do_set_language(self, msg):
        lang = str(msg.get("lang") or "auto")
        cfg = self.get_config()
        cfg["language"] = lang
        self.save_config(cfg)
        self.tr = i18n.Translator(self._language_setting())
        self.send({"type": "i18n", "lang": self.tr.lang, "lang_setting": lang,
                   "catalog": self.tr.catalog()})

    def do_filaments(self, msg):
        fil = self._filaments()
        self.send({"type": "filaments", "filaments": fil["filaments"],
                   "source": fil["source"], "silent": bool(msg.get("silent"))})

    def do_plate(self, msg):
        try:
            d = self.host.plate()
        except Exception as e:
            self.error("plate", self.tr("error.plate", detail=str(e)))
            return
        d["type"] = "plate"
        self.send(d)

    def do_inputs(self, msg):
        self.send(self._inputs())

    def do_pick(self, msg):
        kind = msg.get("kind")
        s = self.settings()
        if kind == "svg":
            args = ("file", self.tr("pick.svg"), msg.get("initial") or s["input_folder"],
                    ("*.svg",), "SVG")
        elif kind == "project":
            args = ("file", self.tr("pick.project"), msg.get("initial") or s["input_folder"],
                    ("*.3mf",), "3MF")
        elif kind in ("output", "input"):
            args = ("folder", self.tr("pick.folder"),
                    msg.get("initial") or s[kind + "_folder"], (), "")
        else:
            return
        try:
            path = self.host.pick(*args)
        except Exception as e:
            self.send({"type": "picked", "kind": kind, "path": "", "failed": True,
                       "text": self.tr("error.picker", detail=str(e)[:200])})
            return
        self.send({"type": "picked", "kind": kind, "path": path,
                   "cancelled": not path})

    def do_upload(self, msg):
        kind = msg.get("kind")
        name = _safe_name(msg.get("name"))
        data = msg.get("data") or ""
        if kind not in ("svg", "project") or not name:
            return
        ext = ".svg" if kind == "svg" else ".3mf"
        if not name.lower().endswith(ext):
            name += ext
        inp, _ = self.folders()
        dest = os.path.join(inp, name)
        if msg.get("binary"):
            if "," in data:
                data = data.split(",", 1)[1]
            raw = base64.b64decode(data)
        else:
            raw = data.encode("utf-8")
        if len(raw) > UPLOAD_LIMIT:
            self.error("upload", self.tr("error.too_big"))
            return
        with open(dest, "wb") as f:
            f.write(raw)
        self.info(self.tr("log.uploaded", name=name))
        self.send({"type": "picked", "kind": kind, "path": dest})
        self.send(self._inputs())

    def do_save_settings(self, msg):
        allowed = settings_defaults()
        cfg = self.get_config()
        for k, v in (msg.get("settings") or {}).items():
            if k in allowed and k != "language":
                cfg[k] = v
        ok = self.save_config(cfg)
        self.send({"type": "saved", "ok": bool(ok),
                   "text": self.tr("status.saved" if ok else "error.save_settings")})
        if not msg.get("quiet"):
            self.info(self.tr("status.saved" if ok else "error.save_settings"))

    def do_reset_settings(self, msg):
        lang = self.get_config().get("language", "auto")
        self.save_config({"language": lang})
        self.do_init(msg)

    def do_open_path(self, msg):
        path = msg.get("path") or ""
        if not path or not os.path.exists(path):
            self.error("open_path", self.tr("error.not_found", path=path))
            return
        try:
            self.host.open_path(path)
        except Exception as e:
            self.error("open_path", self.tr("error.open", detail=str(e)))

    # ------------------------------------------------------------ heavy
    def _options(self, msg):
        merged = self.settings()
        merged.update(msg.get("options") or {})
        return Options.from_dict(merged)

    def _out_dir(self, msg):
        out = (msg.get("output_folder") or "").strip()
        if not out:
            out = self.folders()[1]
        return out

    def _choices(self, msg):
        out = {}
        for c in msg.get("colors") or []:
            if isinstance(c, dict) and c.get("color"):
                out[str(c["color"]).lower()] = c
        return out

    def _svg(self, msg):
        p = (msg.get("svg") or "").strip()
        if not p or not os.path.isfile(p):
            raise EngineError("error.no_svg")
        return p

    def do_analyze(self, msg, rep):
        from . import engine
        svg = self._svg(msg)
        opts = self._options(msg)
        fil = msg.get("filaments")
        if fil is None:
            fil = self._filaments()["filaments"]
        rep.progress(0.0, "progress.reading")
        res = engine.analyze(svg, opts, filaments=fil, tr=self.tr, rep=rep)
        warnings = [self.tr(k, **p) for k, p in res.pop("warnings")]
        for w in warnings:
            self.warn(w)
        res["warnings"] = warnings
        res["type"] = "analysis"
        res["original"] = None
        try:
            if os.path.getsize(svg) <= ORIGINAL_PREVIEW_LIMIT:
                with open(svg, "rb") as f:
                    res["original"] = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            pass
        self.send(res)
        n, raw = len(res["colors"]), res["raw_count"]
        self.info(self.tr("log.analyzed", name=os.path.basename(svg), count=n, raw=raw))

    def do_objects(self, msg, rep):
        from . import engine
        path = (msg.get("project") or "").strip()
        rep.progress(0.1, "progress.reading_project")
        listing = engine.list_objects(path)
        objs = listing["objects"]
        rep.progress(1.0, "progress.done")
        out = []
        for o in objs:
            size = o.get("size")
            dims = "x".join(f"{v:.1f}" for v in size) + " mm" if size else "?"
            out.append({"id": o["id"], "size": size, "kind": o["kind"],
                        "parts": o["parts"],
                        "label": self.tr("objects.label", name=o["name"], size=dims,
                                         parts=o["parts"])})
        self.send({"type": "objects", "project": path, "objects": out,
                   "filaments": listing["filaments"]})
        self.info(self.tr("log.objects", count=len(out), name=os.path.basename(path)))

    def _finish(self, action, dest, report):
        bad = [r["name"] for r in report if not r["watertight"]]
        for r in report:
            self.info(self.tr("log.part", name=r["name"], color=r["color"],
                              filament=r["filament"], faces=r["faces"],
                              volume=f"{r['volume_mm3']:.1f}"))
        if bad:
            self.warn(self.tr("warn.not_watertight", names=", ".join(bad)))
        s = self.settings()
        self.send({"type": "done", "action": action, "path": dest,
                   "folder": os.path.dirname(dest), "report": report,
                   "open_after": bool(s.get("open_after")),
                   "text": self.tr("status.saved_to", path=dest)})

    def do_generate(self, msg, rep):
        from . import engine
        svg = self._svg(msg)
        opts = self._options(msg)
        out = self._out_dir(msg)
        dest, report = engine.generate(svg, out, opts, self._choices(msg),
                                       filaments=msg.get("filaments"), tr=self.tr, rep=rep)
        self._finish("generate", dest, report)

    def do_apply(self, msg, rep):
        from . import engine
        svg = self._svg(msg)
        project = (msg.get("project") or "").strip()
        obj = str(msg.get("object_id") or "").strip()
        if not obj:
            raise EngineError("error.no_object")
        opts = self._options(msg)
        out_dir = self._out_dir(msg)
        dest = engine.project_output_path(project, out_dir)
        dest, report = engine.apply_to_project(svg, project, obj, dest, opts,
                                               self._choices(msg),
                                               filaments=msg.get("filaments"),
                                               tr=self.tr, rep=rep)
        self._finish("apply", dest, report)
