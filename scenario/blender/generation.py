# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Glue between scene state, schemas, estimates and the job manager (main thread)."""
import logging
import time
from dataclasses import dataclass, field

import bpy

from . import params_ui, props, runtime
from ..core.api.catalog import DEFAULT_MODELS, MULTIVIEW_HINTS, RENDER_LANES, edit3d_models, lane_kind, mesh_param, models_for_lane
from ..core.api.errors import ScenarioError
from ..core.schema.params import build_body, missing_required_files, parse_schema, validate
from ..core.scene import capture_plan

log = logging.getLogger("scenario.generation")

_schemas = {}


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
        lane_records = models_for_lane(lane, records)
        runtime.state.lane_models[lane] = lane_records
        runtime.set_enum_items(("models", lane), [(r.id, r.name, r.short_description) for r in lane_records])
    runtime.state.catalog_loaded = True
    runtime.state.catalog_loading = False
    runtime.state.catalog_error = ""
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            restore_model_key(lane_state)
            # a catalog refresh must not re-price forms that are already quoted
            on_model_changed(bpy.context, lane_state, mark_dirty=False)
    if bpy.context.scene is not None:
        refresh_3d_models(bpy.context)
        refresh_edit3d_models(bpy.context)


def restore_model_key(lane_state):
    """Point the enum back at the model the user chose (stored by id), if the rebuilt list still has it."""
    key = lane_state.model_key
    if not key:
        return
    valid = [item[0] for item in runtime.enum_items(("models", props.lane_of(lane_state)))]
    if key in valid and lane_state.model_id != key:
        lane_state.model_id = key


def set_models(detailed, failed):
    for rec in detailed:
        runtime.state.records[rec.id] = rec
        _schemas.pop(rec.id, None)
    for model_id, reason in failed.items():
        runtime.set_message(f"{model_id}: {reason}")
    _pending_models.difference_update([r.id for r in detailed] + list(failed))
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            if lane_state.model_id in [r.id for r in detailed]:
                on_model_changed(bpy.context, lane_state)


_pending_models = set()


def request_model(model_id):
    """Fetch a model record in the background; the 'models' event finishes the job."""
    if model_id in _pending_models or not runtime.online():
        return
    try:
        manager = runtime.ensure_manager()
        catalog = runtime.ensure_catalog()
    except ScenarioError as err:
        runtime.set_message(err.reason)
        return
    _pending_models.add(model_id)
    manager.fetch_models(catalog, [model_id])


def _image_inputs(record):
    return [p for p in record.parameters if p.get("type") in ("file", "file_array") and (p.get("kind") or "image") == "image"]


def _looks_multiview(record):
    text = (record.id + " " + record.name).lower()
    return any(hint in text for hint in MULTIVIEW_HINTS)


def three_d_models(mode, records):
    """Bucket 3D models by how they are driven: TEXT (txt23d), IMAGE (one picture), MULTI (several views).

    With a schema, a file_array image input that accepts more than one file means multi-view. Without a schema
    (list entries), the model id and name decide ("multi", "multiview"). Models taking 1 to N images appear in both."""
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
            multi_named = _looks_multiview(record)
            if (mode == 'MULTI' and multi_named) or (mode == 'IMAGE' and not multi_named):
                out.append(record)
            continue
        multi = any(p.get("type") == "file_array" and (p.get("maxLength") or 2) > 1 for p in inputs)
        single = any(p.get("type") == "file" for p in inputs) or any(p.get("type") == "file_array" and (p.get("minLength") or 1) <= 1 for p in inputs)
        if mode == 'MULTI' and (multi or _looks_multiview(record)):
            out.append(record)
        elif mode == 'IMAGE' and (single or not multi) and not (_looks_multiview(record) and not single):
            out.append(record)
    return models_for_lane("3d", out)


def refresh_3d_models(context=None):
    scene = getattr(context, "scene", None) or bpy.context.scene
    if scene is None:
        return
    records = three_d_models(scene.scenario.three_d_mode, list(runtime.state.records.values()))
    runtime.state.lane_models["3d"] = records
    runtime.set_enum_items(("models", "3d"), [(r.id, r.name, r.short_description) for r in records])
    lane_state = scene.scenario.lane_state("3d")
    restore_model_key(lane_state)
    on_model_changed(context or bpy.context, lane_state)
    # models known only from the list get their schema in the background so the form and the quote work
    missing = [r.id for r in records if not r.parameters and r.id not in _pending_models][:12]
    if missing:
        request_models(missing)


def refresh_edit3d_models(context=None):
    """The Edit 3D model list follows the task tabs (Retexture, Retopology, Rigging...)."""
    scene = getattr(context, "scene", None) or bpy.context.scene
    if scene is None:
        return
    records = edit3d_models(scene.scenario.edit3d_task, list(runtime.state.records.values()))
    runtime.state.lane_models["edit3d"] = records
    runtime.set_enum_items(("models", "edit3d"), [(r.id, r.name, r.short_description) for r in records])
    lane_state = scene.scenario.lane_state("edit3d")
    restore_model_key(lane_state)
    if lane_state.model_id == "NONE" or lane_state.model_id not in [r.id for r in records]:
        if records:
            lane_state.model_id = records[0].id
    on_model_changed(context or bpy.context, lane_state)
    missing = [r.id for r in records if not r.parameters and r.id not in _pending_models][:12]
    if missing:
        request_models(missing)


def request_models(model_ids):
    if not runtime.online():
        return
    try:
        manager = runtime.ensure_manager()
        catalog = runtime.ensure_catalog()
    except ScenarioError as err:
        runtime.set_message(err.reason)
        return
    _pending_models.update(model_ids)
    manager.fetch_models(catalog, list(model_ids))


def ensure_record(model_id):
    """Return a detailed record (with parameters), from memory or the disk cache; never hits the network on the main thread.

    Callers that can wait use request_model() and react to the 'models' event. MCP tools run this off the main
    thread through the executor and may fetch synchronously."""
    record = runtime.state.records.get(model_id)
    if record is not None and record.parameters:
        return record
    catalog = runtime.ensure_catalog()
    cached = catalog.load_cached(model_id)
    if cached is not None and cached.parameters:
        runtime.state.records[model_id] = cached
        _schemas.pop(model_id, None)
        return cached
    if runtime.on_main_thread():
        request_model(model_id)
        raise ScenarioError(0, "Loading the model description")
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
        lane_state.last_error = "" if err.reason.startswith("Loading") else err.reason
        return
    lane_state.last_error = ""
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
    spark: dict = None            # set by the render lanes when Prompt Spark must write the look first
    meta: dict = field(default_factory=dict)


def build_request(scene, lane, for_estimate=False):
    lane_state = scene.scenario.lane_state(lane)
    model_id = lane_state.model_id
    schema = schema_for(model_id)
    if schema is None:
        return Request(lane, lane_kind(lane), model_id, {}, errors=["Model not loaded yet"])
    if lane == "video" and schema.by_name("duration") is not None and lane_state.match_timeline:
        apply_match_timeline(scene, lane_state, schema)  # base Video: the model duration follows the timeline
    values, enabled = params_ui.collect_values(lane_state, schema)
    refs = params_ui.collect_file_refs(lane_state, schema)
    files, array_params, asset_ids, captures = {}, set(), {}, []
    # A model's 3D mesh input is fed by the scene selection automatically, in every lane: the Edit lane requires it,
    # elsewhere (a text-to-motion model's character mesh) it is optional but still used when something is selected.
    # Skip it only when the user attached an explicit file/asset for that input.
    record = runtime.state.records.get(model_id)
    mesh_name = mesh_param(record) if record is not None else None
    if lane == "edit3d" and mesh_name is None:
        return Request(lane, lane_kind(lane), model_id, {}, errors=["This model takes no mesh input"])
    if mesh_name is not None and not any(r.param_name == mesh_name for r in lane_state.references):
        from . import mesh_export

        if lane == "edit3d" or mesh_export.source_objects(bpy.context):
            captures.append({"param": mesh_name, "source": 'MESH', "camera": None, "first": True})
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
                if for_estimate:
                    captures.append({"param": spec.name, "source": 'RENDER', "camera": None})  # quoted like a pending file, no disk write
                else:
                    path = _save_render_result(scene)
                    if path:
                        files.setdefault(spec.name, []).append(path)
            elif ref.source in props.CAPTURE_SOURCES:
                captures.append({"param": spec.name, "source": ref.source, "camera": ref.asset_id or None})
            elif ref.source == 'MESH':
                # the user attached the selected scene mesh to a 3D input outside the edit3d lane (e.g. a text-to-motion
                # model's optional character mesh); export it at generate time just like edit3d does
                captures.append({"param": spec.name, "source": 'MESH', "camera": None})
    body = build_body(schema.specs, values, asset_ids, enabled=enabled)
    request = Request(lane, lane_kind(lane), model_id, body, files, array_params, [], False, captures)
    if lane in RENDER_LANES:
        from . import render_lanes

        render_lanes.decorate(scene, lane, lane_state, schema, request, for_estimate)
        if request.errors:
            return request
    pending = {name: list(paths) for name, paths in request.files.items()}
    for cap in request.captures:
        if cap.get("param"):
            pending.setdefault(cap["param"], []).append("<capture>")
    check = dict(body)
    for name, paths in pending.items():
        check.setdefault(name, paths if name in request.array_params else paths[0])
    if "seedance" in model_id and schema.prompt_name and (pending or asset_ids):
        has_video = any(s.kind == "video" and s.name in check for s in schema.specs if s.is_file)
        has_image = any((s.kind or "image") == "image" and s.name in check for s in schema.specs if s.is_file)
        body[schema.prompt_name] = capture_plan.tag_prompt(body.get(schema.prompt_name, ""), has_video, has_image)
        check[schema.prompt_name] = body[schema.prompt_name]
    errors = validate(schema.specs, check, schema.one_of)
    if lane == "edit3d":
        from . import mesh_export

        if not mesh_export.source_objects(bpy.context):
            errors.append("Select the mesh to edit")
    if for_estimate:
        # The dry run rejects unknown asset ids (404), so files still to be uploaded are left out of the quote.
        if missing_required_files(schema.specs, check):
            errors.append("Add a reference to see the cost")
        elif missing_required_files(schema.specs, body):
            # the required file only exists as a pending capture or export: the server prices it after the upload
            errors.append("Price shown after the upload (the model needs the " + ("mesh" if lane == "edit3d" else "capture") + " first)")
        request.partial = bool(request.captures) or any(spec.cost_impact and spec.name in request.files for spec in schema.specs if spec.is_file)
    request.errors = errors
    return request


def model_duration_value(lane_state):
    """The Render Video model chosen output duration in seconds, or None."""
    schema = schema_for(lane_state.model_id)
    spec = schema.by_name("duration") if schema is not None else None
    if spec is None:
        return None
    index = lane_state.params.find("duration")
    if index < 0:
        return None
    item = lane_state.params[index]
    try:
        if spec.allowed_values:
            return float(item.enum_value)
        return float(item.int_value if spec.is_integer else item.float_value)
    except (ValueError, TypeError):
        return None


def sync_shot_duration(scene):
    """With Match timeline on, the camera path (and the captured clip) lasts exactly the model video duration, so the
    motion maps one to one. Called from property callbacks, never during draw, so it may write scene data."""
    if scene is None or not hasattr(scene, "scenario_shot"):
        return
    lane_state = scene.scenario.lane_state("render_video")
    if lane_state is None or not lane_state.match_timeline:
        return
    value = model_duration_value(lane_state)
    if value is None or value <= 0:
        return
    shot = scene.scenario_shot
    prop = shot.bl_rna.properties["duration"]
    value = max(prop.hard_min, min(prop.hard_max, value))
    if abs(shot.duration - value) > 1e-6:
        shot.duration = value


def apply_match_timeline(scene, lane_state, schema):
    """Drive the model's duration from the timeline: a choice list (Seedance: Auto, 4..15) picks the first value that
    fits the clip; a numeric range (Minimax H3: 5 to 15 s) takes the clip length rounded up and clamped. The capture is
    then trimmed or padded to that duration in perform_captures, so the clip and the video always have the same length."""
    spec = schema.by_name("duration")
    if spec is None or not lane_state.match_timeline:
        return None
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    _, _, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                            preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    index = lane_state.params.find("duration")
    if index < 0:
        return None
    item = lane_state.params[index]
    if spec.allowed_values:
        value, note = capture_plan.choose_duration(seconds, spec.allowed_values)
        if value is not None and item.enum_value != str(value):
            item.enum_value = str(value)
    elif spec.ptype == "number":
        value, note = capture_plan.clamp_duration(seconds, spec.min, spec.max, integer=spec.is_integer)
        if spec.is_integer:
            if item.int_value != int(value):
                item.int_value = int(value)
        elif abs(item.float_value - value) > 1e-6:
            item.float_value = float(value)
    else:
        return None
    if not item.enabled:
        item.enabled = True
    return value, note, seconds


def timeline_sync_info(scene, lane_state, schema):
    """(clip seconds, model duration, note) for the UI, without touching the form."""
    spec = schema.by_name("duration") if schema else None
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    _, _, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                            preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    if spec is None:
        return seconds, None, ""
    if spec.allowed_values:
        value, note = capture_plan.choose_duration(seconds, spec.allowed_values)
    elif spec.ptype == "number":
        value, note = capture_plan.clamp_duration(seconds, spec.min, spec.max, integer=spec.is_integer)
    else:
        return seconds, None, ""
    return seconds, value, note


def perform_captures(context, request, runner=None):
    """Run the pending viewport/camera captures on the main thread and turn them into files."""
    from . import capture

    scene = context.scene
    lane_state = scene.scenario.lane_state(request.lane)
    schema = schema_for(request.model_id)
    limit = None
    chosen = request.body.get("duration")
    duration_spec = schema.by_name("duration") if schema else None
    if isinstance(chosen, (int, float)) and chosen > 0:
        limit = float(chosen)
    elif duration_spec and duration_spec.allowed_values:
        numeric = [int(v) for v in duration_spec.allowed_values if isinstance(v, (int, float)) and int(v) > 0]
        limit = max(numeric) if numeric else None
    elif duration_spec and duration_spec.ptype == "number" and duration_spec.max:
        limit = float(duration_spec.max)
    def _add(cap, path):
        if cap.get("param") is None:
            return
        target = request.files.setdefault(cap["param"], [])
        if cap.get("first"):
            target.insert(0, path)
        else:
            target.append(path)

    for cap in request.captures:
        source = cap["source"]
        if source == 'RENDER':
            continue
        if source == 'MESH':
            from . import mesh_export

            objects = mesh_export.source_objects(context)
            path = mesh_export.export_glb(context, objects)
            request.meta["source_object"] = objects[0].name if objects else ""
            request.meta["source_objects"] = [o.name for o in objects]
            _add(cap, path)
            continue
        camera = bpy.data.objects.get(cap["camera"]) if cap.get("camera") else None
        base = 'CAMERA' if source.startswith('CAMERA') else 'VIEWPORT'
        force_solid = bool(lane_state.force_solid) if lane_state is not None else False
        if cap.get("role") == "spark":
            # a still for Prompt Spark to look at, never sent to the generation model; taken at the first frame of the clip
            path = capture.new_capture_path("spark", "png")
            request.meta["spark_image"] = capture.first_frame_still(context, path, source=base, camera=camera, force_solid=False, runner=runner)
            continue
        if source in props.CLIP_SOURCES:
            fps = scene.render.fps / (scene.render.fps_base or 1.0)
            start, end, _ = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                    preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
            if limit:
                start, end = capture_plan.clip_frames_for(limit, fps, start, end)
            # the clip lasts exactly the duration the model was asked for (and never less than Seedance's 4 s)
            target = max(capture_plan.MIN_CLIP_SECONDS, float(chosen)) if isinstance(chosen, (int, float)) and chosen > 0 else capture_plan.MIN_CLIP_SECONDS
            start, end, padded = capture_plan.ensure_min_frames(start, end, fps, min_seconds=target)
            if padded:
                runtime.set_message(f"Clip padded to {target:g} s (frames {start} to {end}) to match the video duration")
            path = capture.new_capture_path("playblast", "mp4")
            info = capture.capture_playblast(context, path, source=base, camera=camera, frame_start=start, frame_end=end, force_solid=force_solid, runner=runner)
            _add(cap, info["path"])
            request.meta.setdefault("captures", []).append(info["path"])
        else:
            path = capture.new_capture_path("still", "png")
            still = capture.capture_still(context, path, source=base, camera=camera, force_solid=force_solid, runner=runner)
            _add(cap, still)
            request.meta.setdefault("captures", []).append(still)
            if cap.get("first") and request.spark is not None and request.spark.get("kind") == "image":
                request.meta["spark_image"] = still
    request.captures = []
    return request


def request_meta(context, lane, request=None):
    lane_state = context.scene.scenario.lane_state(lane)
    record = runtime.state.records.get(lane_state.model_id)
    meta = {"prompt": lane_state.prompt, "model_name": record.name if record else lane_state.model_id}
    if lane == "material":
        meta["target_objects"] = [o.name for o in context.selected_objects if o.type == 'MESH']
    if request is not None:
        # the local files that went into the job, so Generations can show what was used (like the web app)
        inputs = []
        for paths in request.files.values():
            inputs.extend(p for p in paths if p not in inputs)
        meta["inputs"] = inputs
        meta.update(request.meta)
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
    prepare = None
    if request.spark is not None:
        from . import render_lanes

        prepare = render_lanes.make_prepare(request.spark, request.meta.get("spark_image"), request.meta.get("prompt_name") or "prompt")
    rec = manager.submit(lane, request.kind, request.model_id, request.body, files=request.files,
                         array_params=request.array_params, meta=request_meta(context, lane, request), prepare=prepare)
    runtime.state.jobs_view.insert(0, rec)
    lane_state.last_error = ""
    runtime.set_message(("Prompt Spark is writing the look for " if prepare else "Submitted to ") + rec.meta.get('model_name', rec.model_id))
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
