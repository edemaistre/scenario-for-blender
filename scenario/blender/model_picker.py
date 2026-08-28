# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Model picker: a searchable dialog with chips, thumbnails and the description of the highlighted model.

The native EnumProperty dropdown stays available as a fallback (a small icon-only button); the dialog is the
default way to choose among the hundreds of catalog models, like "Choose a Model" in the Scenario web app."""
import logging
import textwrap
import threading

import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, StringProperty

from . import generation, runtime
from ..core.api import model_filter
from ..core.api.assets import download_file

log = logging.getLogger("scenario.picker")

THUMB_LIMIT = 40           # thumbnails fetched per refilter, the rows a user can scroll to before typing again
RECENT_FILE = "recent_models.json"
_ctx = {"lane": "", "records": [], "current": ""}
_pending_thumbs = set()
_pending_lock = threading.Lock()


# -- thumbnails ---------------------------------------------------------------
def _thumb_path(model_id):
    return runtime.paths().cache_dir / "thumbs" / f"{model_id}.jpg"


def _fetch_thumbnail(url, path, model_id):
    try:
        download_file(url, path, timeout=30, retries=1)
    except Exception as err:  # a missing thumbnail is cosmetic; never surface it as a job error
        log.debug("thumbnail %s failed: %s", model_id, err)
    finally:
        with _pending_lock:
            _pending_thumbs.discard(model_id)


def ensure_thumbnail(record):
    """Start a background download of the model thumbnail when it is not cached yet. Returns True when cached."""
    if record is None:
        return False
    path = _thumb_path(record.id)
    if path.exists():
        return True
    url = model_filter.thumbnail_url(record)
    if not url:
        return False
    with _pending_lock:
        if record.id in _pending_thumbs:
            return False
        _pending_thumbs.add(record.id)
    threading.Thread(target=_fetch_thumbnail, args=(url, path, record.id), name=f"scenario-thumb-{record.id}", daemon=True).start()
    return False


def thumbnail_icon(model_id):
    """icon_id of a cached thumbnail, 0 when there is none. Only reads a file that already exists (draw-safe)."""
    path = _thumb_path(model_id)
    if not path.exists():
        return 0
    previews = runtime.previews()
    key = f"thumb:{model_id}"
    if key not in previews:
        try:
            previews.load(key, str(path), 'IMAGE')
        except (KeyError, RuntimeError):
            return 0
    return previews[key].icon_id


# -- list state on the window manager -------------------------------------------
def _recent():
    return model_filter.RecentModels(runtime.paths().state_dir / RECENT_FILE)


def candidate_records(lane):
    records = list(runtime.state.lane_models.get(lane) or [])
    if not records:
        records = [r for r in runtime.state.records.values() if lane in r.lanes]
    return records


def refilter(wm):
    """Rebuild the picker rows from the current query and chip; keeps the highlighted model when it survives."""
    lane = _ctx["lane"]
    filtered = model_filter.filter_records(_ctx["records"], wm.scenario_picker_query, wm.scenario_picker_chip, _recent().ids(lane))
    highlighted = _ctx["current"]
    items = wm.scenario_picker_items
    if 0 <= wm.scenario_picker_index < len(items):
        highlighted = items[wm.scenario_picker_index].model_id or highlighted
    items.clear()
    index = 0
    for position, record in enumerate(filtered):
        item = items.add()
        item.model_id, item.name = record.id, record.name
        item.description = record.short_description or ""
        item.icon_name = model_filter.modality_icon(record)
        if record.id == highlighted:
            index = position
    wm.scenario_picker_index = index
    for record in filtered[:THUMB_LIMIT]:
        ensure_thumbnail(record)
    return filtered


def _on_filter_change(self, context):
    refilter(self)


def prepare(context, lane):
    """Load the lane's models into the picker rows and highlight the current choice."""
    scene = context.scene
    lane = lane or scene.scenario.lane
    lane_state = scene.scenario.lane_state(lane)
    _ctx["lane"] = lane
    _ctx["records"] = candidate_records(lane)
    _ctx["current"] = (lane_state.model_key or lane_state.model_id) if lane_state is not None else ""
    wm = context.window_manager
    wm.scenario_picker_index = -1
    if wm.scenario_picker_query:
        wm.scenario_picker_query = ""  # update callback refilters
    else:
        refilter(wm)
    return wm.scenario_picker_items


def apply_choice(context, lane, index=None):
    """Make the highlighted (or `index`) row the lane's model. Returns the model id, or None when nothing applied."""
    wm = context.window_manager
    items = wm.scenario_picker_items
    index = wm.scenario_picker_index if index is None else index
    if not (0 <= index < len(items)):
        return None
    model_id = items[index].model_id
    lane = lane or _ctx["lane"] or context.scene.scenario.lane
    lane_state = context.scene.scenario.lane_state(lane)
    if lane_state is None:
        return None
    lane_state.model_key = model_id
    valid = [item[0] for item in runtime.enum_items(("models", lane))]
    if model_id in valid:
        if lane_state.model_id != model_id:
            lane_state.model_id = model_id  # the update callback runs on_model_changed
        else:
            generation.on_model_changed(context, lane_state)
    else:
        generation.request_model(model_id)
        runtime.set_message(f"{model_id} is not in this lane's list yet")
    _recent().touch(lane, model_id)
    return model_id


def highlighted_record():
    wm = bpy.context.window_manager
    items = wm.scenario_picker_items
    if 0 <= wm.scenario_picker_index < len(items):
        model_id = items[wm.scenario_picker_index].model_id
        return next((r for r in _ctx["records"] if r.id == model_id), None) or runtime.state.records.get(model_id)
    return None


# -- Blender classes ----------------------------------------------------------------
class ScenarioPickerItem(bpy.types.PropertyGroup):
    model_id: StringProperty()
    name: StringProperty()
    description: StringProperty()
    icon_name: StringProperty(default='QUESTION')


class SCENARIO_UL_models(bpy.types.UIList):
    bl_idname = "SCENARIO_UL_models"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        icon_id = thumbnail_icon(item.model_id)
        if icon_id:
            row.template_icon(icon_value=icon_id, scale=1.0)
        else:
            row.label(text="", icon=item.icon_name or 'QUESTION')
        row.label(text=item.name)
        if item.description:
            muted = row.row(align=True)
            muted.enabled = False
            muted.alignment = 'RIGHT'
            muted.label(text=item.description[:44] + ("..." if len(item.description) > 44 else ""))

    def draw_filter(self, context, layout):
        pass  # search and chips live above the list


class SCENARIO_OT_pick_model(bpy.types.Operator):
    bl_idname = "scenario.pick_model"
    bl_label = "Choose a model"
    bl_description = "Search the Scenario catalog and pick the model for this lane"
    bl_options = {'INTERNAL'}
    lane: StringProperty()

    def invoke(self, context, event):
        prepare(context, self.lane)
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout
        layout.prop(wm, "scenario_picker_query", text="", icon='VIEWZOOM', placeholder="Search models")
        layout.row(align=True).prop(wm, "scenario_picker_chip", expand=True)
        layout.template_list("SCENARIO_UL_models", "", wm, "scenario_picker_items", wm, "scenario_picker_index", rows=10)
        if not wm.scenario_picker_items:
            layout.label(text="No model matches" if _ctx["records"] else "Models are still loading", icon='INFO')
        record = highlighted_record()
        if record is None:
            return
        box = layout.box()
        row = box.row()
        icon_id = thumbnail_icon(record.id)
        if icon_id:
            row.template_icon(icon_value=icon_id, scale=5.0)
        col = row.column(align=True)
        col.label(text=record.name, icon=model_filter.modality_icon(record))
        for line in textwrap.wrap(record.short_description or "", 70)[:3]:
            col.label(text=line)
        muted = col.row()
        muted.enabled = False
        muted.label(text=record.id)

    def execute(self, context):
        model_id = apply_choice(context, self.lane)
        if model_id is None:
            self.report({'WARNING'}, "No model highlighted")
            return {'CANCELLED'}
        record = runtime.state.records.get(model_id)
        self.report({'INFO'}, f"Model: {record.name if record else model_id}")
        return {'FINISHED'}


def draw_model_row(layout, lane_state, lane):
    """Replaces `layout.prop(lane_state, "model_id")`: a wide button opening the picker plus the native dropdown as a fallback."""
    split = layout.split(factor=0.22)
    split.label(text="Model:")
    row = split.row(align=True)
    record = runtime.state.records.get(lane_state.model_id)
    if record is not None:
        label, icon = record.name, model_filter.modality_icon(record)
    else:
        label, icon = ("Choose a model..." if runtime.state.catalog_loaded else "Loading models..."), 'VIEWZOOM'
    op = row.operator("scenario.pick_model", text=label, icon=icon)
    op.lane = lane
    row.prop(lane_state, "model_id", text="", icon_only=True)


CLASSES = (ScenarioPickerItem, SCENARIO_UL_models, SCENARIO_OT_pick_model)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.scenario_picker_items = CollectionProperty(type=ScenarioPickerItem)
    wm.scenario_picker_index = IntProperty(default=0)
    wm.scenario_picker_query = StringProperty(name="Search", description="Filter models by name, description, tag or id",
                                              options={'TEXTEDIT_UPDATE'}, update=_on_filter_change)
    wm.scenario_picker_chip = EnumProperty(name="Filter", items=model_filter.FILTERS, default='all', update=_on_filter_change)


def unregister():
    wm = bpy.types.WindowManager
    for name in ("scenario_picker_chip", "scenario_picker_query", "scenario_picker_index", "scenario_picker_items"):
        if hasattr(wm, name):
            delattr(wm, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
