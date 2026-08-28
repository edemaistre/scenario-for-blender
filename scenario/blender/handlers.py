# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Applies job-manager events on the main thread."""
import logging

import bpy

from . import apply_image, apply_material, generation, props, runtime

log = logging.getLogger("scenario.handlers")

RESULT_HANDLERS = {"image": apply_image.on_image_result, "material": apply_material.on_material_result}


def dispatch(event):
    name, payload = event
    if name == "catalog":
        generation.set_catalog(payload["records"], payload["detailed"])
    elif name == "estimate":
        _on_estimate(payload)
    elif name in ("job", "job_done", "job_failed"):
        _on_job(name, payload)
    elif name == "history":
        from . import history

        history.on_history_event(payload)
    elif name == "error":
        runtime.set_message(str(payload))


def _on_estimate(result):
    log.info("estimate result %s cu=%s error=%s", result.key, result.cu_cost, result.error)
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            if lane_state.estimate_key != result.key:
                continue
            if result.error:
                lane_state.estimate_state = 'ERROR'
                lane_state.estimate_error = result.error
            else:
                lane_state.estimate_state = 'READY'
                lane_state.estimate_cu = float(result.cu_cost or 0.0)
                lane_state.estimate_error = ""


def _on_job(name, rec):
    view = runtime.state.jobs_view
    if not any(r.local_id == rec.local_id for r in view):
        view.insert(0, rec)
    del view[50:]
    if name == "job_done":
        handler = RESULT_HANDLERS.get(rec.kind)
        if handler is None:
            runtime.set_message(f"{rec.kind} result ready in {rec.files[0] if rec.files else 'the output folder'}")
            return
        try:
            handler(rec)
        except Exception as err:  # keep the pump alive, surface the failure
            log.exception("applying result failed")
            runtime.set_message(f"Result downloaded but could not be applied: {err}")
    elif name == "job_failed":
        runtime.set_message(f"Generation failed: {rec.error or rec.status}")
