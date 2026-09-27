# -*- coding: utf-8 -*-
"""
Reading and editing saved 3MF projects.

OrcaSlicer and Bambu Studio store every object as a list of components whose
meshes live in separate files (3D/Objects/object_N.model, production
extension), and describe the parts in Metadata/model_settings.config with
<part id=...> entries. Older files and other slicers keep the mesh inline in
3D/3dmodel.model. Both layouts are supported.

Files are edited by inserting text, never by re-serializing them: OrcaSlicer's
parser matches attribute names literally ("p:path", "p:UUID"), and an XML
library round trip would rename those prefixes (ns0:, ns1:), silently breaking
the project.
"""

import json
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from .colors import normalize_hex
from .errors import ProjectError
from .threemf import CORE_NS, IDENTITY_4X4, PROD_NS, mesh_xml

_C = "{%s}" % CORE_NS
_P = "{%s}" % PROD_NS
CONFIG = "Metadata/model_settings.config"
PROJECT_SETTINGS = "Metadata/project_settings.config"


def _norm(path):
    return path.lstrip("/")


def _matrix(text):
    """3MF 3x4 transform string -> 4x4 numpy matrix (column vectors)."""
    if not text:
        return np.eye(4)
    v = [float(x) for x in text.split()]
    if len(v) != 12:
        return np.eye(4)
    m = np.eye(4)
    # 3MF stores the matrix row-major for row vectors: [x y z 1] * M
    m[:3, 0] = v[0:3]
    m[:3, 1] = v[3:6]
    m[:3, 2] = v[6:9]
    m[:3, 3] = v[9:12]
    return m


class ProjectObject:
    def __init__(self, oid, name, kind):
        self.id = oid
        self.name = name
        self.kind = kind            # "mesh" or "components"
        self.parts = 0
        self.triangles = 0
        self.bbox = None            # (min xyz, max xyz) in object coordinates
        self.item_matrix = None     # 4x4, object -> plate (first instance)

    @property
    def size(self):
        if self.bbox is None:
            return None
        lo, hi = self.bbox
        return tuple(float(x) for x in (hi - lo))

    def as_dict(self):
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "parts": self.parts, "triangles": self.triangles,
                "size": list(self.size) if self.size else None}


class Project:
    """A 3MF project loaded in memory."""

    def __init__(self, path):
        self.path = path
        try:
            with zipfile.ZipFile(path) as z:
                self.infos = z.infolist()
                self.files = {i.filename: z.read(i.filename) for i in self.infos}
        except (zipfile.BadZipFile, OSError) as e:
            raise ProjectError("error.project_read", detail=str(e)[:200]) from e
        self.root_name = self._find_root()
        self._trees = {}
        self._config = self._read_config()

    # ------------------------------------------------------------------ io
    def _find_root(self):
        rels = self.files.get("_rels/.rels")
        if rels:
            try:
                for rel in ET.fromstring(rels):
                    if rel.get("Type", "").endswith("/3dmodel"):
                        name = _norm(rel.get("Target", ""))
                        if name in self.files:
                            return name
            except ET.ParseError:
                pass
        for name in self.files:
            if name.lower().endswith("3dmodel.model"):
                return name
        raise ProjectError("error.project_no_model")

    def tree(self, name):
        name = _norm(name)
        t = self._trees.get(name)
        if t is None:
            if name not in self.files:
                raise ProjectError("error.project_missing_part", name=name)
            try:
                t = ET.fromstring(self.files[name])
            except ET.ParseError as e:
                raise ProjectError("error.project_read", detail=str(e)[:200]) from e
            self._trees[name] = t
        return t

    def text(self, name):
        return self.files[_norm(name)].decode("utf-8")

    def _read_config(self):
        data = self.files.get(CONFIG)
        if not data:
            return None
        try:
            return ET.fromstring(data)
        except ET.ParseError:
            return None

    # ------------------------------------------------------------- queries
    def _object_el(self, model_name, oid):
        res = self.tree(model_name).find(_C + "resources")
        if res is None:
            return None
        for o in res.findall(_C + "object"):
            if o.get("id") == str(oid):
                return o
        return None

    def _config_object(self, oid):
        if self._config is None:
            return None
        for o in self._config.findall("object"):
            if o.get("id") == str(oid):
                return o
        return None

    def _config_name(self, oid):
        o = self._config_object(oid)
        if o is None:
            return None
        for m in o.findall("metadata"):
            if m.get("key") == "name":
                return m.get("value")
        return None

    def _collect(self, model_name, obj_el, matrix, out, depth=0):
        """Appends (V transformed, F) of every mesh under obj_el to `out`."""
        if depth > 16:
            return
        mesh = obj_el.find(_C + "mesh")
        if mesh is not None:
            vs = mesh.find(_C + "vertices")
            ts = mesh.find(_C + "triangles")
            if vs is None or ts is None:
                return
            V = np.array([(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                          for v in vs], dtype=float).reshape(-1, 3)
            if len(V):
                V = V @ matrix[:3, :3].T + matrix[:3, 3]
            F = np.array([(int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))) for t in ts],
                         dtype=np.int64).reshape(-1, 3)
            if np.linalg.det(matrix[:3, :3]) < 0:        # a mirror flips the winding
                F = F[:, ::-1]
            out.append((V, F))
            return
        comps = obj_el.find(_C + "components")
        if comps is None:
            return
        for c in comps.findall(_C + "component"):
            sub_model = _norm(c.get(_P + "path") or "") or model_name
            sub = self._object_el(sub_model, c.get("objectid"))
            if sub is None:
                continue
            m = matrix @ _matrix(c.get("transform"))
            self._collect(sub_model, sub, m, out, depth + 1)

    def objects(self):
        """Objects placed on the build plate(s), with their size."""
        root = self.tree(self.root_name)
        build = root.find(_C + "build")
        placed, matrices = [], {}
        if build is not None:
            for item in build.findall(_C + "item"):
                oid = item.get("objectid")
                if oid not in placed:
                    placed.append(oid)
                    matrices[oid] = _matrix(item.get("transform"))
        out = []
        for oid in placed:
            el = self._object_el(self.root_name, oid)
            if el is None:
                continue
            comps = el.find(_C + "components")
            kind = "components" if comps is not None else "mesh"
            name = (self._config_name(oid) or el.get("name")
                    or f"#{oid}")
            obj = ProjectObject(oid, name, kind)
            obj.item_matrix = matrices.get(oid)
            meshes = []
            self._collect(self.root_name, el, np.eye(4), meshes)
            if not meshes:
                continue
            allv = np.concatenate([m[0] for m in meshes if len(m[0])]) \
                if any(len(m[0]) for m in meshes) else np.zeros((0, 3))
            obj.triangles = sum(len(m[1]) for m in meshes)
            obj.parts = len(comps.findall(_C + "component")) if comps is not None else 1
            if len(allv):
                obj.bbox = (allv.min(axis=0), allv.max(axis=0))
            out.append(obj)
        return out

    def object(self, oid):
        for o in self.objects():
            if o.id == str(oid):
                return o
        raise ProjectError("error.project_no_object", id=oid)

    def object_mesh(self, oid):
        """(V, F) of object `oid`, every component merged, in object coordinates."""
        el = self._object_el(self.root_name, oid)
        if el is None:
            raise ProjectError("error.project_no_object", id=oid)
        meshes = []
        self._collect(self.root_name, el, np.eye(4), meshes)
        if not meshes:
            raise ProjectError("error.project_no_mesh")
        Vs, Fs, off = [], [], 0
        for V, F in meshes:
            Vs.append(V)
            Fs.append(F + off)
            off += len(V)
        return np.concatenate(Vs), np.concatenate(Fs)

    def filaments(self):
        """
        Filaments configured in the project ([{n, name, color}]), from
        Metadata/project_settings.config. OrcaSlicer resets a part to filament
        1 when its number is above this count. Empty when unknown.
        """
        data = self.files.get(PROJECT_SETTINGS)
        if not data:
            return []
        try:
            cfg = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return []
        colors = cfg.get("filament_colour") or []
        names = cfg.get("filament_settings_id") or []
        if isinstance(colors, str):
            colors = colors.split(";")
        if isinstance(names, str):
            names = names.split(";")
        count = max(len(colors), len(names))
        return [{"n": i + 1,
                 "name": str(names[i]) if i < len(names) else f"#{i + 1}",
                 "color": (normalize_hex(str(colors[i])) or "") if i < len(colors) else ""}
                for i in range(count)]

    # --------------------------------------------------------------- edits
    def _max_id(self):
        best = 0
        for name, data in self.files.items():
            if not name.lower().endswith(".model"):
                continue
            for m in re.finditer(rb'<object\b[^>]*?\bid\s*=\s*"(\d+)"', data):
                best = max(best, int(m.group(1)))
        return best

    @staticmethod
    def _prefix(text, ns):
        m = re.search(r'xmlns:([A-Za-z_][\w.-]*)\s*=\s*"%s"' % re.escape(ns), text)
        return m.group(1) if m else None

    @staticmethod
    def _object_span(text, oid):
        """(start, end) of the <object id="oid"> ... </object> block."""
        m = re.search(r'<object\b[^>]*?\bid\s*=\s*"%s"[^>]*>' % re.escape(str(oid)), text)
        if not m:
            return None
        end = text.find("</object>", m.end())
        if end < 0:
            return None
        return m.start(), end + len("</object>")

    def add_parts(self, oid, parts):
        """
        Adds `parts` (threemf.Part, vertices in object coordinates) to object
        `oid` as new parts with their names and filaments.
        """
        oid = str(oid)
        root_text = self.text(self.root_name)
        span = self._object_span(root_text, oid)
        if span is None:
            raise ProjectError("error.project_no_object", id=oid)
        block = root_text[span[0]:span[1]]
        if "<components" in block:
            self._add_as_components(oid, parts, root_text, span)
        else:
            self._add_to_inline_mesh(oid, parts, root_text, span)

    def _add_as_components(self, oid, parts, root_text, span):
        root_el = self._object_el(self.root_name, oid)
        comps = root_el.find(_C + "components")
        existing = comps.findall(_C + "component")
        first_path = None
        for c in existing:
            if c.get(_P + "path"):
                first_path = _norm(c.get(_P + "path"))
                break

        next_id = self._max_id() + 1
        ids = list(range(next_id, next_id + len(parts)))

        if first_path:
            # meshes go to the file that already holds this object's meshes
            sub_text = self.text(first_path)
            p_sub = self._prefix(sub_text, PROD_NS)
            objs = "".join(self._object_xml(i, part, p_sub) for i, part in zip(ids, parts))
            cut = sub_text.rfind("</resources>")
            if cut < 0:
                raise ProjectError("error.project_read", detail=first_path)
            self.files[first_path] = (sub_text[:cut] + objs + sub_text[cut:]).encode("utf-8")
            p_root = self._prefix(root_text, PROD_NS) or "p"
            comp_xml = "".join(
                f'    <component {p_root}:path="/{first_path}" objectid="{i}" '
                f'{p_root}:UUID="{uuid.uuid4()}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
                for i in ids)
            if not self._prefix(root_text, PROD_NS):
                root_text = root_text.replace(
                    "<model ", f'<model xmlns:p="{PROD_NS}" ', 1)
                span = self._object_span(root_text, oid)
            block = root_text[span[0]:span[1]]
            k = block.rfind("</components>")
            new_block = block[:k] + comp_xml + "   " + block[k:]
            root_text = root_text[:span[0]] + new_block + root_text[span[1]:]
        else:
            # components in the same file: new objects must come before the
            # object that references them
            p_root = self._prefix(root_text, PROD_NS)
            objs = "".join(self._object_xml(i, part, p_root) for i, part in zip(ids, parts))
            comp_xml = "".join(
                f'    <component objectid="{i}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
                for i in ids)
            block = root_text[span[0]:span[1]]
            k = block.rfind("</components>")
            new_block = block[:k] + comp_xml + "   " + block[k:]
            root_text = (root_text[:span[0]] + objs + "  " + new_block
                         + root_text[span[1]:])

        self.files[self.root_name] = root_text.encode("utf-8")
        self._trees.clear()

        existing_ids = [c.get("objectid") for c in existing]
        self._config_add_parts(oid, existing_ids, list(zip(ids, parts)))

    @staticmethod
    def _object_xml(oid, part, prefix):
        uid = f' {prefix}:UUID="{uuid.uuid4()}"' if prefix else ""
        return (f'  <object id="{oid}"{uid} type="model">\n'
                + mesh_xml(part.V, part.F) + "  </object>\n")

    def _add_to_inline_mesh(self, oid, parts, root_text, span):
        """Legacy layout: parts appended to the object's own mesh."""
        el = self._object_el(self.root_name, oid)
        mesh = el.find(_C + "mesh")
        if mesh is None:
            raise ProjectError("error.project_no_mesh")
        n_vert = len(mesh.find(_C + "vertices"))
        n_tri = len(mesh.find(_C + "triangles"))

        verts, tris, ranges = [], [], []
        v_off, t_off = n_vert, n_tri
        for part in parts:
            verts.append("".join(f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>\n'
                                 for x, y, z in part.V.tolist()))
            tris.append("".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n'
                                for a, b, c in (part.F + v_off).tolist()))
            ranges.append((t_off, t_off + len(part.F) - 1, part))
            v_off += len(part.V)
            t_off += len(part.F)

        block = root_text[span[0]:span[1]]
        kv = block.rfind("</vertices>")
        block = block[:kv] + "".join(verts) + block[kv:]
        kt = block.rfind("</triangles>")
        block = block[:kt] + "".join(tris) + block[kt:]
        root_text = root_text[:span[0]] + block + root_text[span[1]:]
        self.files[self.root_name] = root_text.encode("utf-8")
        self._trees.clear()
        self._config_add_volumes(oid, el.get("name"), n_tri, ranges)

    # ------------------------------------------------------ model settings
    def _config_root(self):
        if self._config is None:
            self._config = ET.Element("config")
        return self._config

    def _config_obj(self, oid, name):
        cfg = self._config_root()
        node = self._config_object(oid)
        if node is None:
            node = ET.Element("object", {"id": str(oid)})
            ET.SubElement(node, "metadata", {"key": "name", "value": name or f"#{oid}"})
            ET.SubElement(node, "metadata", {"key": "extruder", "value": "1"})
            # objects must come before plates in model_settings.config
            first_plate = next((i for i, ch in enumerate(list(cfg)) if ch.tag == "plate"),
                               None)
            if first_plate is None:
                cfg.append(node)
            else:
                cfg.insert(first_plate, node)
        return node

    @staticmethod
    def _part_node(tag, attrs, part):
        node = ET.Element(tag, attrs)
        ET.SubElement(node, "metadata", {"key": "name", "value": part.name})
        ET.SubElement(node, "metadata", {"key": "matrix", "value": IDENTITY_4X4})
        ET.SubElement(node, "metadata", {"key": "extruder", "value": str(part.extruder)})
        return node

    def _config_add_parts(self, oid, existing_ids, new):
        el = self._object_el(self.root_name, oid)
        name = self._config_name(oid) or (el.get("name") if el is not None else None)
        node = self._config_obj(oid, name)
        have = {p.get("id") for p in node.findall("part")}
        for k, cid in enumerate(existing_ids, start=1):
            if cid not in have:
                p = ET.SubElement(node, "part", {"id": str(cid), "subtype": "normal_part"})
                ET.SubElement(p, "metadata", {"key": "name",
                                              "value": f"{name or 'part'} {k}"})
                ET.SubElement(p, "metadata", {"key": "matrix", "value": IDENTITY_4X4})
        for pid, part in new:
            p = self._part_node("part", {"id": str(pid), "subtype": part.subtype}, part)
            ET.SubElement(p, "mesh_stat", {"face_count": str(len(part.F)),
                                           "edges_fixed": "0", "degenerate_facets": "0",
                                           "facets_removed": "0", "facets_reversed": "0",
                                           "backwards_edges": "0"})
            node.append(p)
        added = sum(len(part.F) for _pid, part in new)
        for m in node.findall("metadata"):
            if m.get("face_count") is not None:
                try:
                    m.set("face_count", str(int(m.get("face_count")) + added))
                except ValueError:
                    pass
        self._store_config()

    def _config_add_volumes(self, oid, name, n_tri0, ranges):
        node = self._config_obj(oid, name)
        if not node.findall("volume"):
            v0 = ET.SubElement(node, "volume", {"firstid": "0", "lastid": str(n_tri0 - 1)})
            ET.SubElement(v0, "metadata", {"key": "name", "value": name or "base"})
            ET.SubElement(v0, "metadata", {"key": "volume_type", "value": "ModelPart"})
            ET.SubElement(v0, "metadata", {"key": "matrix", "value": IDENTITY_4X4})
            ET.SubElement(v0, "metadata", {"key": "extruder", "value": "1"})
        for first, last, part in ranges:
            v = self._part_node("volume", {"firstid": str(first), "lastid": str(last)}, part)
            ET.SubElement(v, "metadata", {"key": "volume_type", "value": "ModelPart"})
            node.append(v)
        self._store_config()

    def _store_config(self):
        cfg = self._config_root()
        ET.indent(cfg, space="  ")
        self.files[CONFIG] = ET.tostring(cfg, encoding="utf-8", xml_declaration=True)

    # ---------------------------------------------------------------- save
    def save(self, out_path):
        order = [i.filename for i in self.infos]
        for name in self.files:
            if name not in order:
                order.append(name)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name in order:
                z.writestr(name, self.files[name])

