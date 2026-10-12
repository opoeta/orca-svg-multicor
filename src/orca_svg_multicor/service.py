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
from .deps import load_engine
from .errors import Cancelled, EngineError, UserError
from .host import (Log, default_folders, denied_name, plugin_data_dir, read_for_update,
                   read_settings_copy, user_folders, write_settings_copy)
from .options import Options

QUICK = {"init", "set_language", "filaments", "plate", "pick", "upload", "inputs",
         "save_settings", "open_path", "reset_settings", "changelog", "describe_colors"}
HEAVY = {"analyze", "generate", "apply", "objects", "faces", "face_context", "paint_fill"}
UPLOAD_LIMIT = 64 * 1024 * 1024
ORIGINAL_PREVIEW_LIMIT = 4 * 1024 * 1024


SETTINGS_REV = 3
BACKUPS_KEPT = 20          # copies of projects replaced by "apply" (apply_output "project")


def settings_defaults():
    inp, out = default_folders()
    d = {"language": "auto", "input_folder": inp, "output_folder": out,
         "target": "plate", "open_after": False, "icon_mode": "path",
         "ask_colors": True,
         "apply_output": "project"}   # project (replaced, after a backup) | copy (<name>_svg.3mf)
    d.update(Options.DEFAULTS)
    return d


def copy_file(src, dst, chunk=1 << 20):
    """
    Copies with one open() per file instead of shutil.copyfile. OrcaSlicer
    judges shutil.copyfile's source and destination together: a backup with
    a new name each time made it ask permission at every apply. Each open()
    is judged alone, and the plugin's data folder needs no permission.
    """
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            block = fi.read(chunk)
            if not block:
                break
            fo.write(block)


def _paint_ops(msg):
    """The page's paint operations (brush strokes, filled areas), as a list of dicts."""
    ops = msg.get("paint")
    if not isinstance(ops, list):
        return []
    return [op for op in ops[:2000] if isinstance(op, dict)]


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
        self.get_config, save = config

        def save_config(cfg):
            ok = save(cfg)
            if ok:
                write_settings_copy(cfg)
            return ok

        self.save_config = save_config
        self.respond = respond
        self.mode = mode
        self.log_file = Log()
        self._listing_cache = {}
        self._faces_cache = {}
        self._migrate()
        self.tr = i18n.Translator(self._language_setting())

    # ------------------------------------------------------------ helpers
    def _migrate(self):
        """One-time updates of saved settings, marked by settings_rev."""
        try:
            cfg = self.get_config()
            if "settings_rev" not in cfg:
                # a fresh config: the plugin was (re)installed, maybe from
                # OrcaCloud after a file. The copy in the data folder has the
                # settings the person had.
                copy = read_settings_copy()
                if copy.get("settings_rev"):
                    cfg.update(copy)
                    self.save_config(cfg)
            if int(cfg.get("settings_rev") or 1) >= SETTINGS_REV:
                if read_settings_copy() != cfg:
                    write_settings_copy(cfg)     # the copy follows "Restore defaults" too
                return
            # rev 2: the size became the file's own size by default. Every page
            # saved the old default (width, 100 mm) without anyone choosing it.
            rev = int(cfg.get("settings_rev") or 1)
            if rev < 2 and cfg.get("size_mode") == "width" and float(cfg.get("size_mm") or 0) == 100.0:
                cfg["size_mode"] = "original"
            # rev 3: thin details and sharp tips are cleaned by default (0.4 mm,
            # a common nozzle); the old default, off, was saved by every page
            if rev < 3 and "min_detail_mm" in cfg and float(cfg.get("min_detail_mm") or 0) == 0.0:
                cfg["min_detail_mm"] = 0.4
            cfg["settings_rev"] = SETTINGS_REV
            self.save_config(cfg)
        except Exception:  # noqa: BLE001 - settings must never stop the plugin
            traceback.print_exc()

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
            if isinstance(e, PermissionError):
                self.log_file.write("ERROR", traceback.format_exc())
                self.error(action, self.tr("error.permission", detail=str(e)[:160]))
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
        Reads the files a heavy action will use, on the calling (UI) thread,
        so OrcaSlicer's permission prompt, if any, shows up where it can (off
        the UI thread it refuses first and asks afterwards). Nothing is
        written: OrcaSlicer asks per exact file, so a test file would only add
        prompts of its own.
        """
        for key in ("svg", "project"):
            p = msg.get(key)
            if p and not denied_name(p) and os.path.isfile(p):
                try:
                    if key == "project":
                        read_for_update(p, 1)
                    else:
                        with open(p, "rb") as f:
                            f.read(1)
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

    def _layer_heights(self):
        try:
            return self.host.layer_heights()
        except Exception:  # noqa: BLE001 - optional information
            return None

    def do_init(self, msg):
        s = self.settings()
        fil = self._filaments()
        self.send({
            "type": "init", "version": __version__, "mode": self.mode,
            "lang": self.tr.lang, "lang_setting": s.get("language", "auto"),
            "host_lang": self.host.language(), "languages": i18n.available(),
            "catalog": self.tr.catalog(), "settings": s, "layers": self._layer_heights(),
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

    def do_describe_colors(self, msg):
        """Name and suggested filament of colors the page picked for its parts."""
        from . import colors as C
        fil = msg.get("filaments")
        if fil is None:
            fil = self._filaments()["filaments"]
        wanted = [c for c in (C.normalize_hex(x) for x in msg.get("colors") or []) if c]
        match = C.match_filaments(wanted, fil or [])
        self.send({"type": "colors_info", "items": {
            c: {"name": self.tr.color_name(C.color_name_key(c)),
                "filament": match[c][0] if c in match else None}
            for c in wanted}})

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
        # which object of the saved project each plate object is
        if d.get("project"):
            try:
                engine = load_engine()
                key = (d["project"], os.path.getmtime(d["project"]))
                d["project_mtime"] = key[1]
                listing = self._listing_cache.get(key)
                if listing is None:
                    listing = engine.list_objects(d["project"])
                    self._listing_cache = {key: listing}
                d["layers"] = listing.get("layers")
                ids = engine.match_plate_objects(d["objects"], listing["objects"])
                for item, oid in zip(d["objects"], ids):
                    item["object_id"] = oid
                d["plate_saved"] = engine.plate_matches_file(d["objects"], listing["objects"], ids)
            except UserError as e:
                d["project_error"] = self.tr(e.key, **e.params)
            except Exception as e:  # noqa: BLE001 - a broken file must not break the page
                d["project_error"] = self.tr("error.project_read", detail=str(e)[:200])
        self.send(d)

    def do_changelog(self, msg):
        from .panel import read_changelog
        self.send({"type": "changelog", "text": read_changelog(self.tr.lang), "version": __version__})

    def do_inputs(self, msg):
        self.send(self._inputs())

    def do_pick(self, msg):
        kind = msg.get("kind")
        s = self.settings()
        if kind == "svg":
            args = ("file", self.tr("pick.svg"), self._pick_start("svg", msg), ("*.svg",), "SVG")
        elif kind == "project":
            args = ("file", self.tr("pick.project"), self._pick_start("project", msg),
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
        if path and denied_name(path):
            self.send({"type": "picked", "kind": kind, "path": "", "failed": True,
                       "text": self.tr("error.denied_name", path=path)})
            return
        if path and kind in ("svg", "project"):
            self._remember_folder(kind, os.path.dirname(path))
        self.send({"type": "picked", "kind": kind, "path": path,
                   "cancelled": not path})

    def _pick_start(self, kind, msg):
        """
        The folder the picker opens in: the current file's, the one chosen
        last time, then Downloads, Documents, home.
        """
        cfg = self.get_config()
        for folder in [msg.get("initial"), cfg.get(f"last_{kind}_folder")] + user_folders():
            if folder and os.path.isdir(folder) and not denied_name(folder):
                return folder
        return ""

    def _remember_folder(self, kind, folder):
        cfg = self.get_config()
        if folder and cfg.get(f"last_{kind}_folder") != folder:
            cfg[f"last_{kind}_folder"] = folder
            self.save_config(cfg)

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
        return self._allowed(out)

    def _choices(self, msg):
        out = {}
        for c in msg.get("colors") or []:
            if isinstance(c, dict) and c.get("color"):
                out[str(c["color"]).lower()] = c
        return out

    @staticmethod
    def _allowed(path):
        """Refuses early, and clearly, a path OrcaSlicer would block anyway."""
        if path and denied_name(path):
            raise EngineError("error.denied_name", path=path)
        return path

    def _svg(self, msg):
        p = (msg.get("svg") or "").strip()
        self._allowed(p)
        if not p or not os.path.isfile(p):
            raise EngineError("error.no_svg")
        return p

    def do_analyze(self, msg, rep):
        engine = load_engine()
        svg = self._svg(msg)
        opts = self._options(msg)
        fil = msg.get("filaments")
        if fil is None:
            fil = self._filaments()["filaments"]
        rep.progress(0.0, "progress.reading")
        res = engine.analyze(svg, opts, filaments=fil, tr=self.tr, rep=rep,
                             levels=bool(msg.get("levels")))
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
        engine = load_engine()
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

    def do_faces(self, msg, rep):
        engine = load_engine()
        project = self._allowed((msg.get("project") or "").strip())
        oid = str(msg.get("object_id") or "").strip()
        if not project or not os.path.isfile(project):
            raise EngineError("error.no_project")
        key, loaded, listing = self._faces(engine, project, oid)
        self.send({"type": "faces", "project": project, "object_id": oid, "mtime": key[1],
                   "faces": listing["faces"], "default": listing["default"]})

    def _faces(self, engine, project, oid):
        """(key, loaded, listing) of an object's faces, kept until the project changes."""
        key = (project, os.path.getmtime(project), oid)
        cached = self._faces_cache.get(key)
        if cached is None:
            loaded = engine.load_faces(project, oid)
            cached = (loaded, engine.list_faces(project, oid, loaded))
            self._faces_cache = {key: cached}
        return (key,) + cached

    def do_paint_fill(self, msg, rep):
        """The bucket: the bare part of the face where the page was clicked, and the color next to it."""
        engine = load_engine()
        svg = self._svg(msg)
        project = self._allowed((msg.get("project") or "").strip())
        oid = str(msg.get("object_id") or "").strip()
        if not project or not os.path.isfile(project):
            raise EngineError("error.no_project")
        key, (faces, _silhouette), _listing = self._faces(engine, project, oid)
        face = next((f for f in faces if str(f.id) == str(msg.get("face_id"))), None)
        if face is None:
            raise EngineError("error.no_faces")
        point = msg.get("point") or []
        if len(point) != 2:
            return
        color = msg.get("color") if isinstance(msg.get("color"), str) else None
        found = engine.paint_fill(svg, face, self._options(msg), _paint_ops(msg), point, color, rep)
        d = {"type": "paint_fill", "project": project, "object_id": oid, "mtime": key[1],
             "face_id": msg.get("face_id")}
        if found is None:
            d.update(ok=False, text=self.tr("paint.nothing"))
        else:
            rings, color = found
            d.update(ok=True, op={"kind": "area", "color": color, "rings": rings})
        self.send(d)

    def do_face_context(self, msg, rep):
        """The whole object seen from outside one face, for the page to draw around it."""
        engine = load_engine()
        project = self._allowed((msg.get("project") or "").strip())
        oid = str(msg.get("object_id") or "").strip()
        if not project or not os.path.isfile(project):
            raise EngineError("error.no_project")
        key, loaded, _listing = self._faces(engine, project, oid)
        d = engine.face_context(loaded, msg.get("face_id"))
        d.update({"type": "face_context", "project": project, "object_id": oid, "mtime": key[1],
                  "face_id": msg.get("face_id")})
        self.send(d)

    def _finish(self, action, dest, report, reopen=False, text=None):
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
                   "open_after": reopen or bool(s.get("open_after")),
                   "reopen": reopen,
                   "text": text or self.tr("status.saved_to", path=dest)})

    def do_generate(self, msg, rep):
        engine = load_engine()
        svg = self._svg(msg)
        opts = self._options(msg)
        out = self._out_dir(msg)
        dest, report = engine.generate(svg, out, opts, self._choices(msg),
                                       filaments=msg.get("filaments"), tr=self.tr, rep=rep,
                                       heights=self._layer_heights())
        self._finish("generate", dest, report, reopen=bool(msg.get("reopen")))

    def do_apply(self, msg, rep):
        engine = load_engine()
        svg = self._svg(msg)
        project = self._allowed((msg.get("project") or "").strip())
        obj = str(msg.get("object_id") or "").strip()
        if not obj:
            raise EngineError("error.no_object")
        opts = self._options(msg)
        mode = (msg.get("options") or {}).get("apply_output") or self.settings().get("apply_output")

        def apply(dest):
            return engine.apply_to_project(svg, project, obj, dest, opts, self._choices(msg),
                                           filaments=msg.get("filaments"), tr=self.tr, rep=rep,
                                           face_id=msg.get("face_id"), paint_ops=_paint_ops(msg))

        if mode == "copy":
            dest, report = apply(engine.project_output_path(project, self._out_dir(msg)))
            self._finish("apply", dest, report, reopen=bool(msg.get("reopen")))
            return
        # the project itself: written aside, the original kept in backups, then replaced
        work = os.path.join(plugin_data_dir(), "tmp", os.path.basename(project))
        os.makedirs(os.path.dirname(work), exist_ok=True)
        _dest, report = apply(work)
        backup = self._backup(project)
        copy_file(work, project)
        try:
            os.remove(work)
        except OSError:
            pass
        self.info(self.tr("status.saved_project", path=project, backup=backup))
        self._finish("apply", project, report, reopen=bool(msg.get("reopen")),
                     text=self.tr("status.saved_project", path=project, backup=backup))

    @staticmethod
    def _backup(project):
        """A copy of `project` in <data>/backups before it is replaced; the last BACKUPS_KEPT stay."""
        folder = os.path.join(plugin_data_dir(), "backups")
        os.makedirs(folder, exist_ok=True)
        stem = os.path.splitext(os.path.basename(project))[0]
        dest = os.path.join(folder, f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}.3mf")
        with open(dest, "wb") as f:
            f.write(read_for_update(project))
        kept = sorted((os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith(".3mf")),
                      key=os.path.getmtime)
        for old in kept[:-BACKUPS_KEPT]:
            try:
                os.remove(old)
            except OSError:
                pass
        return dest
