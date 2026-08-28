# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level property groups: one lane state per generation lane, schema-driven parameter values."""
import time

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import runtime

LANE_ITEMS = [
    ('image', "Image", "Text and reference images to images"),
    ('video', "Video", "Text, images or a Blender playblast to video"),
    ('3d', "3D", "Text or images to 3D models"),
    ('material', "Materials", "PBR materials with Patina"),
    ('render', "Render-to-real", "Viewport capture and playblast to styled stills and video"),
    ('mcp', "MCP", "Let agents build in this Blender"),
    ('history', "Generations", "Everything generated in this project"),
]
GENERATION_LANES = ("image", "video", "3d", "material", "render")
LANE_ATTR = {"image": "image", "video": "video", "3d": "three_d", "material": "material", "render": "render"}
ATTR_LANE = {attr: lane for lane, attr in LANE_ATTR.items()}
REFERENCE_SOURCES = [
    ('FILE', "File", "An image or video file on disk"),
    ('VIEWPORT', "Viewport still", "Capture the active 3D viewport as an image at generate time"),
    ('CAMERA', "Camera still", "Render the scene camera view as an image at generate time"),
    ('VIEWPORT_CLIP', "Viewport clip", "Playblast the active viewport over the timeline at generate time"),
    ('CAMERA_CLIP', "Camera clip", "Playblast the scene camera over the timeline at generate time"),
    ('RENDER', "Render Result", "The latest render result"),
    ('ASSET', "Scenario asset", "An asset already in your Scenario project"),
]
CAPTURE_SOURCES = ('VIEWPORT', 'CAMERA', 'VIEWPORT_CLIP', 'CAMERA_CLIP')
CLIP_SOURCES = ('VIEWPORT_CLIP', 'CAMERA_CLIP')
ADDABLE_SOURCES = [item for item in REFERENCE_SOURCES if item[0] != 'ASSET']  # asset ids come from the MCP tools, not the Add menu


_T0 = time.monotonic()


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


def _param_items(self, context):
    return runtime.enum_items(("param", self.model_id, self.name))


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


def _on_mode_change(self, context):
    from . import generation

    generation.refresh_3d_models(context)


class ScenarioLaneState(bpy.types.PropertyGroup):
    lane: StringProperty()
    model_id: EnumProperty(name="Model", items=_model_items, update=_on_model_change)
    model_key: StringProperty(description="Chosen model id, the source of truth that survives catalog changes")
    prompt: StringProperty(name="Prompt", description="What to generate", update=_on_prompt_update)
    params: CollectionProperty(type=ScenarioParamValue)
    references: CollectionProperty(type=ScenarioReference)
    estimate_state: EnumProperty(items=[('IDLE', "Idle", ""), ('PENDING', "Pending", ""), ('READY', "Ready", ""), ('ERROR', "Error", ""), ('UNAVAILABLE', "Unavailable", "")], default='IDLE')
    estimate_cu: FloatProperty(default=-1.0)
    estimate_dirty_at: FloatProperty(default=0.0)
    estimate_key: StringProperty()
    estimate_error: StringProperty()
    estimate_partial: BoolProperty(default=False, description="The quote excludes references that are not uploaded yet")
    last_error: StringProperty()
    match_timeline: BoolProperty(name="Match timeline", default=True, description="Set the clip duration from the scene frame range", update=_on_prompt_update)
    force_solid: BoolProperty(name="Grey clay capture", default=False, description="Capture with solid single-colour shading so the model reads motion, not materials")
    capture_source: EnumProperty(name="Source", items=[('VIEWPORT', "Viewport", "The active 3D viewport"), ('CAMERA', "Scene camera", "The scene camera")], default='CAMERA')
    generate_audio: BoolProperty(name="Generate audio", default=False)
    concept_path: StringProperty()
    concept_job: StringProperty()


class ScenarioSceneProps(bpy.types.PropertyGroup):
    lane: EnumProperty(name="Lane", items=LANE_ITEMS, default='image')
    three_d_mode: EnumProperty(name="Input", items=[('TEXT', "Text", "Describe the object"), ('IMAGE', "Image", "One reference image"), ('MULTI', "Multi-view", "Several views of the same object")], default='TEXT', update=_on_mode_change)
    image: PointerProperty(type=ScenarioLaneState)
    video: PointerProperty(type=ScenarioLaneState)
    three_d: PointerProperty(type=ScenarioLaneState)
    material: PointerProperty(type=ScenarioLaneState)
    render: PointerProperty(type=ScenarioLaneState)

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
