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
REFERENCE_SOURCES = [
    ('FILE', "File", "An image or video file on disk"),
    ('VIEWPORT', "Viewport", "Capture the active 3D viewport at generate time"),
    ('RENDER', "Render Result", "The latest render result"),
    ('ASSET', "Scenario asset", "An asset already in your Scenario project"),
]


def mark_estimate_dirty(lane_state):
    lane_state.estimate_state = 'PENDING'
    lane_state.estimate_dirty_at = time.time()


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
    return runtime.enum_items(("models", self.lane))


def _on_model_change(self, context):
    from . import generation

    generation.on_model_changed(context, self)


def _on_prompt_update(self, context):
    mark_estimate_dirty(self)


class ScenarioLaneState(bpy.types.PropertyGroup):
    lane: StringProperty()
    model_id: EnumProperty(name="Model", items=_model_items, update=_on_model_change)
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


class ScenarioSceneProps(bpy.types.PropertyGroup):
    lane: EnumProperty(name="Lane", items=LANE_ITEMS, default='image')
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
        state = getattr(self, attr)
        if not state.lane:
            state.lane = lane
        return state


CLASSES = (ScenarioParamValue, ScenarioReference, ScenarioLaneState, ScenarioSceneProps)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scenario = PointerProperty(type=ScenarioSceneProps)


def unregister():
    del bpy.types.Scene.scenario
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
