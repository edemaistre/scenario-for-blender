# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Glue between scene state, schemas, estimates and the job manager (main thread)."""
import logging
import time
from dataclasses import dataclass, field

import bpy

from . import params_ui, props, runtime
from ..core.api.catalog import DEFAULT_MODELS, models_for_lane
from ..core.api.errors import ScenarioError
from ..core.schema.params import build_body, missing_required_files, parse_schema, validate
from ..core.scene import capture_plan

log = logging.getLogger("scenario.generation")

LANE_KIND = {"image": "image", "video": "video", "3d": "3d", "material": "material", "render": "video"}
_schemas = {}


def lane_kind(lane):
    return LANE_KIND.get(lane, "image")


def schema_for(model_id):
    if not model_id or model_id == "NONE":
        return None
    schema = _schemas.get(model_id)
    if schema is None:
        record = runtime.state.records.get(model_id)
        if record is None or not record.parameters:
            return None
        schema = parse_schema(record)
        _schemas[model_id] = schema
    return schema


def request_catalog():
    if runtime.state.catalog_loading or not runtime.online():
        return False
    try:
        manager = runtime.ensure_manager()
        catalog = runtime.ensure_catalog()
    except ScenarioError as err:
        runtime.set_message(err.reason)
        return False
    wanted = [m for lane in DEFAULT_MODELS for m in DEFAULT_MODELS[lane]]
    cached = catalog.load_list_cached("public")
    if cached:
        detailed = []
        for model_id in wanted:
            path = catalog.cache_dir / "models" / f"{model_id}.json"
            if path.exists():
                detailed.append(catalog.get(model_id))
        set_catalog(cached, detailed)
    runtime.state.catalog_loading = True
    manager.fetch_catalog(catalog, "public", wanted)
    return True


def set_catalog(records, detailed):
    for rec in detailed:
        runtime.state.records[rec.id] = rec
        _schemas.pop(rec.id, None)
    for rec in records:
        runtime.state.records.setdefault(rec.id, rec)
    for lane in props.GENERATION_LANES:
        lane_records = models_for_lane("video" if lane == "render" else lane, records)
        runtime.state.lane_models[lane] = lane_records
        runtime.set_enum_items(("models", lane), [(r.id, r.name, r.short_description) for r in lane_records])
    runtime.state.catalog_loaded = True
    runtime.state.catalog_loading = False
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            # a catalog refresh must not re-price forms that are already quoted
            on_model_changed(bpy.context, lane_state, mark_dirty=False)
    if bpy.context.scene is not None:
        refresh_3d_models(bpy.context)


def _image_inputs(record):
    return [p for p in record.parameters if p.get("type") in ("file", "file_array") and (p.get("kind") or "image") == "image"]


def three_d_models(mode, records):
    """Bucket 3D models by how they are driven: TEXT (txt23d), IMAGE (one picture), MULTI (several views)."""
    out = []
    for record in records:
        caps = set(record.capabilities)
        if record.deprecated_successor:
            continue
        if mode == 'TEXT':
            if "txt23d" in caps:
                out.append(record)
            continue
        if "img23d" not in caps:
            continue
        inputs = _image_inputs(record)
        if not inputs:
            if mode == 'IMAGE':
                out.append(record)  # list entry without schema yet, assume single image
            continue
        multi = any(p.get("type") == "file_array" and (p.get("maxLength") or 2) > 1 for p in inputs)
        if mode == 'MULTI' and multi:
            out.append(record)
        elif mode == 'IMAGE' and (not multi or any(p.get("type") == "file" for p in inputs) or True):
            out.append(record)
    return models_for_lane("3d", out)


def refresh_3d_models(context=None):
    scene = getattr(context, "scene", None) or bpy.context.scene
    if scene is None:
        return
    records = three_d_models(scene.scenario.three_d_mode, list(runtime.state.records.values()))
    runtime.state.lane_models["3d"] = records
    runtime.set_enum_items(("models", "3d"), [(r.id, r.name, r.short_description) for r in records])
    on_model_changed(context or bpy.context, scene.scenario.lane_state("3d"))


def ensure_record(model_id):
    """Return a detailed record (with parameters); fetch synchronously if only the list entry is known."""
    record = runtime.state.records.get(model_id)
    if record is not None and record.parameters:
        return record
    catalog = runtime.ensure_catalog()
    record = catalog.get(model_id)
    runtime.state.records[model_id] = record
    _schemas.pop(model_id, None)
    return record


def on_model_changed(context, lane_state, mark_dirty=True):
    model_id = lane_state.model_id
    if not model_id or model_id == "NONE":
        return
    try:
        ensure_record(model_id)
    except ScenarioError as err:
        lane_state.last_error = err.reason
        return
    schema = schema_for(model_id)
    if schema is None:
        return
    params_ui.sync_params(lane_state, schema, model_id)
    if mark_dirty or lane_state.estimate_state == 'IDLE':
        props.mark_estimate_dirty(lane_state)


@dataclass
class Request:
    lane: str
    kind: str
    model_id: str
    body: dict
    files: dict = field(default_factory=dict)
    array_params: set = field(default_factory=set)
    errors: list = field(default_factory=list)
    partial: bool = False
    captures: list = field(default_factory=list)


def build_request(scene, lane, for_estimate=False):
    lane_state = scene.scenario.lane_state(lane)
    model_id = lane_state.model_id
    schema = schema_for(model_id)
    if schema is None:
        return Request(lane, lane_kind(lane), model_id, {}, errors=["Model not loaded yet"])
    if schema.by_name("duration") is not None and lane_state.match_timeline:
        apply_match_timeline(scene, lane_state, schema)
    values, enabled = params_ui.collect_values(lane_state, schema)
    refs = params_ui.collect_file_refs(lane_state, schema)
    files, array_params, asset_ids, captures = {}, set(), {}, []
    for spec in schema.specs:
        if not spec.is_file:
            continue
        if spec.ptype == "file_array":
            array_params.add(spec.name)
        for ref in refs.get(spec.name, []):
            if ref.source == 'ASSET' and ref.asset_id:
                asset_ids.setdefault(spec.name, []).append(ref.asset_id)
            elif ref.source == 'FILE' and ref.filepath:
                files.setdefault(spec.name, []).append(bpy.path.abspath(ref.filepath))
            elif ref.source == 'RENDER':
                path = _save_render_result(scene)
                if path:
                    files.setdefault(spec.name, []).append(path)
            elif ref.source in props.CAPTURE_SOURCES:
                captures.append({"param": spec.name, "source": ref.source, "camera": ref.asset_id or None})
    body = build_body(schema.specs, values, asset_ids, enabled=enabled)
    pending = {name: list(paths) for name, paths in files.items()}
    for cap in captures:
        pending.setdefault(cap["param"], []).append("<capture>")
    check = dict(body)
    for name, paths in pending.items():
        check.setdefault(name, paths if name in array_params else paths[0])
    if "seedance" in model_id and schema.prompt_name and (pending or asset_ids):
        has_video = any(s.kind == "video" and s.name in check for s in schema.specs if s.is_file)
        has_image = any((s.kind or "image") == "image" and s.name in check for s in schema.specs if s.is_file)
        body[schema.prompt_name] = capture_plan.tag_prompt(body.get(schema.prompt_name, ""), has_video, has_image)
        check[schema.prompt_name] = body[schema.prompt_name]
    errors = validate(schema.specs, check)
    partial = False
    if for_estimate:
        # The dry run rejects unknown asset ids (404), so files still to be uploaded are left out of the quote.
        if missing_required_files(schema.specs, check):
            errors.append("Add a reference to see the cost")
        partial = bool(captures) or any(spec.cost_impact and spec.name in files for spec in schema.specs if spec.is_file)
    return Request(lane, lane_kind(lane), model_id, body, files, array_params, errors, partial, captures)


def apply_match_timeline(scene, lane_state, schema):
    spec = schema.by_name("duration")
    if spec is None or not spec.allowed_values or not lane_state.match_timeline:
        return None
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    _, _, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                            preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    value, note = capture_plan.choose_duration(seconds, spec.allowed_values)
    index = lane_state.params.find("duration")
    if index >= 0 and value is not None:
        item = lane_state.params[index]
        if item.enum_value != str(value):
            item.enum_value = str(value)
        item.enabled = True
    return value, note, seconds


def perform_captures(context, request, runner=None):
    """Run the pending viewport/camera captures on the main thread and turn them into files."""
    from . import capture

    scene = context.scene
    lane_state = scene.scenario.lane_state(request.lane)
    schema = schema_for(request.model_id)
    limit = None
    chosen = request.body.get("duration")
    duration_spec = schema.by_name("duration") if schema else None
    if isinstance(chosen, int) and chosen > 0:
        limit = chosen
    elif duration_spec and duration_spec.allowed_values:
        numeric = [int(v) for v in duration_spec.allowed_values if isinstance(v, (int, float)) and int(v) > 0]
        limit = max(numeric) if numeric else None
    for cap in request.captures:
        source = cap["source"]
        camera = bpy.data.objects.get(cap["camera"]) if cap.get("camera") else None
        base = 'CAMERA' if source.startswith('CAMERA') else 'VIEWPORT'
        force_solid = bool(lane_state.force_solid) if lane_state is not None else False
        if source in props.CLIP_SOURCES:
            fps = scene.render.fps / (scene.render.fps_base or 1.0)
            start, end, _ = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                    preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
            if limit:
                start, end = capture_plan.clip_frames_for(limit, fps, start, end)
            path = capture.new_capture_path("playblast", "mp4")
            info = capture.capture_playblast(context, path, source=base, camera=camera, frame_start=start, frame_end=end, force_solid=force_solid, runner=runner)
            request.files.setdefault(cap["param"], []).append(info["path"])
        else:
            path = capture.new_capture_path("still", "png")
            request.files.setdefault(cap["param"], []).append(capture.capture_still(context, path, source=base, camera=camera, force_solid=force_solid, runner=runner))
    request.captures = []
    return request


def request_meta(context, lane):
    lane_state = context.scene.scenario.lane_state(lane)
    record = runtime.state.records.get(lane_state.model_id)
    meta = {"prompt": lane_state.prompt, "model_name": record.name if record else lane_state.model_id}
    if lane == "material":
        meta["target_objects"] = [o.name for o in context.selected_objects if o.type == 'MESH']
    return meta


def request_estimate(scene, lane):
    lane_state = scene.scenario.lane_state(lane)
    request = build_request(scene, lane, for_estimate=True)
    if request.errors:
        lane_state.estimate_state = 'UNAVAILABLE'
        lane_state.estimate_error = request.errors[0]
        return
    key = f"{lane}:{request.model_id}:{time.time():.3f}"
    log.info("estimate requested %s", key)
    lane_state.estimate_key = key
    lane_state.estimate_state = 'PENDING'
    lane_state.estimate_partial = request.partial
    try:
        runtime.ensure_manager().estimate(key, request.model_id, request.body)
    except ScenarioError as err:
        lane_state.estimate_state = 'ERROR'
        lane_state.estimate_error = err.reason


def submit_generation(context, lane):
    scene = context.scene
    lane_state = scene.scenario.lane_state(lane)
    request = build_request(scene, lane)
    if request.errors:
        raise ScenarioError(0, "; ".join(request.errors))
    try:
        perform_captures(context, request)
    except RuntimeError as err:
        raise ScenarioError(0, str(err)) from err
    manager = runtime.ensure_manager()
    rec = manager.submit(lane, request.kind, request.model_id, request.body, files=request.files,
                         array_params=request.array_params, meta=request_meta(context, lane))
    runtime.state.jobs_view.insert(0, rec)
    lane_state.last_error = ""
    runtime.set_message(f"Submitted to {rec.meta.get('model_name', rec.model_id)}")
    return rec


def _save_render_result(scene):
    image = bpy.data.images.get("Render Result")
    if image is None:
        return None
    path = runtime.paths().cache_dir / "captures" / f"render_{int(time.time())}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save_render(str(path), scene=scene)
    except RuntimeError as err:
        log.warning("no render result to save: %s", err)
        return None
    return str(path)
