# Publishing on OrcaCloud

## Why

OrcaSlicer's **Plugins** dialog shows an image in *Plugin Info* and entries in
*Changelog* only for plugins that come from OrcaCloud ("Subscribed" or "Mine").
Every plugin that shows them there was installed from OrcaCloud; none carries
them in its package. For a plugin installed from a local file both stay empty
(`src/slic3r/plugin/PluginDescriptor.hpp`: the thumbnail is the "Cloud
main_image … empty for local plugins", the changelog is the "Cloud release
changelog"), and OrcaSlicer only merges cloud data into a plugin whose key is
the OrcaCloud id, that is, one installed from OrcaCloud.

So: publish once on OrcaCloud, connect this repository, and every GitHub
release publishes the new version there, with its changelog.

## First publication (once, on your OrcaCloud account)

1. Sign in at <https://cloud.orcaslicer.com> (or from OrcaSlicer's menu).
2. **Plugins > Shared Plugins**, then the **+** button (bottom right).
3. Upload the wheel **renamed with a target suffix**, as OrcaCloud requires:
   `orca_svg_multicor_any.whl` (the same file as
   `orca_svg_multicor-<version>-py3-none-any.whl` from the GitHub release).
4. Fill in:

   | Field | Value |
   | --- | --- |
   | Name | SVG Multicolor |
   | Plugin image | `cover.png` in this folder (320 × 320) |
   | Description | below |
   | Version | the version of the file you uploaded |
   | Plugin type | Script (it also adds a page next to Prepare/Preview) |
   | Changelog | the notes of that version's GitHub release (English and Portuguese) |
   | Tags | utility, workflow, multicolor, svg |
   | Public | on, to appear in the Plugin Hub |

   Screenshots go in the **description**: the editor's image button uploads
   them (PNG, JPG, WEBP or GIF, up to 2 MB each), or paste the description
   below, which shows the images of this repository. OrcaSlicer's Plugins
   dialog shows only the plugin image; the screenshots appear on the plugin's
   page on OrcaCloud (Plugin Hub). `docs/` has each one in English and in
   Portuguese (`*-pt_BR.png`).
5. Save. Then **Edit plugin > GitHub publishing**, enter
   `opoeta/orca-svg-multicor` and **Connect**.
6. In the GitHub repository: **Settings > Secrets and variables > Actions >
   Variables**, add `ORCACLOUD_PUBLISH` = `true`. From then on, pushing a tag
   `vX.Y.Z` publishes the release on GitHub and on OrcaCloud
   (`.github/workflows/release.yml`), the changelog taken from `CHANGELOG.md`.
   The tag must be higher than the version already on OrcaCloud.
   **Actions > Publish on OrcaCloud > Run workflow** publishes a release that
   already exists (`.github/workflows/publish-orcacloud.yml`), to check the
   connection or to retry: OrcaCloud answers 201 when it publishes, 401 when
   the repository is not connected, and a version error when it already has
   that version.
7. In OrcaSlicer, **delete the locally installed copy** (both would load the
   same Python package), then subscribe to the plugin in the Plugin Hub and
   activate it in **File > Plugins**.

## Description

> Turns a multicolor SVG (a logo, a sign, a sticker design) into one printable
> part per color, aligned and already assigned to your filaments. Applies the
> colors to the surface you choose of an object on the plate (the top, a side,
> the floor of a tray...), inlaid or raised, or adds them as a new object,
> optionally on a base plate. Understands the SVG like a browser:
> stacked shapes, fill rules, strokes, gradients. Limits the colors to your
> filaments and matches each color to the closest one. A page next to Prepare
> and Preview, in 13 languages, following OrcaSlicer's language.
>
> Source and issues: https://github.com/opoeta/orca-svg-multicor
>
> ![The page, next to Prepare and Preview: the design on the chosen surface](https://raw.githubusercontent.com/opoeta/orca-svg-multicor/main/docs/screenshot.png)
>
> ![A new object on a base plate](https://raw.githubusercontent.com/opoeta/orca-svg-multicor/main/docs/screenshot-new.png)
>
> ![Settings in the Config tab](https://raw.githubusercontent.com/opoeta/orca-svg-multicor/main/docs/config.png)
