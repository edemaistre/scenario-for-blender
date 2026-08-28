# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt tools next to every prompt field, like the Scenario web app: a dice (generate a new prompt), sparkles
(rewrite your prompt), translate (to English).

Generate and Rewrite call Prompt Spark with the lane's model (model-contextual when the model supports it, up to
3.75 CU, otherwise the generic 0.75 CU answer). When Prompt Spark answers with nothing usable (some models return
`asset_` ids that resolve to no text), the Scenario LLM writes the prompt instead (0.5 CU). Translate always uses the
Scenario LLM. The API call runs on a worker thread through the job manager; the result comes back as a
("prompt", payload) event that the pump hands to `on_prompt_event`, which writes the text into the lane's prompt."""
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
# Blender appends the final period to descriptions itself, hence none at the end.
TOOLTIP_GENERATE = f"Generate a new prompt. Prompt Spark, up to {SPARK_COST:g} CU"
TOOLTIP_REWRITE = f"Rewrite your prompt. Prompt Spark, up to {SPARK_COST:g} CU"
TOOLTIP_TRANSLATE = f"Translate to English. Scenario LLM, {TRANSLATE_COST:g} CU"
MODE_ITEMS = [
    ('GENERATE', "Generate a new prompt", TOOLTIP_GENERATE),
    ('REWRITE', "Rewrite your prompt", TOOLTIP_REWRITE),
]
MESSAGES = {
    'GENERATE': "Prompt written by Prompt Spark",
    'REWRITE': "Prompt rewritten by Prompt Spark",
    'TRANSLATE': "Prompt translated to English",
}
LLM_FALLBACK_MESSAGE = "Prompt written by the Scenario LLM (Prompt Spark had no answer for this model)"
LLM_GENERATE = ("Write one generation prompt for the AI model \"{name}\"{about}. {intent}"
                "Describe the subject, the style, the materials, the lighting and the composition the way that model expects. "
                "One paragraph, no title, no preamble, no quotes: return only the prompt.")
LLM_REWRITE = ("Rewrite the user's prompt for the AI model \"{name}\"{about}. Keep the subject and the intent, make it precise "
               "and complete for that model (style, materials, lighting, composition), remove filler. "
               "One paragraph, no title, no preamble, no quotes: return only the rewritten prompt.")


def _poll(context):
    from .operators import _network_poll

    return _network_poll(None, context)


def _lane_states(lane):
    for scene in bpy.data.scenes:
        lane_state = scene.scenario.lane_state(lane)
        if lane_state is not None:
            yield lane_state


def _model_context(model_id):
    """Name and short description of the lane's model, read on the main thread for the LLM fallback."""
    record = runtime.state.records.get(model_id) if model_id else None
    if record is None:
        return model_id or "the selected model", ""
    about = f" ({record.short_description.strip()})" if record.short_description else ""
    return record.name, about


def fallback_instruction(mode, model_name, about, intent):
    """The Scenario LLM instruction used when Prompt Spark has no usable answer."""
    if mode == 'REWRITE':
        return LLM_REWRITE.format(name=model_name, about=about)
    wish = f"The user's idea: {intent.strip()}. " if intent and intent.strip() else ""
    return LLM_GENERATE.format(name=model_name, about=about, intent=wish)


def usable_text(text):
    """A prompt we accept into the field: non-empty and never an `asset_` id."""
    text = (text or "").strip()
    return text if text and not spark_api.is_asset_ref(text) else ""


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
    lane, text = payload.get("lane"), usable_text(payload.get("text"))
    if not lane or not text:
        return
    for lane_state in _lane_states(lane):
        lane_state.prompt = text
    if payload.get("source") == "llm" and payload.get("mode") != 'TRANSLATE':
        runtime.set_message(LLM_FALLBACK_MESSAGE)
    else:
        runtime.set_message(MESSAGES.get(payload.get("mode"), "Prompt updated"))


def spark_or_llm(client, mode, intent, model_id, instruction):
    """Prompt Spark first; the Scenario LLM when Spark has nothing usable. Returns (text, source). Raises on total failure."""
    try:
        prompts = spark_api.spark(client, prompt=intent, model_id=model_id, num_results=1)
        text = usable_text(prompts[0])
        if text:
            return text, "spark"
        spark_error = ValueError(spark_api.NO_PROMPT)
    except (ScenarioError, ValueError) as err:
        spark_error = err
    log.info("Prompt Spark gave nothing usable (%s); asking the Scenario LLM", getattr(spark_error, "reason", spark_error))
    text = usable_text(llm.run_text(client, instruction, text_inputs=[intent] if intent else ()))
    if not text:
        raise ValueError("The Scenario LLM returned no usable prompt")
    return text, "llm"


class SCENARIO_OT_prompt_spark(bpy.types.Operator):
    bl_idname = "scenario.prompt_spark"
    bl_label = "Prompt Spark"
    bl_description = TOOLTIP_GENERATE
    lane: StringProperty(default="image", description="Lane whose prompt is written")
    mode: EnumProperty(items=MODE_ITEMS, default='GENERATE', description="Write a new prompt or rewrite the current one")

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
        model_name, about = _model_context(model_id)
        instruction = fallback_instruction(mode, model_name, about, intent)

        def worker(manager, client):
            try:
                text, source = spark_or_llm(client, mode, intent, model_id, instruction)
            except (ScenarioError, ValueError) as err:
                manager.events.put(("error", f"Prompt Spark failed: {getattr(err, 'reason', err)}"))
                return
            manager.events.put(("prompt", {"lane": lane, "text": text, "mode": mode, "source": source}))

        try:
            _start(context, lane, worker, "Prompt Spark is writing..." if mode == 'GENERATE' else "Prompt Spark is rewriting...")
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


class SCENARIO_OT_prompt_translate(bpy.types.Operator):
    bl_idname = "scenario.prompt_translate"
    bl_label = "Translate to English"
    bl_description = TOOLTIP_TRANSLATE
    lane: StringProperty(default="image", description="Lane whose prompt is translated")

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
                text = usable_text(llm.translate(client, prompt))
                if not text:
                    raise ValueError("The Scenario LLM returned no translation")
            except (ScenarioError, ValueError) as err:
                manager.events.put(("error", f"Translation failed: {getattr(err, 'reason', err)}"))
                return
            manager.events.put(("prompt", {"lane": lane, "text": text, "mode": 'TRANSLATE', "source": "llm"}))

        try:
            _start(context, lane, worker, "Translating the prompt...")
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


def _icon_kwargs(name):
    try:
        from . import icons

        return icons.kwargs(name)
    except ImportError:
        return {"icon": {"dice": 'LIGHT_SUN', "sparkles": 'FILE_REFRESH', "translate": 'WORLD_DATA'}.get(name, 'QUESTION')}


def _wrap(text, width):
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width and current:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines


def draw_prompt_row(layout, lane_state, lane, text="", placeholder=None, wrap_width=44, max_lines=3):
    """The prompt as a box of its own, like Scenario's: a header, the full-width field, the long prompt wrapped
    underneath so it stays readable, and the three prompt tools (dice, sparkles, translate) as a row of equal
    buttons. Rewrite and Translate need a prompt to work on."""
    box = layout.box()
    header = box.row(align=True)
    header.label(text=text or "Prompt", icon='TEXT')
    header.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL', emboss=False).lane = lane
    field = box.row(align=True)
    if placeholder:
        field.prop(lane_state, "prompt", text="", placeholder=placeholder)
    else:
        field.prop(lane_state, "prompt", text="")
    prompt = lane_state.prompt.strip()
    if len(prompt) > wrap_width:
        col = box.column(align=True)
        col.scale_y = 0.85
        lines = _wrap(prompt, wrap_width)
        for line in lines[:max_lines]:
            col.label(text=line)
        if len(lines) > max_lines:
            col.label(text="…")
    tools = box.row(align=True)
    tools.alignment = 'CENTER'  # icon buttons keep a fixed width in Blender: centre them and make them larger
    tools.scale_x, tools.scale_y = 1.8, 1.3
    op = tools.operator(SCENARIO_OT_prompt_spark.bl_idname, text="", **_icon_kwargs("dice"))
    op.lane, op.mode = lane, 'GENERATE'
    sub = tools.row(align=True)
    sub.enabled = bool(prompt)
    op = sub.operator(SCENARIO_OT_prompt_spark.bl_idname, text="", **_icon_kwargs("sparkles"))
    op.lane, op.mode = lane, 'REWRITE'
    sub.operator(SCENARIO_OT_prompt_translate.bl_idname, text="", **_icon_kwargs("translate")).lane = lane
    return box


CLASSES = (SCENARIO_OT_prompt_spark, SCENARIO_OT_prompt_translate)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
