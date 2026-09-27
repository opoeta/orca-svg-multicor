# Changelog

## 3.0.0

A rewrite focused on correct results, projects saved by current slicers, and
an interface in 13 languages.

### Fixed
- **Colors overlapped in 3D.** Each color used to be the union of all its
  shapes, ignoring what was painted on top of it, so a white logo on a black
  square produced a full black square plus a white part in the same volume.
  Shapes are now resolved like a browser paints them: later shapes cut earlier
  ones and the parts tile the plane.
- **"Apply to a project" did not work with projects saved by OrcaSlicer or
  Bambu Studio.** Those projects keep meshes in `3D/Objects/*.model` behind
  components, which the plugin rejected ("made of components"). They are now
  supported, and the size of the object includes its component transforms.
- **Namespace prefixes were rewritten in saved projects.** Re-serializing
  `3dmodel.model` with ElementTree replaced prefixes such as `p:` with automatic
  ones (`ns0:`), while OrcaSlicer matches `p:path` and `p:UUID` literally.
  Files are now edited by inserting text only.
- **"Apply" used the wrong project.** A project path typed or read from the
  plate was not sent; the first file of the input folder list was used instead,
  together with an object id from the other file.
- Open paths lost their first point ("M0,0 L10,0 L10,10" produced nothing).
- Islands inside holes vanished with the nonzero rule; overlapping rings were
  united instead of cut with the evenodd rule. Both rules are now exact.
- Gradients were printed black; they now use the average of their stops.
- Shapes with `opacity="0"`, `fill-opacity="0"` or fully transparent colors
  were printed.
- Curve sampling and simplification worked in SVG units, so small viewBoxes lost
  detail and large ones produced huge files. Both now work in millimeters.
- Filament preset names and color names were inserted into the page as HTML;
  a name with `<` or `"` could break the color list. The page now builds every
  element with DOM calls.
- Two parts with the same name got the same filament (filaments were keyed by
  name).
- The filament list was limited to the "max. colors" value.
- The plugin rewrote `icon.png` inside its installed package whenever OrcaSlicer
  asked for the icon (replacing the 256 px icon with a 64 px one).
- Batch mode opened one message box per converted file.
- The native progress dialog could not cancel anything.

### Added
- Interface in English, Português (Brasil), Español, Français, Deutsch,
  Italiano, Polski, Türkçe, Русский, Українська, 简体中文, 日本語 and 한국어,
  following OrcaSlicer's language or chosen in the page.
- New panel: live preview (result and original), hover to highlight a color,
  per-color names, filaments and on/off, filament chips, progress bar, log,
  light and dark themes, responsive layout.
- Strokes become printable areas (joins, caps and miter limit respected).
- Base plate (outline or rounded rectangle) for new 3MF files.
- "Remove details thinner than": unprintable slivers go to the neighboring
  color, without leaving gaps.
- Perceptual color distance (CIEDE2000) for merging, reducing and matching
  filaments; better color names.
- "Original size" from the SVG's physical units.
- Standard 3MF output carries colors (`basematerials`).
- Native file pickers for SVG and projects (not only folders), always on top.
- Warnings for text, bitmap images, clipping/masks, dashes, transparency.
- Settings can be saved as defaults; output folder remembered.
- Tests (87), a development server to run the panel in a browser, CI and
  releases on GitHub.

### Changed
- The heavy libraries are imported only when needed, so OrcaSlicer starts
  faster with the plugin enabled.
- Capability names are now `SVG Multicolor`, `SVG Multicolor - window` and
  `SVG Multicolor - batch`; config keys are in English.
- The log is `<data>/svg_multicor/plugin.log`, rotated at 1 MB, instead of a
  `registro.txt` written into the output folder.
- Batch mode no longer applies the first SVG to a project.

## 2.9.0

Original release by Israel Fernandes.
