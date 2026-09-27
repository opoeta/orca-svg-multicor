# -*- coding: utf-8 -*-
"""Assembles the panel page: one self-contained HTML string (no network)."""

import json
import os

from . import i18n
from ._version import __version__

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


def _read(name):
    with open(os.path.join(UI_DIR, name), encoding="utf-8") as f:
        return f.read()


def build_html(lang=None, mode="page", extra_head=""):
    """
    The page, already translated to `lang` so the first paint is in the right
    language. The page asks the plugin for everything else once it loads.
    """
    tr = i18n.Translator(lang)
    boot = {"lang": tr.lang, "catalog": tr.catalog(), "mode": mode,
            "version": __version__}
    # "</" inside a <script> block would end it early
    boot_json = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
    html = _read("panel.html")
    html = html.replace("/*CSS*/", _read("panel.css"), 1)
    html = html.replace("/*BOOT*/", boot_json, 1)
    html = html.replace("/*JS*/", _read("panel.js").replace("</script", "<\\/script"), 1)
    if extra_head:
        html = extra_head + html
    return html
