# -*- coding: utf-8 -*-
"""
Translations.

Catalogs are flat JSON files in locales/<code>.json ("pt_BR", "zh_CN", ...),
English being the reference. A missing key falls back to English, then to the
key itself, so a partial translation never breaks the interface.

To add a language: copy locales/en.json to locales/<code>.json, translate the
values (keep the {placeholders}), and set "_meta.name" to the language's own
name. Nothing else needs to change.
"""

import json
import os
import re
import threading

LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
DEFAULT = "en"

_lock = threading.Lock()
_cache = {}


def _load(code):
    with _lock:
        if code in _cache:
            return _cache[code]
        path = os.path.join(LOCALES_DIR, code + ".json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = None
        _cache[code] = data
        return data


def available():
    """[{"code": "pt_BR", "name": "Português (Brasil)"}, ...] sorted by name."""
    out = []
    try:
        names = sorted(os.listdir(LOCALES_DIR))
    except OSError:
        names = []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        code = fn[:-5]
        data = _load(code) or {}
        name = (data.get("_meta") or {}).get("name") or code
        out.append({"code": code, "name": name})
    out.sort(key=lambda x: (x["code"] != DEFAULT, x["name"].lower()))
    return out


def normalize(code):
    """
    Maps whatever the host reports ("pt_BR", "pt-br", "pt", "zh_CN.UTF-8",
    "Portuguese_Brazil") to an available catalog code, or "en".
    """
    if not code:
        return DEFAULT
    c = str(code).strip().split(".")[0].replace("-", "_")
    codes = [x["code"] for x in available()]
    lower = {x.lower(): x for x in codes}
    if c.lower() in lower:
        return lower[c.lower()]
    base = c.split("_")[0].lower()
    # prefer the region the host asked for, then any region of the language
    for x in codes:
        if x.lower() == base:
            return x
    for x in codes:
        if x.lower().split("_")[0] == base:
            return x
    return DEFAULT


_RE_FIELD = re.compile(r"\{(\w+)\}")


def _format(text, params):
    if not params:
        return text
    return _RE_FIELD.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params
                         else m.group(0), text)


class Translator:
    def __init__(self, lang=None):
        self.lang = normalize(lang)
        self._en = _load(DEFAULT) or {}
        self._cat = _load(self.lang) or {}

    def __call__(self, key, **params):
        text = self._cat.get(key)
        if not isinstance(text, str) or not text:
            text = self._en.get(key)
        if not isinstance(text, str) or not text:
            text = key
        return _format(text, params)

    def catalog(self):
        """English merged with the current language, for the web page."""
        merged = {k: v for k, v in self._en.items() if isinstance(v, str)}
        merged.update({k: v for k, v in self._cat.items() if isinstance(v, str) and v})
        return merged

    def color_name(self, key):
        return self("color." + key)
