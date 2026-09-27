# SVG Multicolor for OrcaSlicer

[![CI](https://github.com/opoeta/orca-svg-multicor/actions/workflows/ci.yml/badge.svg)](https://github.com/opoeta/orca-svg-multicor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/opoeta/orca-svg-multicor)](https://github.com/opoeta/orca-svg-multicor/releases/latest)

**[Leia em português](README.pt-BR.md)**

An OrcaSlicer plugin that turns a multicolor SVG (a logo, a sign, a sticker design)
into **one printable part per color**, all aligned in the same frame and already
assigned to your filaments.

![The SVG Multicolor panel](docs/screenshot.png)

## What it does

- **New 3MF**: one object with one part per color, named and assigned to a
  filament, optionally on top of a **base plate** (following the outline, or a
  rounded rectangle). Opens in OrcaSlicer / Bambu Studio ready to slice. A
  standard 3MF (with colors) is also available for other slicers, plus one STL
  per color.
- **Apply to a project**: adds the colors as new parts of an object in a saved
  project, centered on its top face, **inlaid** (same height, the top layers
  change color) or **raised**. Works with the projects OrcaSlicer and Bambu
  Studio save today. The original project is never overwritten.
- **Sees the SVG like a browser does**: shapes painted later cover earlier
  ones, so the parts fit together instead of overlapping; fill rules
  (nonzero / evenodd) are exact; outlines (strokes) become printable areas;
  gradients use the average of their colors; hidden and fully transparent
  shapes are skipped; CSS classes, `<use>`, transforms and physical units
  (`width="80mm"`) are understood.
- **Fits your printer**: limits the number of colors to your filaments by
  merging the least significant ones into the most similar (CIEDE2000),
  merges near-identical tones, and can hand details thinner than the nozzle to
  the neighboring color.
- **Reads your filaments** from OrcaSlicer and matches each color to the closest
  one. Live preview, per-color names, filaments and on/off switches.
- **13 languages**, following OrcaSlicer's language automatically: English,
  Português (Brasil), Español, Français, Deutsch, Italiano, Polski, Türkçe,
  Русский, Українська, 简体中文, 日本語, 한국어.

## Installing

1. Download `orca_svg_multicor-<version>-py3-none-any.whl` from the
   [latest release](https://github.com/opoeta/orca-svg-multicor/releases/latest).
2. In OrcaSlicer, open the **Plugins** dialog and install the `.whl` file as a
   local plugin. OrcaSlicer installs the dependencies (numpy, shapely,
   svgelements, mapbox-earcut) by itself.
3. Enable the plugin. It adds:
   - **SVG Multicolor**: a page next to Prepare and Preview;
   - **SVG Multicolor - batch**: converts every SVG of the input folder with the
     same settings, from the Plugins dialog's Run action.

   Builds of OrcaSlicer without plugin pages get **SVG Multicolor - window**
   instead: the same page in a window.

> **Upgrading from 2.x**: remove the old plugin first. Both versions use the same
> Python package name and cannot be loaded side by side.

Requires an OrcaSlicer build with Python plugin support.

## Using it

The page works like the Prepare tab: settings on the left, the view on the
right, the main action at the top right.

1. **SVG file**: *Browse…* and choose the SVG. The colors appear on their own.
2. **Colors**: hover a row to highlight it in the view. Rename parts, untick
   what you do not want (a plain background, for example; colors that span the
   whole drawing are tagged *background?*), and pick each color's filament, or
   let the wand match them to the filaments loaded in OrcaSlicer.
3. **Apply to**:
   - **An object on the plate**: save the project (Ctrl+S), pick the object,
     choose *inlaid* (same height, the top layers change color) or *raised*,
     then **Apply to the plate**. OrcaSlicer's plugin API cannot change the
     plate directly, so the design goes into the saved project, which reopens
     in OrcaSlicer with the new parts. The original file is kept; the result is
     saved next to it as `*_svg.3mf` in the output folder.
   - **A new object on the plate**: optionally on a base plate, then **Add to
     the plate**; OrcaSlicer opens the new 3MF.

The page remembers the values you change. Defaults, the output folder, the
file format, STL export and the language are in the Plugins dialog, **Config**
tab, along with what's new in each version.

![Settings in the Config tab](docs/config.png)

### Settings

| Setting | Meaning |
| --- | --- |
| Size | Width, height, or the SVG's own physical size |
| Color thickness | Height of the color parts (mm) |
| Max. colors | Merge colors down to this number (0 = no limit) |
| Merge similar tones | Joins colors closer than this ΔE (0 = off) |
| Include outlines | Turns strokes into printable areas |
| Base plate | Thickness (0 = none), margin, shape and filament |
| Precision | Simplification tolerance (mm) |
| Ignore specks under | Drops islands and holes smaller than this area (mm²) |
| Remove details thinner than | Hands unprintable slivers to the neighboring color (0 = off) |

### Good to know

- **Text** must be converted to paths (outlines) in your editor; **bitmap
  images** are ignored; **clipping paths and masks** are ignored (release them
  if shapes show up where they should not). The panel warns about all of these.
- The **file dialog** runs as a separate process (PowerShell on Windows,
  `osascript` on macOS, `zenity`/`kdialog` on Linux), and results are opened by
  starting OrcaSlicer's executable, which hands the file to the window already
  open. OrcaSlicer asks once whether the plugin may start a process; if you say
  no, the page offers to upload a copy of the SVG instead.
- Inlaying relies on OrcaSlicer giving parts added later priority where parts
  overlap, the same mechanism used when you add a part inside an object by hand.
- OrcaSlicer's **Plugins dialog shows a preview image and a changelog only for
  plugins installed from OrcaCloud**; for a local `.whl` both stay empty by
  design. See [docs/orcacloud](docs/orcacloud/README.md) to publish it there.
  The changelog is also in [CHANGELOG.md](CHANGELOG.md).
- Files live in `<OrcaSlicer data folder>/svg_multicor/` (input, output and
  `plugin.log`); both folders can be changed in the Config tab.

## Adding a language

Copy `src/orca_svg_multicor/locales/en.json` to `<code>.json` (the code
OrcaSlicer uses, such as `nl` or `zh_TW`), translate the values, keep every
`{placeholder}`, set `_meta.name` to the language's own name, and run the tests.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e . -r requirements-dev.txt   # Windows: .venv\Scripts\pip
.venv/bin/pytest
python tools/dev_server.py --lang pt_BR --project some.3mf   # the page in a browser, OrcaSlicer's look, fake plate
python -m build --wheel                   # dist/orca_svg_multicor-<version>-py3-none-any.whl
```

The code is split so that everything except `capabilities.py` runs without
OrcaSlicer:

| Module | Role |
| --- | --- |
| `svgread.py` | SVG → ordered paint operations (fills and strokes) |
| `geometry.py` | fill rules, occlusion, cleanup, base plate, preview |
| `colors.py` | CIEDE2000, naming, merging and reducing colors, filament matching |
| `mesh.py` | extrusion, watertightness check, STL |
| `threemf.py` | OrcaSlicer/Bambu project layout and standard 3MF writers |
| `project3mf.py` | reading and editing saved projects |
| `engine.py` | analyze / generate / apply pipeline |
| `service.py` | messages between the page and the engine, translated |
| `host.py` | OrcaSlicer host API, native pickers, log |
| `capabilities.py` | the OrcaSlicer capabilities |
| `ui/` | the panel (HTML, CSS, JS; no external resources) |

## Credits

Created by Israel Fernandes. Released under the [MIT license](LICENSE).
