# Changelog

## 3.2.0

### Changed
- Results reach OrcaSlicer through the channel its own launcher uses when it
  runs as a single instance (on Windows, a message to the main window), like
  other plugins do: no process is started, so there is no permission prompt.
  Starting OrcaSlicer's executable remains the fallback.

### Added
- Releases can be published on OrcaCloud automatically (GitHub trusted
  publishing). OrcaSlicer's Plugins dialog shows the image and the changelog
  only for plugins installed from OrcaCloud; `docs/orcacloud/README.md`
  explains the one-time setup.

## 3.1.1

### Fixed
- The settings page of the Config tab failed to load ("PermissionError: Plugin
  attempted an audited operation without permission"). OrcaSlicer refuses
  plugins any path with "conf", "cert" or "secret" in a file or folder name,
  and the page's file was called `config.html`; it is now `settings.html`, and
  the tests and the wheel check reject such names.
- An SVG, project or output folder whose path contains one of those words now
  gets a clear message saying why OrcaSlicer blocks it, instead of an
  unexpected error; so does any other permission OrcaSlicer refuses.

## 3.1.0

### Changed: it behaves like a plugin now
- The page is laid out like OrcaSlicer's Prepare tab (settings on the left,
  the view on the right, the main action at the top), styled by OrcaSlicer's
  own theme and plugin defaults, in OrcaSlicer's language. Gone: the page's own
  header, language picker, log panel, input folder list, tabs and "save as
  default" buttons.
- Settings live in the Plugins dialog's **Config** tab, on a translated
  settings page that also shows what's new. The page remembers the values you
  change there, and the batch capability uses the same settings.
- The result always goes back to OrcaSlicer.
- The "window" capability is only offered by OrcaSlicer builds without plugin
  pages.

### Added
- **Apply to an object on the plate**: pick an object of the project open in
  Prepare; the design is applied to the saved project, which reopens in
  OrcaSlicer with the new parts. OrcaSlicer's plugin API cannot change the
  plate directly, so save the project (Ctrl+S) first; the page tells you when
  it has unsaved changes or objects that are not in the saved file yet.
- **Add as a new object**: the new 3MF opens in OrcaSlicer.
- Files are opened by OrcaSlicer itself (its executable, which hands them to
  the window already open) instead of the system's file association, which may
  point to another program.
- The plugin's messages also go to OrcaSlicer's Python log.

### Removed
- Applying to a different saved `.3mf` file from the page (the plate covers
  it), the "open when done" option and the "use the project folder" link.

## 3.0.1

### Fixed
- Browsing for a file made OrcaSlicer ask about a Python "open" event with no
  target. It came from the pipe Python opens to read the picker's answer; the
  picker now writes its answer to a file in the plugin's data folder, which
  needs no permission. (Starting the picker process may still be asked once.)
- numpy and shapely were imported as soon as the plugin loaded, through the
  color helpers; they now load only when a design is processed.
- The tests and the development server wrote into the real plugin log.

### Added
- A crisp SVG icon for the plugin page tab.
- `docs/orcacloud/`: cover image and texts for publishing on OrcaCloud, the only
  source OrcaSlicer uses for the preview image and changelog of its Plugins
  dialog.

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
