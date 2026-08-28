# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Scenario LLM as a text tool (translate, describe, rewrite). No bpy.

`model_scenario-llm` is a catalog model (capabilities txt2txt / img2txt) run like any other generation:
`POST /generate/custom/model_scenario-llm` with `instruction`, optional `textInputs`, `images` (asset ids), `numOutputs`
and `model` (default gemini-3.5-flash-lite). The job costs 0.5 CU (dry run, 2026-08-28) and its output is a text asset
whose content sits in `asset.metadata.preview`, the same place the Generations panel reads archived prompts from."""
import time

from . import assets as assets_api
from . import generate as generate_api
from . import jobs as jobs_api
from .errors import ScenarioError

MODEL_ID = "model_scenario-llm"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
TRANSLATE_INSTRUCTION = ("Translate the text to {target}. Translate faithfully, keep the line breaks and the formatting, "
                         "keep proper nouns and technical terms, do not add comments or quotes: return only the translation.")


def _body(instruction, text_inputs=(), images=(), model=None):
    body = {"instruction": str(instruction), "numOutputs": 1, "model": model or DEFAULT_MODEL}
    if text_inputs:
        body["textInputs"] = [str(t) for t in text_inputs]
    if images:
        body["images"] = list(images)
    return body


def text_from_job(client, job):
    """The text a finished LLM job produced: inline metadata when the API puts it there, else the text asset's preview."""
    meta = (job or {}).get("metadata") or {}
    for key in ("text", "output", "result"):
        value = meta.get(key)
        if isinstance(value, dict):
            value = value.get("text")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for asset_id in jobs_api.asset_ids(job):
        asset = assets_api.get_asset(client, asset_id)
        preview = (asset.get("metadata") or {}).get("preview")
        if isinstance(preview, str) and preview.strip():
            return preview.strip()
    raise ValueError("The Scenario LLM returned no text")


def run_text(client, instruction, text_inputs=(), images=(), model=None, poll_interval=1.5, max_polls=60, sleep=time.sleep):
    """Submit an instruction to the Scenario LLM, wait for the job, return its text (spends credits)."""
    job = generate_api.submit(client, MODEL_ID, _body(instruction, text_inputs, images, model))
    job_id = job.get("jobId")
    polls = 0
    while not jobs_api.is_terminal(job.get("status")):
        if polls >= max_polls:
            raise ScenarioError(0, "The Scenario LLM did not finish in time")
        polls += 1
        sleep(poll_interval)
        job = jobs_api.get_job(client, job_id)
    if not jobs_api.is_success(job.get("status")):
        raise ScenarioError(0, jobs_api.error_text(job) or f"Scenario LLM job {job.get('status')}")
    return text_from_job(client, job)


def translate(client, text, target="English", **kwargs):
    """Translate `text` to `target` (0.5 CU)."""
    return run_text(client, TRANSLATE_INSTRUCTION.format(target=target), text_inputs=[text], **kwargs)


def estimate_text(client, instruction, text_inputs=(), images=(), model=None):
    """Dry run: the CU price of one LLM call (dryRun must be the query parameter, never a body flag)."""
    data = client.post(f"/generate/custom/{MODEL_ID}", query={"dryRun": "true"}, json_body=_body(instruction, text_inputs, images, model))
    return float(data.get("creativeUnitsCost") or 0.0)
