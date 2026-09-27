# -*- coding: utf-8 -*-
"""
Builds the HTML OrcaSlicer shows for the plugin: the page (Pages capability)
and the settings page of the Plugins dialog's Config tab. Both are single
self-contained strings: nothing is loaded from the network.
"""

import json
import os

from . import i18n
from ._version import __version__

HERE = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(HERE, "ui")


def _read(name):
    with open(os.path.join(UI_DIR, name), encoding="utf-8") as f:
        return f.read()


def _json(value):
    # "</" inside a <script> block would end it early
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def read_changelog():
    """CHANGELOG.md shipped in the wheel (or the repository's, when developing)."""
    for p in (os.path.join(HERE, "CHANGELOG.md"), os.path.join(HERE, "..", "..", "CHANGELOG.md")):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return ""


def build_html(lang=None, mode="page", extra_head=""):
    """
    The page, already translated to `lang` so the first paint is in the right
    language. The page asks the plugin for everything else once it loads.
    """
    tr = i18n.Translator(lang)
    boot = {"lang": tr.lang, "catalog": tr.catalog(), "mode": mode, "version": __version__}
    html = _read("panel.html")
    html = html.replace("/*CSS*/", _read("panel.css"), 1)
    html = html.replace("/*BOOT*/", _json(boot), 1)
    html = html.replace("/*JS*/", _read("panel.js").replace("</script", "<\\/script"), 1)
    return extra_head + html if extra_head else html


def build_settings_html(lang=None, defaults=None):
    """Settings page for the Plugins dialog's Config tab (window.orca.getConfig/saveConfig)."""
    tr = i18n.Translator(lang)
    boot = {"lang": tr.lang, "catalog": tr.catalog(), "languages": i18n.available(),
            "defaults": defaults or {}, "changelog": read_changelog(), "version": __version__}
    return _read("settings.html").replace("/*BOOT*/", _json(boot), 1)


def build_note_html(text):
    """A one-line Config page, for capabilities that share another one's settings."""
    safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return ("<meta charset='utf-8'><style>body{margin:0;padding:12px;background:var(--orca-bg,#2d2d31);"
            "color:var(--orca-muted,#9a9aa0);font:13px var(--orca-font,system-ui,sans-serif)}</style>"
            f"<p>{safe}</p>")
