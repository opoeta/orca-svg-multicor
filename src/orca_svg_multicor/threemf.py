# -*- coding: utf-8 -*-
"""
3MF writers.

"orca":     the project layout OrcaSlicer and Bambu Studio write themselves:
            one object whose components point to meshes stored in
            3D/Objects/object_1.model, and Metadata/model_settings.config
            describing each component as a named part with its filament.
            Opening it gives ONE object with one part per color, filaments
            already assigned.
"standard": plain 3MF core + materials, for any slicer: one object made of
            components, each component colored through <basematerials>.
"""

import io
import uuid
import zipfile
from xml.sax.saxutils import escape as _escape

from ._version import __version__

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
BBS_NS = "http://schemas.bambulab.com/package/2021"
MODEL_REL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
</Types>
"""

ROOT_RELS = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="{MODEL_REL}"/>
</Relationships>
"""

IDENTITY_3X4 = "1 0 0 0 1 0 0 0 1 0 0 0"
IDENTITY_4X4 = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"


class Part:
    """One colored piece of the result."""

    def __init__(self, name, V, F, color, extruder=1, subtype="normal_part"):
        self.name = name
        self.V = V
        self.F = F
        self.color = color
        self.extruder = int(extruder)
        self.subtype = subtype


def attr(text):
    """Escapes text for an XML attribute (names typed by the user end up here)."""
    return _escape(str(text), {'"': "&quot;", "'": "&apos;", "\n": "&#10;",
                               "\r": "&#13;", "\t": "&#9;"})


def mesh_xml(V, F, indent="   "):
    """<mesh> element as a string. 4 decimals = 0.1 micron."""
    out = io.StringIO()
    w = out.write
    w(f"{indent}<mesh>\n{indent} <vertices>\n")
    w("".join(f'{indent}  <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>\n'
              for x, y, z in V.tolist()))
    w(f"{indent} </vertices>\n{indent} <triangles>\n")
    w("".join(f'{indent}  <triangle v1="{a}" v2="{b}" v3="{c}"/>\n'
              for a, b, c in F.tolist()))
    w(f"{indent} </triangles>\n{indent}</mesh>\n")
    return out.getvalue()


def _uuid():
    return str(uuid.uuid4())


def application_tag():
    return f"orca-svg-multicor-{__version__}"


# ----------------------------------------------------------------------------
# OrcaSlicer / Bambu Studio project layout
# ----------------------------------------------------------------------------
def orca_model_files(parts, object_name, object_file="3D/Objects/object_1.model"):
    """
    Returns {archive_name: text} for the model part of an Orca project.
    Part ids are 1..N, the assembled object id is N + 1.
    """
    n = len(parts)
    obj_id = n + 1
    sub = io.StringIO()
    w = sub.write
    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w(f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}" '
      f'xmlns:BambuStudio="{BBS_NS}" xmlns:p="{PROD_NS}" requiredextensions="p">\n')
    w(' <metadata name="BambuStudio:3mfVersion">1</metadata>\n')
    w(" <resources>\n")
    for i, part in enumerate(parts, start=1):
        w(f'  <object id="{i}" p:UUID="{_uuid()}" type="model">\n')
        w(mesh_xml(part.V, part.F))
        w("  </object>\n")
    w(" </resources>\n <build/>\n</model>\n")

    root = io.StringIO()
    w = root.write
    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w(f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}" '
      f'xmlns:BambuStudio="{BBS_NS}" xmlns:p="{PROD_NS}" requiredextensions="p">\n')
    w(f' <metadata name="Application">{attr(application_tag())}</metadata>\n')
    w(' <metadata name="BambuStudio:3mfVersion">1</metadata>\n')
    w(f' <metadata name="Title">{attr(object_name)}</metadata>\n')
    w(" <resources>\n")
    w(f'  <object id="{obj_id}" p:UUID="{_uuid()}" type="model">\n   <components>\n')
    for i in range(1, n + 1):
        w(f'    <component p:path="/{object_file}" objectid="{i}" '
          f'p:UUID="{_uuid()}" transform="{IDENTITY_3X4}"/>\n')
    w("   </components>\n  </object>\n </resources>\n")
    w(f' <build p:UUID="{_uuid()}">\n')
    w(f'  <item objectid="{obj_id}" p:UUID="{_uuid()}" '
      f'transform="{IDENTITY_3X4}" printable="1"/>\n')
    w(" </build>\n</model>\n")

    rels = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            f' <Relationship Target="/{object_file}" Id="rel-1" Type="{MODEL_REL}"/>\n'
            f'</Relationships>\n')

    cfg = io.StringIO()
    w = cfg.write
    w('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n')
    w(f'  <object id="{obj_id}">\n')
    w(f'    <metadata key="name" value="{attr(object_name)}"/>\n')
    w(f'    <metadata key="extruder" value="{parts[0].extruder if parts else 1}"/>\n')
    w(f'    <metadata face_count="{sum(len(p.F) for p in parts)}"/>\n')
    for i, part in enumerate(parts, start=1):
        w(f'    <part id="{i}" subtype="{attr(part.subtype)}">\n')
        w(f'      <metadata key="name" value="{attr(part.name)}"/>\n')
        w(f'      <metadata key="matrix" value="{IDENTITY_4X4}"/>\n')
        w(f'      <metadata key="extruder" value="{part.extruder}"/>\n')
        w(f'      <mesh_stat face_count="{len(part.F)}" edges_fixed="0" '
          f'degenerate_facets="0" facets_removed="0" facets_reversed="0" '
          f'backwards_edges="0"/>\n')
        w("    </part>\n")
    w("  </object>\n</config>\n")

    return {
        "3D/3dmodel.model": root.getvalue(),
        "3D/_rels/3dmodel.model.rels": rels,
        object_file: sub.getvalue(),
        "Metadata/model_settings.config": cfg.getvalue(),
    }


def write_orca_project(path, parts, object_name):
    files = orca_model_files(parts, object_name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        for name, text in files.items():
            z.writestr(name, text)


# ----------------------------------------------------------------------------
# plain 3MF (core + materials), for any slicer
# ----------------------------------------------------------------------------
def write_standard_3mf(path, parts, object_name):
    n = len(parts)
    out = io.StringIO()
    w = out.write
    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w(f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}">\n')
    w(f' <metadata name="Application">{attr(application_tag())}</metadata>\n')
    w(f' <metadata name="Title">{attr(object_name)}</metadata>\n')
    w(" <resources>\n")
    mat_id = n + 2
    w(f'  <basematerials id="{mat_id}">\n')
    for part in parts:
        w(f'   <base name="{attr(part.name)}" displaycolor="{part.color.upper()}FF"/>\n')
    w("  </basematerials>\n")
    for i, part in enumerate(parts, start=1):
        w(f'  <object id="{i}" name="{attr(part.name)}" type="model" '
          f'pid="{mat_id}" pindex="{i - 1}">\n')
        w(mesh_xml(part.V, part.F))
        w("  </object>\n")
    agg = n + 1
    w(f'  <object id="{agg}" name="{attr(object_name)}" type="model">\n'
      "   <components>\n")
    for i in range(1, n + 1):
        w(f'    <component objectid="{i}"/>\n')
    w("   </components>\n  </object>\n </resources>\n")
    w(f' <build>\n  <item objectid="{agg}" transform="{IDENTITY_3X4}"/>\n'
      " </build>\n</model>\n")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("3D/3dmodel.model", out.getvalue())


def write_3mf(path, parts, object_name, fmt="orca"):
    if fmt == "standard":
        write_standard_3mf(path, parts, object_name)
    else:
        write_orca_project(path, parts, object_name)
