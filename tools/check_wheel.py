# -*- coding: utf-8 -*-
"""
Sanity checks on a built wheel before it is released:
pure Python, one .dist-info, and every runtime file (locales, ui, icon) inside.

    python tools/check_wheel.py dist/orca_svg_multicor-*.whl
"""

import glob
import json
import sys
import zipfile

REQUIRED = [
    "orca_svg_multicor/__init__.py",
    "orca_svg_multicor/capabilities.py",
    "orca_svg_multicor/icon.png",
    "orca_svg_multicor/icon.svg",
    "orca_svg_multicor/ui/panel.html",
    "orca_svg_multicor/ui/panel.css",
    "orca_svg_multicor/ui/panel.js",
    "orca_svg_multicor/ui/settings.html",
    "orca_svg_multicor/CHANGELOG.md",
    "orca_svg_multicor/locales/en.json",
    "orca_svg_multicor/locales/pt_BR.json",
]
DEPS = ["numpy", "shapely", "svgelements", "mapbox-earcut"]


def check(path):
    problems = []
    if not path.endswith("-py3-none-any.whl"):
        problems.append("not a pure-Python (py3-none-any) wheel")
    z = zipfile.ZipFile(path)
    names = z.namelist()
    infos = {n.split("/")[0] for n in names if n.split("/")[0].endswith(".dist-info")}
    if len(infos) != 1:
        problems.append(f"expected one .dist-info, found {sorted(infos)}")
    for r in REQUIRED:
        if r not in names:
            problems.append(f"missing {r}")
    locales = [n for n in names if n.startswith("orca_svg_multicor/locales/") and n.endswith(".json")]
    for n in locales:
        try:
            json.loads(z.read(n).decode("utf-8"))
        except ValueError as e:
            problems.append(f"{n}: {e}")
    meta = z.read(next(iter(infos)) + "/METADATA").decode("utf-8") if infos else ""
    for d in DEPS:
        if f"Requires-Dist: {d}" not in meta:
            problems.append(f"METADATA does not require {d}")
    if any(n.endswith((".pyc", "_dev_data/")) or "/tests/" in n for n in names):
        problems.append("stray files in the wheel")
    # OrcaSlicer's audit hook refuses plugins any path with these words in a name
    for n in names:
        if n.split("/")[0].endswith(".dist-info"):
            continue
        if any(w in n.lower() for w in ("secret", "cert", "conf")):
            problems.append(f"OrcaSlicer would refuse to read {n} (conf/cert/secret in the name)")
    print(f"{path}: {len(names)} files, {len(locales)} languages")
    return problems


def main(argv):
    paths = [p for a in argv for p in glob.glob(a)]
    if not paths:
        print("no wheel given")
        return 1
    bad = False
    for p in paths:
        for problem in check(p):
            bad = True
            print("  ERROR:", problem)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
