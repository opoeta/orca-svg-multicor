# -*- coding: utf-8 -*-
"""
Development server: runs the panel in a normal browser, without OrcaSlicer.

    python tools/dev_server.py [--port 8765] [--lang pt_BR] [--project saved.3mf]

    /          the page (?svg=<path>&target=new&theme=light&adv=1 to preload)
    /config    the settings page of the Plugins dialog's Config tab

The page gets a stand-in `window.orca` that forwards every message to the real
Python service over HTTP, so analysis, preview and 3MF generation are the real
thing. The host is fake: four filaments, and the "plate" is the project given
with --project. Settings live in tools/_dev_data/config.json.
"""

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
DATA = os.path.join(HERE, "_dev_data")
# the dev server keeps its folders and log away from the real OrcaSlicer data
os.environ.setdefault("SVGM_DATA_DIR", DATA)

from orca_svg_multicor.host import BaseHost  # noqa: E402
from orca_svg_multicor.panel import build_html  # noqa: E402
from orca_svg_multicor.service import Service  # noqa: E402

CONFIG = os.path.join(DATA, "config.json")

# What OrcaSlicer injects into plugin pages: the theme variables and the default
# plugin stylesheet (copied from OrcaSlicer's own injection), so the page looks
# here the way it looks inside OrcaSlicer. ?theme=light switches the variables.
HOST_THEMES = {
    "dark": ":root{--orca-bg:#2d2d31;--orca-fg:#e6e6e6;--orca-muted:#9a9aa0;--orca-border:#48484e;"
            "--orca-accent:#009688;--orca-accent-fg:#ffffff;"
            "--orca-font:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color-scheme:dark;}",
    "light": ":root{--orca-bg:#ffffff;--orca-fg:#262e30;--orca-muted:#6b6b6b;--orca-border:#dbdbdb;"
             "--orca-accent:#009688;--orca-accent-fg:#ffffff;"
             "--orca-font:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color-scheme:light;}",
}
HOST_DEFAULTS = (
    "html,body{background:var(--orca-bg);color:var(--orca-fg);font-family:var(--orca-font);font-size:13px;}"
    "body{margin:0;}h1,h2,h3,h4,h5,h6{color:var(--orca-fg);font-weight:600;}a{color:var(--orca-accent);}"
    "hr{border:0;border-top:1px solid var(--orca-border);}"
    "button{font:inherit;color:var(--orca-accent-fg);background:var(--orca-accent);"
    "border:1px solid var(--orca-accent);border-radius:4px;padding:5px 14px;cursor:pointer;}"
    "button:hover{filter:brightness(1.1);}button:disabled{opacity:.5;cursor:default;}"
    "input,select,textarea{font:inherit;color:var(--orca-fg);background:var(--orca-bg);"
    "border:1px solid var(--orca-border);border-radius:4px;padding:4px 8px;}"
    "input:focus,select:focus,textarea:focus{outline:none;border-color:var(--orca-accent);}"
    "table{border-collapse:collapse;}th,td{text-align:left;padding:6px 10px;"
    "border-bottom:1px solid var(--orca-border);}th{color:var(--orca-muted);font-weight:600;}"
    "::-webkit-scrollbar{width:12px;height:12px;}"
    "::-webkit-scrollbar-thumb{background:var(--orca-border);border-radius:6px;}"
    "::-webkit-scrollbar-track{background:transparent;}")


def host_head(theme):
    return (f'<style id="orca-host-theme-vars">{HOST_THEMES.get(theme, HOST_THEMES["dark"])}</style>'
            f'<style id="orca-plugin-defaults">{HOST_DEFAULTS}</style>')


MOCK_BRIDGE = """<script>
(function () {
  var handlers = [];
  // ?svg=<path>&target=new preload the page (screenshots, demos)
  var q = new URLSearchParams(location.search), preloaded = false;
  function preload() {
    if (preloaded) return; preloaded = true;
    setTimeout(function () {
      if (q.get('target')) { var r = document.querySelector('input[name=target][value="' + q.get('target') + '"]');
        if (r) { r.checked = true; r.dispatchEvent(new Event('change')); } }
      if (q.get('adv')) document.getElementById('adv').open = true;
      if (q.get('svg')) window.__svgmUse && window.__svgmUse(q.get('svg'));
    }, 50);
  }
  function dispatch(list) {
    list.forEach(function (m) {
      handlers.forEach(function (h) { try { h(m); } catch (e) { console.error(e); } });
      if (m && m.type === 'init') preload();
    });
  }
  window.orca = {
    postMessage: function (data) {
      fetch('/msg', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(function (r) { return r.json(); }).then(dispatch)
        .catch(function (e) { console.error('bridge', e); });
    },
    onMessage: function (cb) { handlers.push(cb); }
  };
})();
</script>
"""


class DevHost(BaseHost):
    name = "dev"

    def __init__(self, lang=None, project=""):
        self.lang = lang
        self.project = project

    def language(self):
        return self.lang

    def filaments(self):
        return {"source": "dev", "filaments": [
            {"n": 1, "name": "PLA Basic White", "color": "#f2f2f2"},
            {"n": 2, "name": "PLA Basic Black", "color": "#161616"},
            {"n": 3, "name": "PLA Basic Red", "color": "#c8102e"},
            {"n": 4, "name": "PLA Basic Yellow", "color": "#f4c300"},
        ]}

    def plate(self):
        """The objects of --project, as if that project were open in Prepare."""
        if not self.project:
            return {"objects": [], "dirty": None, "project": ""}
        from orca_svg_multicor.engine import list_objects
        objs = list_objects(self.project)["objects"]
        return {"objects": [{"index": i, "name": o["name"], "size": o["size"], "parts": o["parts"],
                             "file": self.project, "painted": False} for i, o in enumerate(objs)],
                "dirty": False, "project": self.project}

    def open_path(self, path):
        print(f"[dev] OrcaSlicer would open: {path}")


def config_store():
    os.makedirs(DATA, exist_ok=True)

    def get():
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save(cfg):
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True

    return get, save


def make_handler(service, outbox, lock, lang):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/index.html"):
                theme = "light" if "theme=light" in self.path else "dark"
                html = build_html(service.tr.lang, mode="dev", extra_head=host_head(theme) + MOCK_BRIDGE)
                page = ("<!doctype html><html><head><title>SVG Multicolor (dev)</title>"
                        "</head><body>" + html + "</body></html>")
                self._send(200, page, "text/html; charset=utf-8")
            elif self.path.split("?")[0] == "/config":
                from orca_svg_multicor.panel import build_config_html
                from orca_svg_multicor.service import settings_defaults
                stored = json.dumps(service.get_config())
                page = ("<!doctype html><html><head><title>Config (dev)</title>"
                        + host_head("dark").split("<style id=\"orca-plugin-defaults\">")[0]
                        + "<script>window.orca={getConfig:function(){return " + stored + ";},"
                        "saveConfig:function(c){fetch('/msg',{method:'POST',body:JSON.stringify("
                        "{action:'save_settings',settings:c})});},restoreDefaults:function(){},"
                        "onConfig:function(cb){cb(this.getConfig());}};</script></head><body>"
                        + build_config_html(service.tr.lang, settings_defaults()) + "</body></html>")
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, "not found", "text/plain")

        def do_POST(self):
            if self.path != "/msg":
                self._send(404, "not found", "text/plain")
                return
            n = int(self.headers.get("Content-Length") or 0)
            try:
                msg = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                msg = {}
            with lock:
                outbox.clear()
                service.handle(msg)
                out = list(outbox)
            self._send(200, json.dumps(out), "application/json")

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lang", default=None, help="language OrcaSlicer would report")
    ap.add_argument("--project", default="", help="a .3mf to present as the open project")
    args = ap.parse_args()

    outbox = []
    service = Service(DevHost(args.lang, args.project), config_store(), outbox.append,
                      mode="dev")
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(service, outbox, threading.Lock(), args.lang))
    print(f"SVG Multicolor dev server: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
