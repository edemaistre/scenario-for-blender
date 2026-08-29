# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level property groups: one lane state per generation lane, schema-driven parameter values."""
import time

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import runtime
from ..core.api.catalog import EDIT3D_TASKS

# Lane tabs. Edit 3D lives under the 3D tab (its "Edit" mode); Jobs, Generations and Agents are panels, not tabs.
LANE_ITEMS = [
    ('image', "Image", "Text and reference images to images"),
    ('video', "Video", "Text, images or a Blender playblast to video"),
    ('3d', "3D", "Text or images to 3D models; Edit mode runs Scenario's 3D tools on the selected mesh"),
    ('material', "Materials", "PBR materials with Patina"),
    ('audio', "Audio", "Speech, music and sound effects; results can go on the sequencer"),
    ('render_image', "Render Image", "Render the viewport or the camera view as a finished still: capture + optional style images + look prompt"),
    ('render_video', "Render Video", "Render a playblast of the timeline as a finished clip: captured video + optional images + look prompt"),
]
TAB_ICON = {"image": "image", "video": "video", "3d": "3d", "material": "image", "audio": "audio", "render_image": "image", "render_video": "video"}
# Every lane a request can be built for (the tabs plus edit3d, reached through the 3D tab's Edit mode).
GENERATION_LANES = ("image", "video", "3d", "material", "audio", "render_image", "render_video", "edit3d")
LANE_ATTR = {"image": "image", "video": "video", "3d": "three_d", "material": "material", "audio": "audio", "render_image": "render_image", "render_video": "render_video", "edit3d": "edit3d"}
ATTR_LANE = {attr: lane for lane, attr in LANE_ATTR.items()}
REFERENCE_SOURCES = [
    ('FILE', "File", "An image, video or audio file on disk"),
    ('VIEWPORT', "Viewport still", "Capture the active 3D viewport as an image at generate time"),
    ('CAMERA', "Camera still", "Render the scene camera view as an image at generate time"),
    ('VIEWPORT_CLIP', "Viewport clip", "Playblast the active viewport over the timeline at generate time"),
    ('CAMERA_CLIP', "Camera clip", "Playblast the scene camera over the timeline at generate time"),
    ('RENDER', "Render Result", "The latest render result"),
    ('ASSET', "Scenario asset", "An asset already in your Scenario project"),
    ('MESH', "Selected mesh", "Export the selected mesh objects as GLB at generate time"),
]
CAPTURE_SOURCES = ('VIEWPORT', 'CAMERA', 'VIEWPORT_CLIP', 'CAMERA_CLIP')
CLIP_SOURCES = ('VIEWPORT_CLIP', 'CAMERA_CLIP')
ADDABLE_SOURCES = [item for item in REFERENCE_SOURCES if item[0] not in ('ASSET', 'MESH')]  # asset ids come from the MCP tools, the mesh from the selection
# The sources that make sense for a file input, by its kind. A 3D input (a character mesh) takes the selected scene
# mesh or an uploaded model, never an image capture; an image input takes stills, a video input takes clips.
_SOURCES_BY_KIND = {
    "3d": ('FILE',),  # the scene selection is attached automatically; Upload overrides it with a model file
    "image": ('FILE', 'RENDER', 'VIEWPORT', 'CAMERA'),
    "video": ('FILE', 'RENDER', 'VIEWPORT_CLIP', 'CAMERA_CLIP'),
    "audio": ('FILE',),
}


def addable_sources_for(kind):
    """Reference sources offered for a file input of this kind, as (id, label, description) tuples."""
    wanted = _SOURCES_BY_KIND.get((kind or "image").lower(), _SOURCES_BY_KIND["image"])
    by_id = {item[0]: item for item in REFERENCE_SOURCES}
    return [by_id[s] for s in wanted if s in by_id]
EDIT3D_TASK_ITEMS = [(task_id, label, description) for task_id, label, description, _models in EDIT3D_TASKS]
THREE_D_MODES = [('TEXT', "Text", "Describe the object"), ('IMAGE', "Image", "One reference image"), ('MULTI', "Multi-view", "Several views of the same object"),
                 ('EDIT', "Edit", "Remesh, retexture, unwrap, rig, animate or split the selected mesh")]


_T0 = time.monotonic()
_lane_items_cache = []


def clock():
    """Seconds since the add-on loaded. Blender FloatProperty is 32-bit: an epoch timestamp (1.8e9) would round to
    the nearest 128 s and make debounce comparisons fail at random, so timers stored on properties use this small clock."""
    return time.monotonic() - _T0


def mark_estimate_dirty(lane_state):
    lane_state.estimate_state = 'PENDING'
    lane_state.estimate_dirty_at = clock()
    lane_state.estimate_key = ""  # a quote already in flight belongs to the previous form


def lane_of(lane_state):
    """Lane name derived from where the state lives on the scene, so drawing never has to write it."""
    try:
        path = lane_state.path_from_id()
    except (ValueError, AttributeError):
        return lane_state.lane or "image"
    attr = path.rsplit(".", 1)[-1]
    return ATTR_LANE.get(attr, lane_state.lane or "image")


def active_lane(scene):
    """The lane the visible form builds requests for: the 3D tab in Edit mode drives the edit3d lane."""
    lane = scene.scenario.lane
    if lane == "3d" and scene.scenario.three_d_mode == 'EDIT':
        return "edit3d"
    return lane


def _lane_items(self, context):
    """Lane tabs with Scenario's modality icons when the icon set is loaded (kept alive in a module list for Blender)."""
    global _lane_items_cache
    try:
        from . import icons

        icon_for = icons.icon
    except ImportError:
        icon_for = None
    items = []
    for index, (ident, name, desc) in enumerate(LANE_ITEMS):
        value = icon_for(TAB_ICON.get(ident, "image")) if icon_for else 0
        items.append((ident, name, desc, value, index) if value else (ident, name, desc))
    if items != _lane_items_cache:
        _lane_items_cache = items
    return _lane_items_cache


def _param_items(self, context):
    key = ("param", self.model_id, self.name)
    cached = runtime.state.enum_cache.get(key)
    if cached:
        return cached
    # Cache miss: the params were restored from a saved .blend before sync_params re-ran, so the in-memory enum cache
    # is empty and the dropdown would show "Loading..." forever. Rebuild the choices from the schema on the spot
    # (draw-safe: it reads the record and writes only the plain enum-cache dict, never ID data).
    from . import generation

    schema = generation.schema_for(self.model_id)
    spec = schema.by_name(self.name) if schema is not None else None
    if spec is not None and spec.allowed_values and spec.ptype != "string_array":
        options = [(str(v), spec.label_for(v), spec.description) for v in spec.allowed_values if str(v) != ""]
        if options:
            runtime.set_enum_items(key, options)
            return runtime.state.enum_cache[key]
    return runtime.enum_items(key)


def _find_lane_state(context, lane):
    scene = getattr(context, "scene", None) or bpy.context.scene
    if scene is None or not lane:
        return None
    return scene.scenario.lane_state(lane)


def _on_param_update(self, context):
    if self.has_range:
        if self.float_value < self.fmin:
            self.float_value = self.fmin
        elif self.float_value > self.fmax:
            self.float_value = self.fmax
        if self.int_value < int(self.fmin):
            self.int_value = int(self.fmin)
        elif self.int_value > int(self.fmax):
            self.int_value = int(self.fmax)
    lane_state = _find_lane_state(context, self.lane)
    if lane_state is not None:
        mark_estimate_dirty(lane_state)
    if self.name == "duration":
        from . import generation

        generation.sync_shot_duration(getattr(context, "scene", None) or bpy.context.scene)


class ScenarioParamValue(bpy.types.PropertyGroup):
    name: StringProperty()
    model_id: StringProperty()
    lane: StringProperty()
    ptype: StringProperty()
    label: StringProperty()
    str_value: StringProperty(update=_on_param_update)
    int_value: IntProperty(update=_on_param_update)
    float_value: FloatProperty(update=_on_param_update, precision=3)
    bool_value: BoolProperty(update=_on_param_update)
    enum_value: EnumProperty(items=_param_items, update=_on_param_update)
    multi_value: StringProperty(description="Comma separated selection for list parameters")
    enabled: BoolProperty(default=True, update=_on_param_update)
    fmin: FloatProperty(default=-1e9)
    fmax: FloatProperty(default=1e9)
    has_range: BoolProperty(default=False)


class ScenarioReference(bpy.types.PropertyGroup):
    param_name: StringProperty()
    source: EnumProperty(items=REFERENCE_SOURCES, default='FILE')
    filepath: StringProperty(subtype='FILE_PATH')
    asset_id: StringProperty()
    label: StringProperty()


def _model_items(self, context):
    return runtime.enum_items(("models", lane_of(self)))


def _on_model_change(self, context):
    from . import generation

    if self.model_id and self.model_id != "NONE":
        self.model_key = self.model_id
    generation.on_model_changed(context, self)


def _on_prompt_update(self, context):
    mark_estimate_dirty(self)


def _on_match_timeline(self, context):
    mark_estimate_dirty(self)
    from . import generation

    generation.sync_shot_duration(getattr(context, "scene", None) or bpy.context.scene)


def _on_mode_change(self, context):
    from . import generation

    if self.three_d_mode == 'EDIT':
        generation.refresh_edit3d_models(context)
    else:
        generation.refresh_3d_models(context)


def _on_task_change(self, context):
    from . import generation

    generation.refresh_edit3d_models(context)


class ScenarioLaneState(bpy.types.PropertyGroup):
    lane: StringProperty()
    model_id: EnumProperty(name="Model", items=_model_items, update=_on_model_change)
    model_key: StringProperty(description="Chosen model id, the source of truth that survives catalog changes")
    prompt: StringProperty(name="Prompt", description="What to generate", update=_on_prompt_update)
    prompt_rows: IntProperty(name="Prompt height", description="Drag to make the prompt box taller", default=1, min=1, max=8)
    params: CollectionProperty(type=ScenarioParamValue)
    references: CollectionProperty(type=ScenarioReference)
    estimate_state: EnumProperty(items=[('IDLE', "Idle", ""), ('PENDING', "Pending", ""), ('READY', "Ready", ""), ('ERROR', "Error", ""), ('UNAVAILABLE', "Unavailable", "")], default='IDLE')
    estimate_cu: FloatProperty(default=-1.0)
    estimate_dirty_at: FloatProperty(default=0.0)
    estimate_key: StringProperty()
    estimate_error: StringProperty()
    estimate_partial: BoolProperty(default=False, description="The quote excludes references that are not uploaded yet")
    last_error: StringProperty()
    match_timeline: BoolProperty(name="Match timeline", default=True, description="Capture the clip at the video model output duration, so the motion maps one to one", update=_on_match_timeline)
    force_solid: BoolProperty(name="Grey clay capture", default=False, description="Capture with solid single-colour shading so the model reads shapes and motion, not materials")
    capture_source: EnumProperty(name="Source", items=[('VIEWPORT', "Viewport", "The active 3D viewport, as you see it"), ('CAMERA', "Scene camera", "The scene camera view")], default='CAMERA', update=_on_prompt_update)
    # Render lanes
    spark_enabled: BoolProperty(name="Write the look with Prompt Spark", default=True,
                                description="When the look is empty, a capture of the view is sent to Prompt Spark, which writes the art-direction brief (0.75 CU). Off: a photoreal default look is used")
    spark_look: StringProperty(description="The look Prompt Spark wrote for the last generation")
    render_style_open: BoolProperty(name="Rendering Style", default=True, description="Show the look, style images and first frame")
    first_frame_path: StringProperty(description="A Render Image result used as the first frame of the video")
    use_first_frame: BoolProperty(name="Use as first frame", default=True, description="Send the rendered still as the first frame so the clip starts exactly from it", update=_on_prompt_update)
    # Edit 3D
    source_object: StringProperty(description="Name of the mesh object sent to the 3D tool")
    concept_path: StringProperty()  # kept for scenes saved with 0.5.x
    concept_job: StringProperty()


class ScenarioSceneProps(bpy.types.PropertyGroup):
    lane: EnumProperty(name="Lane", items=_lane_items)
    three_d_mode: EnumProperty(name="Input", items=THREE_D_MODES, default='TEXT', update=_on_mode_change)
    edit3d_task: EnumProperty(name="Task", items=EDIT3D_TASK_ITEMS, default='RETEXTURE', update=_on_task_change)
    image: PointerProperty(type=ScenarioLaneState)
    video: PointerProperty(type=ScenarioLaneState)
    three_d: PointerProperty(type=ScenarioLaneState)
    material: PointerProperty(type=ScenarioLaneState)
    audio: PointerProperty(type=ScenarioLaneState)
    render_image: PointerProperty(type=ScenarioLaneState)
    render_video: PointerProperty(type=ScenarioLaneState)
    edit3d: PointerProperty(type=ScenarioLaneState)
    show_cloud_history: BoolProperty(name="Cloud history", default=True, description="List the project's generations made elsewhere (web app, agents, other machines)")

    def lane_state(self, lane=None):
        lane = lane or self.lane
        attr = LANE_ATTR.get(lane)
        if attr is None:
            return None
        return getattr(self, attr)


CLASSES = (ScenarioParamValue, ScenarioReference, ScenarioLaneState, ScenarioSceneProps)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scenario = PointerProperty(type=ScenarioSceneProps)


def unregister():
    del bpy.types.Scene.scenario
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
