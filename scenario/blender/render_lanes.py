# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render Image and Render Video: a capture of the scene, optional style images, a look, a precise prompt.

Render Image: viewport or camera still + style images + look -> a finished still (image edit models).
Render Video: playblast of the timeline + images (first frame, styles) + look -> a finished clip (video models with a video input).
With an empty look, a still of the view goes to Prompt Spark, which writes the art-direction brief before the job is
submitted (the manager's `prepare` hook, on the worker thread)."""
import logging
import os

import bpy

from . import runtime
from ..core.api import spark as spark_api
from ..core.api.catalog import RENDER_LANES, tagged_video_model
from ..core.scene import capture_plan, render_prompt

log = logging.getLogger("scenario.render")
SPARK_NUM_RESULTS = 1


def is_render_lane(lane):
    return lane in RENDER_LANES


def image_specs(schema):
    return [s for s in schema.specs if s.is_file and (s.kind or "image") == "image"]


def video_spec(schema):
    return next((s for s in schema.specs if s.is_file and s.kind == "video"), None)


def scene_spec(lane, schema):
    """The input that receives the capture: the video input for Render Video, the image list (else the single image) for Render Image."""
    if lane == "render_video":
        return video_spec(schema)
    specs = image_specs(schema)
    arrays = [s for s in specs if s.ptype == "file_array"]
    return (arrays or specs or [None])[0]


def style_spec(schema, exclude=None):
    """Where style images go: the image list input, or the single image input that is not already taken."""
    for spec in image_specs(schema):
        if spec.ptype == "file_array" and spec is not exclude:
            return spec
    for spec in image_specs(schema):
        if spec is not exclude:
            return spec
    return None


def first_frame_spec(schema):
    """A single image input named like a first frame (Seedance `image`, H3 `firstFrameImage`), else None."""
    for spec in image_specs(schema):
        if spec.ptype == "file" and any(k in spec.name.lower() for k in ("image", "firstframe", "first_frame", "start")) and "last" not in spec.name.lower():
            return spec
    return None


def hidden_inputs(schema):
    """File inputs Render Image does not use: anything that is not an image (Gemini 3.1 also takes a video)."""
    return {s.name for s in schema.specs if s.is_file and (s.kind or "image") != "image"}


def hidden_param_names(schema):
    """Parameters that only make sense with a hidden input, by name prefix (`video` -> `videoFps`) or by dependency."""
    hidden = hidden_inputs(schema)
    out = set()
    for spec in schema.specs:
        if spec.is_file or spec.is_prompt:
            continue
        lower = spec.name.lower()
        if any(lower.startswith(h.lower()) for h in hidden) or any(dep in hidden for dep in spec.required_if_defined):
            out.add(spec.name)
    return out


def capture_source(lane_state, lane):
    base = 'CAMERA' if lane_state.capture_source == 'CAMERA' else 'VIEWPORT'
    return base + ('_CLIP' if lane == "render_video" else '')


def decorate(scene, lane, lane_state, schema, request, for_estimate):
    """Turn a generic request into a render request: the capture first, the images in the order the prompt names them, the prompt itself."""
    spec = scene_spec(lane, schema)
    if spec is None:
        request.errors.append("This model takes no " + ("video" if lane == "render_video" else "image") + " input; pick another one")
        return request
    request.captures.insert(0, {"param": spec.name, "source": capture_source(lane_state, lane), "camera": None, "first": True})
    look = lane_state.prompt.strip()
    style_count = sum(len(v) for v in request.files.values()) + sum(1 for c in request.captures if not c.get("first"))
    style_count += sum(len(v) if isinstance(v, list) else 1 for k, v in request.body.items() if schema.by_name(k) is not None and schema.by_name(k).is_file)
    first_frame = False
    if lane == "render_video":
        ff_path = lane_state.first_frame_path if lane_state.use_first_frame else ""
        if ff_path and os.path.exists(bpy.path.abspath(ff_path)):
            ff_spec = first_frame_spec(schema)
            target = ff_spec or style_spec(schema)
            if target is not None:
                files = request.files.setdefault(target.name, [])
                files.insert(0, bpy.path.abspath(ff_path))
                if target.ptype == "file_array":
                    request.array_params.add(target.name)
                first_frame = True
        image_count = style_count + (1 if first_frame else 0)
        tagged = tagged_video_model(request.model_id)
        request.spark = None if (look or not lane_state.spark_enabled) else {"kind": "video", "image_count": image_count, "first_frame": first_frame, "tagged": tagged}
        prompt = render_prompt.video_prompt(look or render_prompt.DEFAULT_LOOK, image_count, first_frame, tagged)
    else:
        request.spark = None if (look or not lane_state.spark_enabled) else {"kind": "image", "style_count": style_count}
        prompt = render_prompt.image_prompt(look or render_prompt.DEFAULT_LOOK, style_count)
    if schema.prompt_name:
        request.body[schema.prompt_name] = prompt
    if lane == "render_image":
        # parameters that belong to inputs the lane hides (Gemini's video -> videoFps) are not sent either
        for name in hidden_param_names(schema):
            request.body.pop(name, None)
    if request.spark is not None and lane == "render_video":
        # a still of the first frame for Prompt Spark to look at (the playblast itself is not an image)
        request.captures.append({"param": None, "source": 'CAMERA' if lane_state.capture_source == 'CAMERA' else 'VIEWPORT', "camera": None, "role": "spark"})
    request.meta.update({"render_lane": lane, "look": look, "prompt_name": schema.prompt_name or "prompt", "spark": bool(request.spark)})
    return request


def make_prepare(spark_info, image_path, prompt_name):
    """Worker-side step: ask Prompt Spark for the look from the capture, then write the final prompt into the body."""
    def prepare(client, rec):
        images = [spark_api.data_url(image_path)] if image_path and os.path.exists(image_path) else []
        looks = spark_api.spark(client, prompt=render_prompt.SPARK_BRIEF, images=images, num_results=SPARK_NUM_RESULTS)
        look = looks[0]
        if spark_info["kind"] == "video":
            prompt = render_prompt.video_prompt(look, spark_info["image_count"], spark_info["first_frame"], spark_info["tagged"])
        else:
            prompt = render_prompt.image_prompt(look, spark_info["style_count"])
        rec.body[prompt_name] = prompt
        rec.meta["spark_look"] = look
        rec.meta["prompt"] = look
        log.info("Prompt Spark look: %s", look[:120])
    return prepare


def on_result(rec):
    """A Render Image result becomes the default first frame of Render Video; the Spark look is shown on the lane."""
    lane = rec.meta.get("render_lane")
    if not lane:
        return
    for scene in bpy.data.scenes:
        lane_state = scene.scenario.lane_state(lane)
        if lane_state is None:
            continue
        if rec.meta.get("spark_look"):
            lane_state.spark_look = rec.meta["spark_look"]
        if lane == "render_image" and rec.files:
            video_lane = scene.scenario.lane_state("render_video")
            if video_lane is not None:
                video_lane.first_frame_path = rec.files[0]
                runtime.set_message("Render ready; it is now the first frame of Render Video")


# -- drawing --------------------------------------------------------------

def _clip_info(scene):
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    return capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                   preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)


def _draw_look(layout, lane_state, lane):
    from . import panels

    box = layout.box()
    panels.draw_prompt_row(box, lane_state, lane, text="Look")
    if not lane_state.prompt.strip():
        sub = box.row(align=True)
        sub.prop(lane_state, "spark_enabled", text="")
        sub.label(text="Empty: Prompt Spark writes the look from a capture (0.75 CU)" if lane_state.spark_enabled else "Empty: a photoreal default look is used", icon='LIGHT_SUN')
    if lane_state.spark_look:
        box.label(text="Spark: " + lane_state.spark_look[:70], icon='INFO')


def draw_render_image_lane(layout, context):
    from . import generation, panels, params_ui

    scene = context.scene
    lane_state = scene.scenario.lane_state("render_image")
    box = layout.box()
    box.label(text="Scene to render", icon='RESTRICT_VIEW_OFF')
    row = box.row(align=True)
    row.prop(lane_state, "capture_source", expand=True)
    box.prop(lane_state, "force_solid")
    panels.draw_model_row(layout, lane_state, "render_image")
    schema = generation.schema_for(lane_state.model_id)
    if schema is None:
        layout.label(text=lane_state.last_error or "Loading the model description...", icon='ERROR' if lane_state.last_error else 'TIME')
        return
    _draw_look(layout, lane_state, "render_image")
    spec = scene_spec("render_image", schema)
    if spec is None:
        layout.label(text="This model takes no image input; pick another one", icon='ERROR')
    else:
        # video or audio inputs of an image model (Gemini's video2img) are not what a render needs: keep the form to images
        panels.draw_references(layout, lane_state, schema, title_for={spec.name: "Style images (the capture is image 1)"},
                               fixed_first={spec.name: "1. Capture of the view, taken at generate time"}, hide=hidden_inputs(schema))
    params_ui.draw_params(layout, lane_state, schema, exclude=hidden_param_names(schema))
    panels.draw_generate_row(layout, lane_state, "render_image")


def draw_render_video_lane(layout, context):
    from . import generation, panels, params_ui

    scene = context.scene
    lane_state = scene.scenario.lane_state("render_video")
    box = layout.box()
    box.label(text="Clip to render", icon='RENDER_ANIMATION')
    row = box.row(align=True)
    row.prop(lane_state, "capture_source", expand=True)
    start, end, seconds = _clip_info(scene)
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    box.label(text=f"Frames {start} to {end}: {seconds:.1f} s at {fps:g} fps, 1280x720")
    row = box.row(align=True)
    row.prop(lane_state, "force_solid")
    row.prop(lane_state, "match_timeline")
    schema_now = generation.schema_for(lane_state.model_id)
    if schema_now is not None and lane_state.match_timeline and schema_now.by_name("duration") is not None:
        _, value, note = generation.timeline_sync_info(scene, lane_state, schema_now)
        if value is not None:
            box.label(text=f"Video duration {value:g} s" + (f" ({note}); the clip is cut to match" if note else ", same as the clip"), icon='TIME')
    try:
        from . import shot_planner

        shot_planner.draw_shot_planner(layout, context)
    except ImportError:
        pass
    panels.draw_model_row(layout, lane_state, "render_video")
    schema = generation.schema_for(lane_state.model_id)
    if schema is None:
        layout.label(text=lane_state.last_error or "Loading the model description...", icon='ERROR' if lane_state.last_error else 'TIME')
        return
    _draw_look(layout, lane_state, "render_video")
    box = layout.box()
    if lane_state.first_frame_path:
        row = box.row(align=True)
        row.prop(lane_state, "use_first_frame", text="")
        icon_id = panels.thumbnail(lane_state.first_frame_path)
        if icon_id:
            row.template_icon(icon_value=icon_id, scale=2.0)
        row.label(text="First frame: " + os.path.basename(lane_state.first_frame_path)[-36:])
        row.operator("scenario.clear_first_frame", text="", icon='X')
    else:
        box.label(text="No first frame: a Render Image result can start the clip", icon='INFO')
    spec = scene_spec("render_video", schema)
    if spec is None:
        layout.label(text="This model takes no video input; pick another one", icon='ERROR')
    else:
        titles, fixed = {spec.name: "Playblast (recorded at generate time)"}, {spec.name: "Timeline playblast"}
        hide = {spec.name}
        ff_spec = first_frame_spec(schema)
        if ff_spec is not None:
            hide.add(ff_spec.name)  # fed by the First frame row above
        styles = style_spec(schema, exclude=ff_spec)
        if styles is not None:
            titles[styles.name] = "Style images"
        panels.draw_references(layout, lane_state, schema, title_for=titles, fixed_first=fixed, hide=hide)
    params_ui.draw_params(layout, lane_state, schema, locked={"duration"} if lane_state.match_timeline else ())
    panels.draw_generate_row(layout, lane_state, "render_video")
