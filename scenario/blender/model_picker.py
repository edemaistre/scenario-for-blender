# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Model picker: Scenario's "Choose a Model" dialog inside Blender.

Modality tabs (Image, Video, Audio, 3D) with Scenario's icons, the category chips of the web app per tab (Generate,
Edit, Upscale... / Speech, Music, SFX... / Splat, Remesh, Retexture...), a search field, the list with thumbnails and
the description of the highlighted model. LoRAs and deprecated models never show. Picking a model from another tab
than the lane's moves the scene to that modality's lane. The native dropdown stays as a small fallback button.

Layout: the tabs and the chips are compact centred groups (each button as wide as its icon and word, the group in the
middle of the dialog, like Scenario's "Choose a Model" and the lane tabs of the sidebar); the search field, the list and
the highlighted model's box stay full width."""
import logging
import textwrap
import threading

import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, StringProperty

from . import generation, icons, runtime
from ..core.api import model_filter
from ..core.api.assets import download_file
from ..core.api.catalog import PATINA_MODELS

log = logging.getLogger("scenario.picker")

THUMB_LIMIT = 40           # thumbnails fetched per refilter, the rows a user can scroll to before typing again
CHIPS_PER_ROW = 6          # more category chips than this wrap onto two centred rows
RECENT_FILE = "recent_models.json"
_ctx = {"lane": "", "records": [], "current": "", "material_only": False}
_pending_thumbs = set()
_pending_lock = threading.Lock()
_enum_cache = {}           # keeps enum item tuples alive for Blender


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


# -- taxonomy helpers -----------------------------------------------------------------
def modality_for_lane(lane):
    return model_filter.LANE_MODALITY.get(lane, "image")


def candidate_records(modality):
    """Every visible catalog model of a modality (LoRAs and deprecated out), plus the lane lists (curated first)."""
    records = [r for r in runtime.state.records.values() if model_filter.visible(r) and model_filter.modality_of(r) == modality]
    seen = {r.id for r in records}
    for lane, lane_modality in model_filter.LANE_MODALITY.items():
        if lane_modality != modality:
            continue
        for record in runtime.state.lane_models.get(lane) or []:
            if record.id not in seen and model_filter.visible(record):
                records.append(record)
                seen.add(record.id)
    return records


def _recent():
    return model_filter.RecentModels(runtime.paths().state_dir / RECENT_FILE)


def _modality_items(self, context):
    key = "modalities"
    items = _enum_cache.get(key)
    if items is None:
        items = []
        for index, (ident, label, icon_name) in enumerate(model_filter.MODALITIES):
            value = icons.icon(icon_name)
            items.append((ident, label, f"{label} models", value if value else icons.builtin(icon_name), index))
        _enum_cache[key] = items
    return items


def _category_items(self, context):
    wm = getattr(context, "window_manager", None) or bpy.context.window_manager
    modality = getattr(wm, "scenario_picker_modality", "image") or "image"
    key = ("categories", modality)
    items = _enum_cache.get(key)
    if items is None:
        items = [(ident, label, f"{label} models", 'NONE', index) for index, (ident, label) in enumerate(model_filter.category_items(modality))]
        _enum_cache[key] = items
    return items


def refilter(wm):
    """Rebuild the picker rows from the tab, chip and query; keeps the highlighted model when it survives."""
    modality = wm.scenario_picker_modality
    category = wm.scenario_picker_category
    if _ctx["material_only"]:
        filtered = [r for r in _ctx["records"] if model_filter.matches(r, wm.scenario_picker_query)]
    else:
        filtered = model_filter.filter_records(_ctx["records"], modality, category, wm.scenario_picker_query, _recent().ids(_ctx["lane"]))
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
        item.modality = model_filter.modality_of(record) or "image"
        if record.id == highlighted:
            index = position
    wm.scenario_picker_index = index
    for record in filtered[:THUMB_LIMIT]:
        ensure_thumbnail(record)
    return filtered


def _on_modality_change(self, context):
    _ctx["records"] = candidate_records(self.scenario_picker_modality)
    _enum_cache.pop(("categories", self.scenario_picker_modality), None)
    self.scenario_picker_category = 'all'  # its update refilters


def _on_filter_change(self, context):
    refilter(self)


def prepare(context, lane):
    """Open the picker on the lane's modality tab with the lane's model highlighted."""
    scene = context.scene
    lane = lane or scene.scenario.lane
    lane_state = scene.scenario.lane_state(lane)
    wm = context.window_manager
    _ctx["lane"] = lane
    _ctx["current"] = (lane_state.model_key or lane_state.model_id) if lane_state is not None else ""
    _ctx["material_only"] = lane == "material"
    modality = modality_for_lane(lane)
    if _ctx["material_only"]:
        _ctx["records"] = [r for r in runtime.state.records.values() if r.id in PATINA_MODELS] or list(runtime.state.lane_models.get("material") or [])
    else:
        _ctx["records"] = candidate_records(modality)
    wm.scenario_picker_index = -1
    if wm.scenario_picker_modality != modality:
        wm.scenario_picker_modality = modality  # update: records + category reset + refilter
    elif wm.scenario_picker_category != 'all':
        wm.scenario_picker_category = 'all'
    if wm.scenario_picker_query:
        wm.scenario_picker_query = ""  # update callback refilters
    else:
        refilter(wm)
    return wm.scenario_picker_items


def _target_lane(scene, record, lane):
    """The lane a chosen model belongs to: the current lane when the modality matches, else the modality's base lane
    (3D-to-3D models go to the Edit 3D lane / mode)."""
    modality = model_filter.modality_of(record)
    caps = set(record.capabilities)
    if modality == "3d" and "3d23d" in caps and "txt23d" not in caps and "img23d" not in caps:
        return "edit3d"
    if modality_for_lane(lane) == modality and not (lane == "edit3d" and "3d23d" not in caps):
        return lane
    return model_filter.BASE_LANE.get(modality, lane)


def _enum_has(struct, prop_name, value):
    try:
        items = {item.identifier for item in struct.bl_rna.properties[prop_name].enum_items}
    except (KeyError, AttributeError):
        return False
    if items:
        return value in items
    # a dynamic enum (items callback, like the lane tabs with their icons) reports no RNA items: probe with an assignment
    try:
        current = getattr(struct, prop_name)
        setattr(struct, prop_name, value)
        ok = getattr(struct, prop_name) == value
        if ok and current != value:
            setattr(struct, prop_name, current)
        return ok
    except TypeError:
        return False


def _show_lane(scene, target, record):
    """Make the target lane visible: switch the tab; for 3D pick the input mode the model needs."""
    scenario = scene.scenario
    if _enum_has(scenario, "lane", target):
        if scenario.lane != target:
            scenario.lane = target
    elif target == "edit3d" and _enum_has(scenario, "lane", "3d"):
        scenario.lane = "3d"
        if _enum_has(scenario, "three_d_mode", 'EDIT'):
            scenario.three_d_mode = 'EDIT'
    if target == "3d":
        caps = set(record.capabilities)
        if "txt23d" in caps and "img23d" not in caps:
            mode = 'TEXT'
        elif any(h in (record.id + record.name).lower() for h in ("multi", "multiview")):
            mode = 'MULTI'
        else:
            mode = 'IMAGE'
        if _enum_has(scenario, "three_d_mode", mode) and scenario.three_d_mode != mode:
            scenario.three_d_mode = mode


def apply_choice(context, lane, index=None):
    """Make the highlighted (or `index`) row the model of the lane it belongs to. Returns (model_id, lane) or (None, None)."""
    wm = context.window_manager
    items = wm.scenario_picker_items
    index = wm.scenario_picker_index if index is None else index
    if not (0 <= index < len(items)):
        return None, None
    model_id = items[index].model_id
    record = next((r for r in _ctx["records"] if r.id == model_id), None) or runtime.state.records.get(model_id)
    lane = lane or _ctx["lane"] or context.scene.scenario.lane
    scene = context.scene
    target = _target_lane(scene, record, lane) if record is not None else lane
    lane_state = scene.scenario.lane_state(target) or scene.scenario.lane_state(lane)
    if lane_state is None:
        return None, None
    if record is not None:
        _show_lane(scene, target, record)
    lane_state.model_key = model_id
    valid = [item[0] for item in runtime.enum_items(("models", target))]
    if model_id in valid:
        if lane_state.model_id != model_id:
            lane_state.model_id = model_id  # the update callback runs on_model_changed
        else:
            generation.on_model_changed(context, lane_state)
    else:
        generation.request_model(model_id)
        runtime.set_message(f"{record.name if record else model_id} chosen; its list entry appears once the schema is loaded")
    _recent().touch(lane, model_id)
    if target != lane:
        _recent().touch(target, model_id)
    return model_id, target


def highlighted_record():
    wm = bpy.context.window_manager
    items = wm.scenario_picker_items
    if 0 <= wm.scenario_picker_index < len(items):
        model_id = items[wm.scenario_picker_index].model_id
        return next((r for r in _ctx["records"] if r.id == model_id), None) or runtime.state.records.get(model_id)
    return None


def category_labels(record):
    labels = dict(model_filter.category_items(model_filter.modality_of(record)))
    return ", ".join(labels.get(c, c) for c in sorted(model_filter.categories_of(record)))


# -- dialog layout --------------------------------------------------------------------
def chip_rows(chips, per_row=CHIPS_PER_ROW):
    """The category chips as one row, or two balanced rows when there are more than `per_row` (Image and Video have 8,
    3D has 9, Audio 5)."""
    chips = list(chips)
    if len(chips) <= per_row:
        return [chips]
    half = (len(chips) + 1) // 2
    return [chips[:half], chips[half:]]


def _centered_cells(parent, struct, prop, values):
    """A continuous full-width segmented control: equal cells, no gaps, each with the enum item's icon and label."""
    from .panels import equal_segments

    equal_segments(parent, struct, prop, values)


def draw_filters(layout, wm):
    """Modality tabs and category chips as justified rows with the icon glued to its label and the pair centred in
    each cell. The tab icon comes from the enum item itself (Scenario's PNG, or the built-in fallback when headless)."""
    col = layout.column()
    _centered_cells(col, wm, "scenario_picker_modality", [ident for ident, _label, _icon in model_filter.MODALITIES])
    col.separator()
    chips = col.column(align=True)
    for chip_row in chip_rows(model_filter.category_items(wm.scenario_picker_modality)):
        _centered_cells(chips, wm, "scenario_picker_category", [ident for ident, _label in chip_row])


# -- Blender classes ----------------------------------------------------------------
class ScenarioPickerItem(bpy.types.PropertyGroup):
    model_id: StringProperty()
    name: StringProperty()
    description: StringProperty()
    modality: StringProperty(default="image")


class SCENARIO_UL_models(bpy.types.UIList):
    bl_idname = "SCENARIO_UL_models"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        icon_id = thumbnail_icon(item.model_id)
        if icon_id:
            row.template_icon(icon_value=icon_id, scale=1.0)
        else:
            row.label(text="", **icons.kwargs(item.modality))
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
    bl_description = "Search the Scenario catalog by modality and category and pick the model"
    bl_options = {'INTERNAL'}
    lane: StringProperty()

    def invoke(self, context, event):
        prepare(context, self.lane)
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout
        layout.separator()  # breathing room under the title, as in the composer
        if _ctx["material_only"]:
            header = layout.row()
            header.alignment = 'CENTER'
            header.label(text="Materials: PATINA models", icon='MATERIAL')
        else:
            draw_filters(layout, wm)
        layout.separator()
        layout.prop(wm, "scenario_picker_query", text="", icon='VIEWZOOM', placeholder="Search models")
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
        col.label(text=record.name, **icons.kwargs(model_filter.modality_of(record) or "image"))
        cats = category_labels(record)
        if cats:
            col.label(text=cats)
        for line in textwrap.wrap(record.short_description or "", 70)[:3]:
            col.label(text=line)
        muted = col.row()
        muted.enabled = False
        muted.label(text=record.id)

    def execute(self, context):
        model_id, target = apply_choice(context, self.lane)
        if model_id is None:
            self.report({'WARNING'}, "No model highlighted")
            return {'CANCELLED'}
        record = runtime.state.records.get(model_id)
        where = "" if target == (self.lane or target) else f" (in {target.replace('_', ' ')})"
        self.report({'INFO'}, f"Model: {record.name if record else model_id}{where}")
        return {'FINISHED'}


def draw_model_row(layout, lane_state, lane):
    """A "Model" section (like Clip to render / Camera path): a header, then a wide button opening the picker
    (its icon next to the model name) and the native dropdown at the right as a fallback."""
    box = layout.box()
    box.label(text="Model", icon='NODE_MATERIAL')
    record = runtime.state.records.get(lane_state.model_id)
    if record is not None:
        label = record.name
        icon_kwargs = icons.kwargs(model_filter.modality_of(record) or modality_for_lane(lane))
    else:
        label = "Choose a model..." if runtime.state.catalog_loaded else "Loading models..."
        icon_kwargs = {"icon": 'VIEWZOOM'}
    row = box.row(align=True)
    area = row.split(factor=0.9, align=True)
    area.operator("scenario.pick_model", text=label, **icon_kwargs).lane = lane
    area.prop(lane_state, "model_id", text="", icon_only=True)


CLASSES = (ScenarioPickerItem, SCENARIO_UL_models, SCENARIO_OT_pick_model)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _enum_cache.clear()
    wm = bpy.types.WindowManager
    wm.scenario_picker_items = CollectionProperty(type=ScenarioPickerItem)
    wm.scenario_picker_index = IntProperty(default=0)
    wm.scenario_picker_query = StringProperty(name="Search", description="Filter models by name, description, tag or id",
                                              options={'TEXTEDIT_UPDATE'}, update=_on_filter_change)
    wm.scenario_picker_modality = EnumProperty(name="Modality", items=_modality_items, update=_on_modality_change)
    wm.scenario_picker_category = EnumProperty(name="Category", items=_category_items, update=_on_filter_change)


def unregister():
    wm = bpy.types.WindowManager
    for name in ("scenario_picker_category", "scenario_picker_modality", "scenario_picker_query", "scenario_picker_index", "scenario_picker_items"):
        if hasattr(wm, name):
            delattr(wm, name)
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass  # already unregistered (tests swap the module in place)
    _enum_cache.clear()
