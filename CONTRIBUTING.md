# Contributing

Thanks for helping! Bug reports with the SVG that misbehaves are the most useful
thing you can send: open an issue and attach the file (or a reduced version).

## Translations

1. Copy `src/orca_svg_multicor/locales/en.json` to
   `src/orca_svg_multicor/locales/<code>.json`, using the code OrcaSlicer uses
   for that language (`nl`, `cs`, `zh_TW`, `pt_BR`...). The plugin maps the
   language OrcaSlicer reports to the closest catalog, falling back to English.
2. Translate the values, not the keys. Keep every `{placeholder}` exactly as it
   is, and keep `SVG`, `3MF`, `STL`, `OrcaSlicer`, `Bambu`, `ΔE` and units.
3. Set `"_meta": {"name": "<the language's own name>", "code": "<code>"}`.
4. Use the vocabulary of OrcaSlicer's own translation for that language
   (filament, plate, part, preset, nozzle...), and keep labels short: the panel
   is compact.
5. Run `pytest tests/test_i18n_ui.py`. It checks that no key is missing or extra
   and that the placeholders match English.

Improvements to existing translations are just as welcome.

## Code

```bash
python -m venv .venv
.venv/bin/pip install -e . -r requirements-dev.txt
.venv/bin/pytest
python tools/dev_server.py        # http://127.0.0.1:8765/
```

- Everything except `capabilities.py` must import and run without OrcaSlicer.
- User-facing text goes through i18n keys (`tr("key", **params)` in Python,
  `t('key')` or `data-i18n` in the page). Add new keys to `en.json` and to
  every other catalog (English text is fine as a placeholder; the test will
  tell you if something is missing).
- Geometry changes should come with a test in `tests/test_svg_geometry.py`
  that fails without them.
- The page must not load anything from the network.

## Releasing

Update the version in `pyproject.toml` and `src/orca_svg_multicor/_version.py`,
add a section to `CHANGELOG.md`, then push a tag `vX.Y.Z`. The release workflow
builds the wheel and attaches it to a GitHub release.
