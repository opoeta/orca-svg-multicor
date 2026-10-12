"""
"Unsaved changes" that are only edited presets do not block applying, as long
as the plate is still what the saved project has.

OrcaSlicer's ProjectDirtyStateManager counts presets edited but not saved as
presets (app.has_unsaved_preset_changes) as unsaved project changes, and
Ctrl+S does not clear that: the project looked unsaved forever.
"""
import types

from orca_svg_multicor import engine as E
from orca_svg_multicor.host import OrcaHost
from orca_svg_multicor.service import Service
from test_engine_service import FakeHost


def _plate_like_file(project, **change):
    """The plate OrcaSlicer would report for the saved project, changed by `change`."""
    items = []
    for f in E.list_objects(project)["objects"]:
        lo, hi = (list(v) for v in f["world_bbox"])
        items.append({"name": f["name"], "bbox": [lo, hi], "parts": f["parts"], "instances": 1,
                      "file": project})
    if "move" in change:
        items[0]["bbox"] = [[x + change["move"] for x in v] for v in items[0]["bbox"]]
    if "parts" in change:
        items[0]["parts"] = change["parts"]
    if change.get("no_box"):
        items[0]["bbox"] = None
    if change.get("extra"):
        items.append(dict(items[0], name="copy"))
    return items


def _match(project, items):
    files = E.list_objects(project)["objects"]
    return E.plate_matches_file(items, files, E.match_plate_objects(items, files))


def test_the_plate_is_compared_with_the_saved_file(bbs_project):
    assert _match(bbs_project, _plate_like_file(bbs_project)) is True
    assert _match(bbs_project, _plate_like_file(bbs_project, move=0.5)) is False     # moved or turned
    assert _match(bbs_project, _plate_like_file(bbs_project, parts=3)) is False      # a part added
    assert _match(bbs_project, _plate_like_file(bbs_project, extra=True)) is False   # an object added
    assert _match(bbs_project, _plate_like_file(bbs_project, no_box=True)) is None   # cannot tell


class PlateHost(FakeHost):
    def __init__(self, plate):
        super().__init__("pt_BR")
        self._plate = plate

    def plate(self):
        return dict(self._plate)


def _service_plate(plate):
    out = []
    svc = Service(PlateHost(plate), (lambda: {}, lambda c: True), out.append, mode="dev")
    svc.handle({"action": "plate"})
    return next(m for m in out if m.get("type") == "plate")


def test_the_page_learns_whether_the_plate_is_saved(bbs_project):
    same = _service_plate({"objects": _plate_like_file(bbs_project), "dirty": True,
                           "presets_dirty": True, "project": bbs_project})
    assert same["plate_saved"] is True and same["objects"][0]["object_id"]
    moved = _service_plate({"objects": _plate_like_file(bbs_project, move=2.0), "dirty": True,
                            "presets_dirty": True, "project": bbs_project})
    assert moved["plate_saved"] is False


def _orca(objects, presets_dirty=True):
    plater = {"is_project_dirty": lambda: True}
    if presets_dirty is not None:
        plater["is_presets_dirty"] = lambda: presets_dirty
    model = types.SimpleNamespace(objects=lambda: objects)
    return types.SimpleNamespace(host=types.SimpleNamespace(
        model=lambda: model, plater=lambda: types.SimpleNamespace(**plater)))


def _object(name, lo, hi):
    box = types.SimpleNamespace(defined=True, min=tuple(lo), max=tuple(hi),
                                size=tuple(b - a for a, b in zip(lo, hi)))
    return types.SimpleNamespace(name=name, bounding_box=lambda: box, volume_count=lambda: 2,
                                 instance_count=lambda: 1, input_file="", is_mm_painted=lambda: False)


def test_orcaslicer_reports_positions_and_unsaved_presets():
    plate = OrcaHost(_orca([_object("Box", (1, 2, 0), (11, 22, 5))])).plate()
    assert plate["dirty"] is True and plate["presets_dirty"] is True
    item = plate["objects"][0]
    assert item["bbox"] == [[1.0, 2.0, 0.0], [11.0, 22.0, 5.0]]
    assert item["size"] == [10.0, 20.0, 5.0] and item["parts"] == 2 and item["instances"] == 1
    # an OrcaSlicer without is_presets_dirty: unknown, and the page keeps asking to save
    older = OrcaHost(_orca([_object("Box", (0, 0, 0), (1, 1, 1))], presets_dirty=None)).plate()
    assert older["presets_dirty"] is None
