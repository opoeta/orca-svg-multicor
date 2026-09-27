# -*- coding: utf-8 -*-
"""
The heavy libraries (numpy, shapely, svgelements, mapbox_earcut) and the
standard modules the plugin uses, loaded while OrcaSlicer loads the plugin.

OrcaSlicer audits what a plugin does while its capabilities run, not while
the plugin is being loaded. Two of its rules matter here:

- any path with "conf", "cert" or "secret" in a name is refused, and numpy
  cannot be imported without reading numpy/__config__.py and
  numpy/_core/_ufunc_config.py: imported from a capability, numpy fails with
  "Plugin attempted an audited operation without permission";
- the standard library lives outside the folders a plugin may read freely,
  so a module imported for the first time from a capability makes OrcaSlicer
  ask the user for permission to read it.

So everything is imported once, at load. Outside OrcaSlicer (tests, the dev
server) nothing calls preload() and the light modules stay light.
"""

import os

from .errors import EngineError

error = None      # why preload() failed (the dependencies may not be installed yet)


def preload():
    """Imports everything the capabilities need. True when it all loaded."""
    global error
    try:
        import ctypes  # noqa: F401  host: handing results to the OrcaSlicer window
        import encodings.cp437  # noqa: F401  zipfile: names in 3MF files
        import glob  # noqa: F401  batch
        if os.name == "nt":
            from ctypes import wintypes  # noqa: F401
        import shapely.geometry.polygon  # noqa: F401  colors, when merging
        import shapely.ops  # noqa: F401

        from . import engine  # noqa: F401  numpy, shapely, svgelements, mapbox_earcut
        from . import panel  # noqa: F401
    except Exception as e:  # noqa: BLE001 - the plugin must load anyway
        error = e
        return False
    error = None
    return True


def load_engine():
    """The engine; a clear message when OrcaSlicer refuses to load it now."""
    try:
        from . import engine
    except PermissionError as e:
        raise EngineError("error.deps_blocked") from e
    return engine
