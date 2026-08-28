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
            on_model_changed(bpy.context, lane_state)


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


def on_model_changed(context, lane_state):
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


def build_request(scene, lane, for_estimate=False):
    lane_state = scene.scenario.lane_state(lane)
    model_id = lane_state.model_id
    schema = schema_for(model_id)
    if schema is None:
        return Request(lane, lane_kind(lane), model_id, {}, errors=["Model not loaded yet"])
    values, enabled = params_ui.collect_values(lane_state, schema)
    refs = params_ui.collect_file_refs(lane_state, schema)
    files, array_params, asset_ids = {}, set(), {}
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
    body = build_body(schema.specs, values, asset_ids, enabled=enabled)
    check = dict(body)
    for name, paths in files.items():
        check.setdefault(name, paths if name in array_params else paths[0])
    errors = validate(schema.specs, check)
    partial = False
    if for_estimate:
        # The dry run rejects unknown asset ids (404), so files still to be uploaded are left out of the quote.
        if missing_required_files(schema.specs, check):
            errors.append("Add a reference to see the cost")
        partial = any(spec.cost_impact and spec.name in files for spec in schema.specs if spec.is_file)
    return Request(lane, lane_kind(lane), model_id, body, files, array_params, errors, partial)


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
