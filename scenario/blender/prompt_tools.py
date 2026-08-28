# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt tools next to every prompt field: Spark (write), Rewrite, Translate.

Spark and Rewrite call Prompt Spark in model-contextual mode (3.75 CU); Translate uses the Scenario LLM (0.5 CU).
The API call runs on a worker thread through the job manager; the result comes back as a ("prompt", payload) event
that the pump hands to `on_prompt_event`, which writes the text into the lane's prompt."""
import logging

import bpy
from bpy.props import EnumProperty, StringProperty

from . import runtime
from ..core.api import llm
from ..core.api import spark as spark_api
from ..core.api.errors import ScenarioError

log = logging.getLogger("scenario.prompt_tools")

SPARK_COST = 3.75
TRANSLATE_COST = 0.5
MODE_ITEMS = [
    ('GENERATE', "Write", f"Prompt Spark writes a prompt for this model, from your text when there is one ({SPARK_COST:g} CU)"),
    ('REWRITE', "Rewrite", f"Prompt Spark rewrites your prompt for this model ({SPARK_COST:g} CU)"),
]
MESSAGES = {
    'GENERATE': "Prompt written by Prompt Spark",
    'REWRITE': "Prompt rewritten by Prompt Spark",
    'TRANSLATE': "Prompt translated to English",
}


def _poll(context):
    from .operators import _network_poll

    return _network_poll(None, context)


def _lane_states(lane):
    for scene in bpy.data.scenes:
        lane_state = scene.scenario.lane_state(lane)
        if lane_state is not None:
            yield lane_state


def _start(context, lane, worker, message):
    """Resolve the client on the main thread, then run `worker(manager, client)` on a job-manager thread."""
    lane_state = context.scene.scenario.lane_state(lane)
    client = runtime.make_client()  # bpy is read here, never on the worker
    manager = runtime.ensure_manager()
    if lane_state is not None:
        lane_state.last_error = ""
    runtime.set_message(message)
    manager._spawn(worker, manager, client)


def on_prompt_event(payload):
    """Write a prompt produced off-thread into every scene's lane state (main thread, called by the pump)."""
    lane, text = payload.get("lane"), (payload.get("text") or "").strip()
    if not lane or not text:
        return
    for lane_state in _lane_states(lane):
        lane_state.prompt = text
    runtime.set_message(MESSAGES.get(payload.get("mode"), "Prompt updated"))


class SCENARIO_OT_prompt_spark(bpy.types.Operator):
    bl_idname = "scenario.prompt_spark"
    bl_label = "Prompt Spark"
    bl_description = f"Prompt Spark writes or rewrites the prompt for the selected model ({SPARK_COST:g} CU)"
    lane: StringProperty(default="image")
    mode: EnumProperty(items=MODE_ITEMS, default='GENERATE')

    @classmethod
    def poll(cls, context):
        return _poll(context)

    @classmethod
    def description(cls, context, properties):
        return next((desc for ident, _label, desc in MODE_ITEMS if ident == properties.mode), cls.bl_description)

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        if lane_state is None:
            self.report({'ERROR'}, f"Unknown lane {self.lane}")
            return {'CANCELLED'}
        prompt = lane_state.prompt.strip()
        if self.mode == 'REWRITE' and not prompt:
            self.report({'WARNING'}, "Write a prompt to rewrite first")
            return {'CANCELLED'}
        model_id = lane_state.model_id if lane_state.model_id and lane_state.model_id != "NONE" else None
        lane, mode = self.lane, self.mode
        intent = prompt or None

        def worker(manager, client):
            try:
                prompts = spark_api.spark(client, prompt=intent, model_id=model_id, num_results=1)
            except (ScenarioError, ValueError) as err:
                manager.events.put(("error", f"Prompt Spark failed: {getattr(err, 'reason', err)}"))
                return
            manager.events.put(("prompt", {"lane": lane, "text": prompts[0], "mode": mode}))

        try:
            _start(context, lane, worker, "Prompt Spark is writing..." if mode == 'GENERATE' else "Prompt Spark is rewriting...")
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


class SCENARIO_OT_prompt_translate(bpy.types.Operator):
    bl_idname = "scenario.prompt_translate"
    bl_label = "Translate prompt"
    bl_description = f"Translate the prompt to English with the Scenario LLM ({TRANSLATE_COST:g} CU)"
    lane: StringProperty(default="image")

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        if lane_state is None:
            self.report({'ERROR'}, f"Unknown lane {self.lane}")
            return {'CANCELLED'}
        prompt = lane_state.prompt.strip()
        if not prompt:
            self.report({'WARNING'}, "Write a prompt to translate first")
            return {'CANCELLED'}
        lane = self.lane

        def worker(manager, client):
            try:
                text = llm.translate(client, prompt)
            except (ScenarioError, ValueError) as err:
                manager.events.put(("error", f"Translation failed: {getattr(err, 'reason', err)}"))
                return
            manager.events.put(("prompt", {"lane": lane, "text": text, "mode": 'TRANSLATE'}))

        try:
            _start(context, lane, worker, "Translating the prompt...")
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


def draw_prompt_row(layout, lane_state, lane, text="", placeholder=None):
    """The prompt field with its pencil and the three prompt tools. Rewrite and Translate need a prompt to work on."""
    row = layout.row(align=True)
    if placeholder:
        row.prop(lane_state, "prompt", text=text, placeholder=placeholder)
    else:
        row.prop(lane_state, "prompt", text=text)
    row.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL').lane = lane
    op = row.operator(SCENARIO_OT_prompt_spark.bl_idname, text="", icon='LIGHT_SUN')
    op.lane, op.mode = lane, 'GENERATE'
    sub = row.row(align=True)
    sub.enabled = bool(lane_state.prompt.strip())
    op = sub.operator(SCENARIO_OT_prompt_spark.bl_idname, text="", icon='FILE_REFRESH')
    op.lane, op.mode = lane, 'REWRITE'
    sub.operator(SCENARIO_OT_prompt_translate.bl_idname, text="", icon='WORLD_DATA').lane = lane
    return row


CLASSES = (SCENARIO_OT_prompt_spark, SCENARIO_OT_prompt_translate)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
