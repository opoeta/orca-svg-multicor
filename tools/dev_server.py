# -*- coding: utf-8 -*-
"""
Development server: runs the panel in a normal browser, without OrcaSlicer.

    python tools/dev_server.py [--port 8765] [--lang pt_BR]

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

MOCK_BRIDGE = """<script>
(function () {
  var handlers = [];
  // ?svg=<path>&tab=apply&log=1&project=<path> preload the page (screenshots, demos)
  var q = new URLSearchParams(location.search), preloaded = false;
  function preload() {
    if (preloaded) return; preloaded = true;
    setTimeout(function () {
      if (q.get('tab')) { var b = document.querySelector('[data-tab="' + q.get('tab') + '"]'); if (b) b.click(); }
      if (q.get('log')) document.getElementById('btn_log').click();
      if (q.get('project')) { var p = document.getElementById('project_path'); p.value = q.get('project'); p.dispatchEvent(new Event('change')); }
      if (q.get('svg')) {
        var i = document.getElementById('svg_path'); i.value = q.get('svg');
        setTimeout(function () { i.dispatchEvent(new Event('change')); }, q.get('project') ? 400 : 0);
      }
    }, 0);
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
        if not self.project:
            return {"objects": [], "dirty": None, "project": ""}
        return {"objects": [{"index": 0, "name": os.path.basename(self.project),
                             "size": None, "parts": 1, "file": self.project,
                             "painted": False}],
                "dirty": False, "project": self.project}


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
                html = build_html(service.tr.lang, mode="dev", extra_head=MOCK_BRIDGE)
                page = ("<!doctype html><html><head><title>SVG Multicolor (dev)</title>"
                        "</head><body>" + html + "</body></html>")
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
