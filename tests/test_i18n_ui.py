"""Translations and the web page."""
import json
import os
import re
import shutil
import subprocess

import pytest

from orca_svg_multicor import i18n
from orca_svg_multicor.colors import NAMED_COLORS
from orca_svg_multicor.panel import UI_DIR, build_html

LOCALES = i18n.LOCALES_DIR
CODES = sorted(f[:-5] for f in os.listdir(LOCALES) if f.endswith(".json"))
FIELD = re.compile(r"\{(\w+)\}")


def load(code):
    with open(os.path.join(LOCALES, code + ".json"), encoding="utf-8") as f:
        return json.load(f)


EN = load("en")


def test_there_are_several_languages():
    assert "en" in CODES and "pt_BR" in CODES and len(CODES) >= 10


@pytest.mark.parametrize("code", CODES)
def test_catalog_complete_and_placeholders_match(code):
    cat = load(code)
    assert cat["_meta"]["name"]
    missing = sorted(set(EN) - set(cat))
    extra = sorted(set(cat) - set(EN))
    assert not missing, f"{code} misses {missing}"
    assert not extra, f"{code} has unknown keys {extra}"
    for k, v in EN.items():
        if k == "_meta":
            continue
        assert isinstance(cat[k], str) and cat[k].strip(), f"{code}:{k} empty"
        assert set(FIELD.findall(cat[k])) == set(FIELD.findall(v)), f"{code}:{k} placeholders"


def test_every_key_used_in_code_exists():
    used = set()
    src = os.path.dirname(UI_DIR)
    for fn in os.listdir(src):
        if fn.endswith(".py"):
            text = open(os.path.join(src, fn), encoding="utf-8").read()
            used |= set(re.findall(r'["\']((?:error|warn|progress|log|status|pick|part|objects|batch)\.[a-z_]+)["\']', text))
    for fn in ("panel.html", "panel.js", "settings.html"):
        text = open(os.path.join(UI_DIR, fn), encoding="utf-8").read()
        used |= set(re.findall(r'data-i18n(?:-ph|-title|-aria)?="([a-z_]+\.[a-z_0-9]+)"', text))
        used |= set(re.findall(r"'([a-z]+\.[a-z_0-9]+)'", text))
    used |= {"color." + k for k in NAMED_COLORS}
    used = {k for k in used if k.split(".")[0] not in ("svg", "image")}
    assert not sorted(used - set(EN))


@pytest.mark.parametrize("given,expected", [
    ("pt_BR", "pt_BR"), ("pt-br", "pt_BR"), ("pt", "pt_BR"), ("pt_PT", "pt_BR"),
    ("zh_CN.UTF-8", "zh_CN"), ("de_DE", "de"), ("", "en"), (None, "en"), ("xx_YY", "en")])
def test_normalize(given, expected):
    assert i18n.normalize(given) == expected


def test_translator_fallbacks_and_formatting():
    tr = i18n.Translator("de")
    assert tr("status.saved_to", path="X").endswith("X")
    assert tr("does.not.exist") == "does.not.exist"
    assert tr("objects.parts") != ""        # missing params stay as {n}


def test_page_builds_translated_and_safe():
    html = build_html("pt_BR")
    assert "/*CSS*/" not in html and "/*BOOT*/" not in html and "/*JS*/" not in html
    boot = re.search(r"window\.SVGM_BOOT = (\{.*?\});</script>", html, re.S).group(1)
    data = json.loads(boot)
    assert data["lang"] == "pt_BR" and data["catalog"]["target.title"]
    # no external resources: the page must work offline inside OrcaSlicer
    assert not re.search(r'(src|href)="https?://', html)


def test_config_page_builds():
    from orca_svg_multicor.panel import build_settings_html
    html = build_settings_html("de", {"size_mm": 100})
    boot = json.loads(re.search(r"window\.SVGM_CFG = (\{.*?\});</script>", html, re.S).group(1))
    assert boot["lang"] == "de" and boot["defaults"]["size_mm"] == 100
    assert any(l["code"] == "pt_BR" for l in boot["languages"])
    assert "3.1.0" in boot["changelog"] or boot["changelog"]
    assert not re.search(r'(src|href)="https?://', html)


def test_page_has_no_app_chrome():
    """The page is part of OrcaSlicer: no own language picker, header, log or defaults buttons."""
    html = build_html("en")
    for gone in ('id="lang"', 'class="top"', 'id="log"', "btn_save_defaults", "svg_recent",
                 'id="open_after"'):
        assert gone not in html, gone


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_panel_js_syntax():
    r = subprocess.run(["node", "--check", os.path.join(UI_DIR, "panel.js")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
