# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render-to-real: a styled concept still from the viewport, then a Seedance video from the playblast."""
import bpy

from . import generation, runtime
from ..core.api.errors import ScenarioError
from ..core.schema.params import build_body, parse_schema
from ..core.scene import capture_plan

CONCEPT_MODELS = ("model_google-gemini-3-1-flash", "model_openai-gpt-image-2")
VIDEO_MODEL = "model_bytedance-seedance-2-0"
CONCEPT_PROMPT_SUFFIX = "Keep the composition, camera angle and silhouettes of the reference render exactly; only change the look."


def _record(model_ids):
    for model_id in model_ids:
        record = runtime.state.records.get(model_id)
        if record is not None and record.parameters:
            return record
    for model_id in model_ids:
        try:
            return generation.ensure_record(model_id)
        except ScenarioError:
            continue
    return None


def _capture_source(lane):
    return 'CAMERA' if lane.capture_source == 'CAMERA' else 'VIEWPORT'


def concept_request(context):
    scene = context.scene
    lane = scene.scenario.lane_state("render")
    record = _record(CONCEPT_MODELS)
    if record is None:
        return generation.Request("render", "image", "", {}, errors=["Concept model not available"])
    schema = parse_schema(record)
    refs = schema.by_name("referenceImages") or next((s for s in schema.specs if s.is_file and (s.kind or "image") == "image"), None)
    if refs is None:
        return generation.Request("render", "image", record.id, {}, errors=["Concept model takes no reference image"])
    prompt = f"{lane.prompt.strip()}. {CONCEPT_PROMPT_SUFFIX}" if lane.prompt.strip() else CONCEPT_PROMPT_SUFFIX
    body = build_body(schema.specs, {schema.prompt_name: prompt, "resolution": "1K"}, files={})
    style_files = [bpy.path.abspath(r.filepath) for r in lane.references if r.source == 'FILE' and r.filepath]
    files = {refs.name: style_files} if style_files else {}
    request = generation.Request("render", "image", record.id, body, files, {refs.name} if refs.ptype == "file_array" else set(), [])
    request.captures = [{"param": refs.name, "source": _capture_source(lane), "camera": None}]
    return request


def video_request(context):
    scene = context.scene
    lane = scene.scenario.lane_state("render")
    record = _record((VIDEO_MODEL,))
    if record is None:
        return generation.Request("render", "video", VIDEO_MODEL, {}, errors=["Seedance 2.0 not available"])
    schema = parse_schema(record)
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    _, _, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                            preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    duration_spec = schema.by_name("duration")
    duration, note = capture_plan.choose_duration(seconds, duration_spec.allowed_values if duration_spec else (-1,))
    values = {schema.prompt_name: capture_plan.render_to_real_prompt(lane.prompt), "duration": duration, "resolution": "720p",
              "generateAudio": bool(lane.generate_audio)}
    files = {}
    if lane.concept_path:
        files["referenceImages"] = [lane.concept_path]
    body = build_body(schema.specs, values, files={})
    request = generation.Request("render", "video", record.id, body, files, {"referenceVideos", "referenceImages"}, [])
    request.captures = [{"param": "referenceVideos", "source": 'CAMERA_CLIP' if _capture_source(lane) == 'CAMERA' else 'VIEWPORT_CLIP', "camera": None}]
    if note:
        runtime.set_message(f"Clip {note}")
    return request


def _submit(context, request, step):
    if request.errors:
        raise ScenarioError(0, "; ".join(request.errors))
    try:
        generation.perform_captures(context, request)
    except RuntimeError as err:
        raise ScenarioError(0, str(err)) from err
    manager = runtime.ensure_manager()
    lane = context.scene.scenario.lane_state("render")
    record = runtime.state.records.get(request.model_id)
    meta = {"prompt": lane.prompt, "model_name": record.name if record else request.model_id, "render_step": step}
    rec = manager.submit("render", request.kind, request.model_id, request.body, files=request.files, array_params=request.array_params, meta=meta)
    runtime.state.jobs_view.insert(0, rec)
    if step == "concept":
        lane.concept_job = rec.local_id
    runtime.set_message("Concept submitted" if step == "concept" else "Playblast uploaded, Seedance is rendering")
    return rec


def submit_concept(context):
    return _submit(context, concept_request(context), "concept")


def submit_video(context):
    return _submit(context, video_request(context), "video")


def on_result(rec):
    if rec.lane != "render" or rec.meta.get("render_step") != "concept" or not rec.files:
        return
    for scene in bpy.data.scenes:
        lane = scene.scenario.lane_state("render")
        if lane.concept_job in ("", rec.local_id):
            lane.concept_path = rec.files[0]
            runtime.set_message("Concept ready, now Playblast and Generate")


def draw_render_lane(layout, context):
    lane = context.scene.scenario.lane_state("render")
    box = layout.box()
    box.label(text="1. Concept look", icon='IMAGE_DATA')
    box.prop(lane, "capture_source", text="Source")
    row = box.row(align=True)
    row.prop(lane, "prompt", text="")
    row.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL').lane = "render"
    refs = [r for r in lane.references if r.source == 'FILE']
    header = box.row()
    header.label(text=f"Style references  {len(refs)}", icon='IMAGE_REFERENCE')
    add = header.operator("scenario.add_reference", text="Add", icon='ADD')
    add.lane, add.param_name, add.source = "render", "styleImages", 'FILE'
    for index, ref in enumerate(lane.references):
        r = box.row(align=True)
        r.label(text=ref.label or ref.filepath, icon='DOT')
        rm = r.operator("scenario.remove_reference", text="", icon='X')
        rm.lane, rm.index = "render", index
    box.operator("scenario.render_concept", text="Render concept", icon='RENDER_STILL')
    if lane.concept_path:
        box.label(text="Concept: " + lane.concept_path.rsplit("/", 1)[-1][:40], icon='CHECKMARK')
        box.operator("scenario.show_image", text="Show concept").filepath = lane.concept_path
    box = layout.box()
    box.label(text="2. Playblast to video (Seedance 2.0)", icon='RENDER_ANIMATION')
    scene = context.scene
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    start, end, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                  preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    box.label(text=f"Frames {start} to {end}: {seconds:.1f} s at 720p (clamped 4 to 15 s)")
    box.prop(lane, "force_solid")
    box.prop(lane, "generate_audio")
    row = box.row()
    row.scale_y = 1.4
    row.enabled = bool(lane.concept_path)
    row.operator("scenario.render_video", text="Playblast and Generate", icon='PLAY')
    if not lane.concept_path:
        box.label(text="Render a concept first (or use the Video lane directly)", icon='INFO')
