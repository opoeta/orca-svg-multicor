# Changelog

## 3.15.0

### Changed
- **New look**: a new plugin icon (filament rings in orange, white and cyan
  with Bezier nodes) on the page tab, the OrcaSlicer Plugins dialog and
  OrcaCloud, and every icon of the page redrawn to match it: navy tiles with
  soft 3D shapes. The views (Result, Original, On the object), *Center*,
  *Fill*, *Fit* and the main button now have icons too, and the main button's
  icon follows the target (apply to an object, or add a new one).
- New cursors for the brush, the bucket and the dropper, with a dark outline
  so they show on any color.

## 3.14.0

### Added
- **Zoom on the view, to paint the details**: hold Alt and turn the mouse
  wheel over the "On the object" view to zoom in or out where the pointer
  is (up to 1200%). To move the zoomed view, drag with the middle button,
  or hold Space and drag (as in Photoshop). The toolbar shows the zoom and
  **Fit** goes back to the whole surface. Only the view changes: what is
  painted and applied is the same.

## 3.13.3

### Changed
- **Ctrl + click copies a color**, as in Photoshop (Alt + click too): with
  the brush or the bucket, Ctrl + click takes the color under the pointer
  without painting, and a plain click or drag always paints. While Ctrl is
  held, the pointer shows the dropper. The dropper button ("Copy a color")
  stays in the toolbar.

## 3.13.2

### Fixed
- **The brush painted with the color under the stroke**, not the color
  picked: picking a color and painting over another area changed nothing.
  The color picked is now the one painted with.
- **The bucket only filled bare areas**: with the design covering the whole
  surface it had nothing to do. It now gives a whole area of one color the
  color picked (or the color next to it).

### Changed
- **Dropper** in the toolbar: click a color of the drawing, and the brush
  and the bucket paint with it (it goes back to the tool used before). The
  color square shows it; "A" (automatic) uses the color next to it, and a
  click on the square goes back to automatic.
- A click with the brush paints a dot.

## 3.13.1

### Fixed
- **The brush did nothing when the stroke started on a bare part of the
  surface** without a color picked first. It now copies the closest color
  there (the color next to it); started on the drawing, it takes that color
  as before.
- The brush size field showed no number (too narrow).

### Changed
- **Own cursors** for the brush and the bucket, and a circle of the brush's
  size that follows the pointer. (OrcaSlicer takes a plugin's icon only for
  its page tab; everything inside the page is drawn by the plugin.)
- **Turn view** has a label next to its icon, and the assistant's last step
  has the same button.

## 3.13.0

### New
- **Paint on the surface** ("On the object", toolbar under the view):
  - **Brush**: drag to paint; the stroke takes the color where it starts,
    copying the color next to it (a click on a color picks it). Brush size
    in mm.
  - **Bucket**: click an area of the surface the design leaves bare (an
    edge strip, a corner, a gap): it is filled with the color touching it
    the most.
  - Painted areas become part of their colors and are printed in the same
    layers as the rest (thickness, first layer). They stay on the surface
    when the design moves. Undo and clear; a new surface or object starts
    clean.

## 3.12.0

### New
- **Fill**: the design covers the whole surface, in proportion and centered,
  with no edge of the surface left over (next to *Center*, and in the
  assistant's last step).
- **The design may go past the surface**, up to covering it and 25% more;
  what goes past its edge is cut off, as before, and moving it chooses what
  shows. The size line says so ("goes past the surface").
- **Free size**: a **Height** of its own next to the width (empty: in
  proportion), and **Shift + drag the corner** to change width and height on
  their own.
- **Turn the view** (↻ above the drawing): "On the object" turns by quarter
  turns, with the sides of the plate around it, the position and the
  assistant's 3×3 grid following the screen. Only the view turns; the
  result does not change.

### Fixed
- The names around the surface could be selected (highlighted) when
  dragging outside the design.

## 3.11.1

### Fixed
- The assistant's Surface list kept the faces of the object chosen before:
  after choosing another object, picking a surface there could select a
  different face of the new object (since 3.9.0). It now follows the
  sidebar.

## 3.11.0

### New
- **Where the face is on the object, in "On the object".** Around the face,
  the whole object as seen from that side (dashed: its tabs, notches and
  outline, which are not on the face itself), the sides of the plate (Front,
  Back, Left, Right, or Top and Bottom for a wall) and which OrcaSlicer view
  shows it the same way, with its shortcut (Ctrl+1 to Ctrl+6, for example
  "Seen from below, like OrcaSlicer's bottom view (Ctrl+2)").

### Changed
- **One permission question per project instead of two.** OrcaSlicer asks
  before a plugin reads a file and asks again before it writes it; the
  project is now opened for reading and writing from the start, since
  applying writes it back. A read-only project is still read; a "No" stays a
  "No". OrcaSlicer still asks once for every new file, and again after every
  update of the plugin (it drops the permissions of the previous version).

## 3.10.2

### Fixed
- **A corner of the surface cut off diagonally** (a lid's rounded corner,
  and the design clipped along it). Meshes exported from CAD often have
  vertices a few ten-thousandths of a millimetre apart where they should be
  one; the triangles of the rounded corner then touched the rest of the face
  only at points, and the corner was dropped as a bit too small to offer.
  The face is now closed by 0.01 mm before it is cut out, which joins them
  and moves its outline by nothing a printer can see.
- Listing the surfaces of an object with many small flat faces (a tray with a
  hundred holes) took about 13 s, with OrcaSlicer frozen; it now takes under
  a second, with the same list.

## 3.10.1

### Fixed
- **"The open project has unsaved changes" even right after Ctrl+S.**
  OrcaSlicer counts presets edited but not saved as presets as unsaved
  project changes, and saving the project does not clear that. When only
  the presets are unsaved and every object on the plate is where the saved
  project has it (same objects, parts and position), applying is allowed;
  the plate line says so. If an object was moved, turned, added or removed
  since the last save, the page still asks to save first, since reopening
  the file would lose it.

## 3.10.0

### Changed
- **The face lying on the bed is chosen at first** (the design in the first
  layers); before, the largest face looking up.
- **The design follows the object as it sits on the plate.** "On the object"
  shows the face as OrcaSlicer does, turned like the object on the plate, and
  the design along the object's edges, its top on the edge closest to up in
  OrcaSlicer's view of that face: the top as seen from above, the walls
  upright, the bottom as in OrcaSlicer's bottom view (the front of the plate
  up). Dragging and resizing work on the turned view.
- On the bottom face, the design used to come upside down compared to
  OrcaSlicer's bottom view. If you set Rotation to 180° to make up for it, set
  it back to 0°.

## 3.9.1

### Fixed
- **Browse… opened in the plugin's data folder.** It now opens where the
  current SVG is, else where the last one came from (remembered across
  restarts), else Downloads.
- **A permission prompt at every "Apply to the plate"**: the backup of the
  project got a new name each time, and OrcaSlicer asked about the project
  and that backup together. The backup is now written on its own in the data
  folder, which needs no permission: the same work asks nothing the second
  time. A test runs every action twice under OrcaSlicer's permission rules to
  keep it that way.
- Choosing an output folder outside the data folder no longer asks to create
  and delete a test file there.
- Reopening the project no longer starts a thread (recent OrcaSlicer builds
  ask before a plugin starts one): the file is handed to OrcaSlicer directly.
- A portable OrcaSlicer, or one started with `--datadir`, keeps the plugin's
  files in its own data folder.

### Changed
- **Installed from OrcaCloud**, OrcaSlicer shows the plugin's image in
  *Plugin Info* and what's new in the *Changelog* tab (it fills them only for
  OrcaCloud plugins), and the Config tab no longer repeats the changelog.
  Installed from a file, the Config tab keeps it, closed. The notes sent to
  OrcaCloud are plain text, one line per item, as the Changelog tab shows
  them.
- The settings are also kept in the data folder, so installing again (or from
  OrcaCloud instead of a file) keeps them; "Restore defaults" still restores
  the defaults.

## 3.9.0

### New
- **A step-by-step assistant** beside the drawing (it opens when you choose
  an SVG; the wand next to *Browse…* brings it back):
  1. **Drawing**: choose which **layers of the file** to use (Illustrator and
     Inkscape layers; a hidden layer leaves the design's size and place as
     they were), the size, and **Mirror** (left ↔ right).
  2. **Colors**: how many colors, as before.
  3. **Filaments**: a filament for each color, and **Drawing colors in the
     project's filaments**: when applying to the plate, each filament used
     takes the color of its part (the largest when parts share one), in the
     project itself. It is also in the sidebar, under *Apply to*.
  4. **Finish**: edges *Detailed*, *Normal* or *Simplified* (presets for
     precision and the cleanup of tips and slivers), the color thickness and,
     on an object, the surface, the first layer, the **position** on the face
     (a 3×3 grid: corners, sides, center) and the rotation.
- The sidebar shows how many layers of the file are in use, with *Choose*,
  and a **Mirror** box under the size.

## 3.8.1

### Fixed
- "Non-manifold edges" on the parts in OrcaSlicer (3.8.0, with the new
  cleanup): the triangulation leaves out points lying on a straight edge,
  and the walls still used them, so their edges did not meet the caps'. The
  walls now follow the points the caps use. Outlines touching at a single
  point (a hole touching another outline, two pieces of a color touching)
  are parted by a hundred-thousandth of a millimeter, so their walls do not
  meet either, even when a slicer merges equal vertices.

## 3.8.0

### Changed
- **Thin details and sharp tips are cleaned by default** (Advanced, "Clean
  details and tips under", 0.4 mm): lines and needle tips a 0.4 mm nozzle
  cannot print go to the neighboring color, without gaps, and corners round
  to 0.2 mm. These are the specks and slivers the slicer printed badly
  between colors. The cleanup now uses a round tool: the previous one grew
  the colors back with pointed corners, which rebuilt the very tips it had
  removed (on a real drawing, what a 0.4 mm nozzle cannot reach went from
  46 mm2 to 34 mm2 before, to 11 mm2 now), and it takes about a second.
  Settings that still had the old default, off, move to 0.4 mm once.

### Fixed
- A color whose pieces touched at a single point was exported as a
  non-manifold mesh (the pieces shared a vertical edge); each piece is now
  its own closed shell.

## 3.7.1

### Fixed
- The objects were doubled on the plate after applying: when the project
  reopens on a plate that has objects, OrcaSlicer asks how to load it and
  preselects the last choice, and "Import geometry only" adds the objects
  again. The plugin cannot answer for you (OrcaSlicer's settings are closed
  to plugins), so the page and the reopening message now say to choose
  "Open as project". Ctrl+Z undoes a doubled import.

## 3.7.0

### Changed
- **Applying to an object on the plate updates the project itself** instead
  of writing a new `*_svg.3mf`: the result replaces the saved project, which
  reopens with the new parts. The previous version is first copied to
  `<OrcaSlicer data folder>/svg_multicor/backups` (the last 20 are kept).
  "Save to" (on the page and in the Config tab) still offers a copy.
  OrcaSlicer's plugin API can only read the plate, so the project file is
  the way in.

### Fixed
- "The plate is empty" when the page was read before a project was opened:
  the page now reads the plate again every few seconds while "An object on
  the plate" is chosen, redrawing only what changed.

## 3.6.0

### Added
- **Reframe the design on the object**: in "On the object", drag the design
  to move it and drag its corner to resize it. It always stays on the
  surface: it cannot be larger than the face nor go past its edges (the
  plugin keeps it inside too). "Center" puts it back in the middle.
- **Thickness in layers**: "Color thickness" in mm or in layers. The layer
  height is the project's (applying to the plate) or the printer profile's
  (a new object), or the one set in Advanced; on the bed the first layer
  height counts for the first of them. The page shows the result in mm.
- **First layer**: on the face lying on the bed, choose whether the design
  starts on the first layer or just above it, the first layer staying the
  object's color.

### Changed
- A design larger than the chosen surface is reduced to fit instead of
  being cut at its edges.

## 3.5.1

### Fixed
- A new object came out at half the size of the drawing: the size was
  "Width 100 mm" by default. The default is now **the file's own size**, and
  settings that still had the old default (width, 100 mm) move to it once.
- The real size of SVGs exported by Adobe Illustrator: they have no width or
  height and keep Illustrator's 72 units per inch, so a 201 mm artboard was
  read as 150.75 mm. Illustrator files are recognized by their metadata.
- The page shows the file's size under "Size" ("File: 201 × 201 mm").

## 3.5.0

### Added
- **How many colors?** Opening an SVG shows the drawing with 2, 3 ... 12
  colors side by side, the count of your filaments marked; a click sets
  "Max. colors". The button next to "Max. colors" brings it back; the Config
  tab can turn it off ("Ask how many colors when opening an SVG").
- **Click a color in the drawing** to choose its filament; Ctrl+click (or
  Shift+click) selects several, and the choice goes to all of them. The
  drawing then shows the filament's color. The same menu has "Other color…"
  and "Do not print".

## 3.4.2

### Fixed
- Reducing the colors lost small but distinct ones: with "Max. colors" below
  the colors of the drawing, the smallest color was always merged into its
  nearest one, so a little green became light blue. Now the pair that changes
  the drawing the least is merged (the area that changes color times how much
  it changes): similar colors, such as two blues, join first, and a small
  distinct color stays.

## 3.4.1

### Fixed
- 3.4.0 reached GitHub but not OrcaCloud: its notes have a semicolon, and the
  publishing step cut the release data there. This version brings the 3.4.0
  changes to OrcaCloud: changing the color of a part (click its color square)
  and whole filament names in the color list.

## 3.4.0

### Added
- **Change the color of a part**: click its color square on the page and pick
  another color. The part prints and shows in that color; its name and
  suggested filament follow the new color unless you changed them, and ↺
  brings the original color back.

### Fixed
- Filament names were cut in the color list: the filament now has a line of
  its own, the details (shapes, tones, background) go below it, and hovering
  shows the whole name.

## 3.3.3

### Changed
- Releases are published on OrcaCloud when the GitHub release is published,
  as OrcaCloud requires: a tag leaves a draft release with the wheel and the
  notes, and publishing it publishes the version on GitHub and OrcaCloud.

## 3.3.2

### Changed
- The Config tab shows what's new in Portuguese when OrcaSlicer is in
  Portuguese (`CHANGELOG.pt-BR.md`, now shipped with the plugin); the other
  languages keep the English changelog.
- The release notes on GitHub and OrcaCloud come in English and Portuguese.
- New screenshots in the documentation.

## 3.3.1

### Fixed
- After restarting OrcaSlicer, reading an SVG failed with "OrcaSlicer blocked
  the plugin's access to a file (Plugin attempted an audited operation without
  permission)". OrcaSlicer refuses plugins any path with "conf" in a name, and
  numpy cannot be imported without reading `numpy/__config__.py`; the plugin
  imported numpy when first needed, which OrcaSlicer audits. It now loads its
  libraries while OrcaSlicer loads the plugin, which OrcaSlicer does not audit,
  so no permission is needed later either for the standard library modules it
  uses. If that still fails, the message says to restart OrcaSlicer.

## 3.3.0

### Added
- **Choose the surface**: applying to an object on the plate now offers every
  flat face of the object, named as you see them on the plate (Top, Bottom,
  Front, Back, Left, Right, Slanted) with their size, and the inside of a
  wall as "Front (inner)" and so on. The design goes on the face you choose,
  along its direction: inlaid into the object or raised from it, clipped to
  the face outline.
- **Rotation** of the design on the face (0, 90, 180 or 270 degrees).
- **On the object** view: the chosen face with the design on it, at the size
  it will have; what falls outside the face is faded, and the size turns
  orange when the design is larger than the face.

### Fixed
- On a hollow object (a tray, a box) the design went on top of the highest
  point, floating over the cavity on the rim. The first surface offered is now
  the largest face looking up that is really on the outside (the floor of the
  tray), and the faces where two parts of the object touch are not offered.
- "Inlaid" and "raised" no longer say "the top", and the design no longer
  follows the object's bounding box, which on a rotated or irregular object
  was not a surface of it.

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
