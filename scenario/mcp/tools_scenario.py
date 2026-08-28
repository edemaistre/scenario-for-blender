# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP tools that talk to Scenario through the add-on: catalog, cost, generate, results into the scene."""
import time

import bpy

from .protocol import ToolSpec
from ..blender import generation, runtime
from ..core.api import generate as generate_api
from ..core.schema.params import build_body, validate

LANES = ("image", "video", "3d", "material", "audio", "render_image", "render_video", "edit3d")
KIND = {"image": "image", "video": "video", "3d": "3d", "material": "material", "audio": "audio", "render_image": "image", "render_video": "video", "edit3d": "3d"}


def _catalog_ready():
    if not runtime.state.catalog_loaded:
        generation.request_catalog()
        raise RuntimeError("The model catalog is still loading; call again in a few seconds")


def list_models(args):
    _catalog_ready()
    lane = args.get("lane") or "image"
    if lane not in LANES:
        raise ValueError(f"lane must be one of {LANES}")
    query = (args.get("query") or "").lower()
    records = runtime.state.lane_models.get(lane, [])
    if lane == "3d":
        everything = list(runtime.state.records.values())
        records = generation.three_d_models('TEXT', everything) + generation.three_d_models('IMAGE', everything)
    out, seen = [], set()
    for rec in records:
        if rec.id in seen:
            continue
        seen.add(rec.id)
        if query and query not in (rec.name + " " + rec.short_description + " " + rec.id).lower():
            continue
        out.append({"id": rec.id, "name": rec.name, "description": rec.short_description, "capabilities": list(rec.capabilities)})
    return {"lane": lane, "models": out[:40]}


def model_schema(args):
    record = generation.ensure_record(args["model_id"])
    schema = generation.schema_for(record.id)
    params = []
    for spec in schema.specs:
        item = {"name": spec.name, "type": spec.ptype, "label": spec.label, "required": spec.required_always, "cost_impact": spec.cost_impact}
        if spec.default is not None:
            item["default"] = spec.default
        if spec.allowed_values:
            item["allowed_values"] = list(spec.allowed_values)
        if spec.min is not None or spec.max is not None:
            item["range"] = [spec.min, spec.max]
        if spec.is_file:
            item["file_kind"] = spec.kind or "image"
            item["note"] = "pass a Scenario asset id (capture_reference creates one from the viewport)"
        if spec.description:
            item["description"] = spec.description
        params.append(item)
    return {"model_id": record.id, "name": record.name, "prompt_parameter": schema.prompt_name, "parameters": params}


def _body_for(model_id, parameters):
    record = generation.ensure_record(model_id)
    schema = generation.schema_for(record.id)
    parameters = dict(parameters or {})
    files = {}
    for spec in schema.specs:
        if spec.is_file and spec.name in parameters:
            value = parameters.pop(spec.name)
            files[spec.name] = list(value) if isinstance(value, list) else [value]
    body = build_body(schema.specs, parameters, files)
    errors = validate(schema.specs, body)
    if errors:
        raise ValueError("; ".join(errors))
    return record, body


def estimate_cost(args):
    record, body = _body_for(args["model_id"], args.get("parameters"))
    quote = generate_api.estimate(runtime.make_client(), record.id, body)
    return {"model_id": record.id, "cu_cost": quote.cu_cost, "details": quote.details}


def generate(args):
    import os

    if os.environ.get("SCENARIO_GUI_PROBE") == "1":
        raise PermissionError("Generation is disabled while an automated GUI probe runs")
    lane = args.get("lane") or "image"
    if lane not in LANES:
        raise ValueError(f"lane must be one of {LANES}")
    record, body = _body_for(args["model_id"], args.get("parameters"))
    manager = runtime.ensure_manager()
    meta = {"prompt": str(body.get("prompt") or ""), "model_name": record.name, "source": "mcp",
            "target_objects": [o.name for o in bpy.context.selected_objects if o.type == 'MESH']}
    rec = manager.submit(lane, KIND[lane], record.id, body, meta=meta)
    runtime.state.jobs_view.insert(0, rec)
    return {"local_id": rec.local_id, "status": rec.status, "lane": lane, "model_id": record.id,
            "note": "Poll job_status or wait_for_job; on success the result lands in the scene automatically (image datablock, material on the selection, 3D at the cursor, video file)."}


def _find(local_or_job_id):
    manager = runtime.ensure_manager()
    for rec in manager.registry.all():
        if rec.local_id == local_or_job_id or rec.job_id == local_or_job_id:
            return rec
    raise ValueError(f"Unknown job {local_or_job_id}")


def _status(rec):
    return {"local_id": rec.local_id, "job_id": rec.job_id, "status": rec.status, "progress": rec.progress, "cu_cost": rec.cu_cost,
            "files": list(rec.files), "error": rec.error, "kind": rec.kind}


def job_status(args):
    return _status(_find(args["id"]))


def wait_for_job(args):
    deadline = time.time() + float(args.get("timeout", 170))
    while time.time() < deadline:
        rec = _find(args["id"])
        if rec.is_terminal:
            return _status(rec)
        time.sleep(1.5)
    return dict(_status(_find(args["id"])), note="still running, call again")


def import_result(args):
    from ..blender import handlers

    rec = _find(args["id"])
    if not rec.files:
        raise ValueError("This job has no downloaded files yet")
    rec.meta["target_objects"] = [o.name for o in bpy.context.selected_objects if o.type == 'MESH']
    handlers.dispatch(("job_done", rec))
    return {"applied": rec.kind, "files": list(rec.files)}


def capture_reference(args):
    from ..blender import capture
    from ..core.api import assets

    source = args.get("source") or 'VIEWPORT'
    path = capture.new_capture_path("mcp_ref", "png")
    capture.capture_still(bpy.context, path, source=source, width=1280, height=720)
    asset_id = assets.upload_file(runtime.make_client(), path, kind="image")
    return {"asset_id": asset_id, "path": path}


def list_generations(args):
    from ..blender import history

    if not runtime.state.history:
        history.refresh()
        return {"generations": [], "note": "history requested, call again in a few seconds"}
    limit = int(args.get("limit", 20))
    return {"generations": [{"job_id": e.job_id, "kind": e.kind, "model_id": e.model_id, "prompt": e.prompt, "status": e.status, "cu_cost": e.cu_cost,
                             "local_files": e.local_files} for e in runtime.state.history[:limit]]}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


SPECS = (
    ToolSpec("list_models", "Scenario models usable in a lane (image, video, 3d, material), curated first.", _schema({"lane": {"type": "string", "enum": list(LANES)}, "query": {"type": "string"}}), list_models, {"readOnlyHint": True}),
    ToolSpec("model_schema", "Parameters a model accepts (names, types, defaults, allowed values, which ones affect cost).", _schema({"model_id": {"type": "string"}}, ["model_id"]), model_schema, {"readOnlyHint": True}),
    ToolSpec("estimate_cost", "Exact CU price of a generation without running it (dry run).", _schema({"model_id": {"type": "string"}, "parameters": {"type": "object"}}, ["model_id"]), estimate_cost, {"readOnlyHint": True}, offthread=True),
    ToolSpec("generate", "Submit a Scenario generation; the result is placed in the scene when done. Spends the user's credits.",
             _schema({"lane": {"type": "string", "enum": list(LANES)}, "model_id": {"type": "string"}, "parameters": {"type": "object", "description": "Model parameters; file parameters take Scenario asset ids"}}, ["lane", "model_id"]), generate),
    ToolSpec("job_status", "Status, progress, cost and files of a generation.", _schema({"id": {"type": "string", "description": "local_id or job_id"}}, ["id"]), job_status, {"readOnlyHint": True}),
    ToolSpec("wait_for_job", "Block up to timeout seconds until a generation finishes.", _schema({"id": {"type": "string"}, "timeout": {"type": "number"}}, ["id"]), wait_for_job, {"readOnlyHint": True}, offthread=True),
    ToolSpec("import_result", "Bring a finished generation into the scene again (image, material on the selection, 3D at the cursor).", _schema({"id": {"type": "string"}}, ["id"]), import_result),
    ToolSpec("capture_reference", "Capture the viewport or the scene camera as a still and upload it; returns an asset id to use as a reference parameter.", _schema({"source": {"type": "string", "enum": ["VIEWPORT", "CAMERA"]}}), capture_reference),
    ToolSpec("list_generations", "Recent generations of this project (cloud history).", _schema({"limit": {"type": "integer"}}), list_generations, {"readOnlyHint": True}),
)
