# Publishing on OrcaCloud

OrcaSlicer's **Plugins** dialog shows a preview image and a changelog only for
plugins that come from OrcaCloud. For a plugin installed from a local `.whl`
file both stay empty: in OrcaSlicer's source, the thumbnail is documented as
"Cloud main_image … empty for local plugins" and the changelog as "Cloud release
changelog" (`src/slic3r/plugin/PluginDescriptor.hpp`). A plugin cannot fill them
itself.

Publishing on OrcaCloud (cloud.orcaslicer.com, signed in with your account)
gives both. Everything needed is here:

| Field | Use |
| --- | --- |
| Main image | `cover.png` (320 × 320, same size as the plugins already published) |
| Package | `orca_svg_multicor-<version>-py3-none-any.whl` from the GitHub release |
| Name | SVG Multicolor |
| Tags | utility, workflow, multicolor, svg |
| Description | below |
| Changelog | one entry per version, below |

## Description

> Turns a multicolor SVG (a logo, a sign, a sticker design) into one printable
> part per color, aligned and already assigned to your filaments. Generates a new
> 3MF (one object, one named part per color, optional base plate) or inlays the
> colors into an object of a saved project. Understands the SVG like a browser:
> stacked shapes, fill rules, strokes, gradients. Limits the colors to your
> filaments and matches each color to the closest filament. Interface in 13
> languages, following OrcaSlicer's language.
>
> Source and issues: https://github.com/opoeta/orca-svg-multicor

## Changelog entries

**3.1.0**

```
- Works like part of OrcaSlicer: page laid out like the Prepare tab, OrcaSlicer's theme and language.
- Apply to an object on the plate: the saved project reopens with the new parts.
- Add as a new object: the new 3MF opens in OrcaSlicer.
- Settings and what's new in the Plugins dialog's Config tab.
```

**3.0.1**

```
- No more "open" permission prompt when browsing for a file.
- Crisp icon on the plugin page tab.
- Faster plugin loading (heavy libraries load only when needed).
```

**3.0.0**

```
- Colors no longer overlap: shapes painted on top cut the ones below, like in a browser.
- "Apply to a project" works with projects saved by OrcaSlicer and Bambu Studio, and uses the project's filaments.
- Exact fill rules, strokes, gradients, invisible shapes; new 3MF with named parts and filaments; base plate.
- New panel with live preview, per-color filament and name, 13 languages.
```
