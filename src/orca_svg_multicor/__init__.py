"""
SVG Multicolor, a plugin for OrcaSlicer.

Splits a multicolor SVG into one part per color, aligned in the same frame,
either as a new 3MF or as parts added inside an object of a saved project.

Inside OrcaSlicer the `orca` module exists and the plugin registers itself.
Anywhere else (tests, the dev server) the package imports cleanly without it.
Heavy libraries (numpy, shapely) are only imported when first needed, so
loading the plugin does not slow OrcaSlicer's startup.
"""

from ._version import __version__

try:
    import orca  # provided by OrcaSlicer's embedded interpreter
except ImportError:  # pragma: no cover - outside OrcaSlicer
    orca = None

if orca is not None:
    from . import capabilities as _capabilities

    @orca.plugin
    class SvgMulticolorPlugin(orca.base):
        """Registers the capabilities of this package."""

        def register_capabilities(self) -> None:
            _capabilities.register_all(orca)

__all__ = ["__version__"]
