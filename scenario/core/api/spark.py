# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt Spark: Scenario's prompt writer (POST /generate/prompt). No bpy.

Verified 2026-08-28 against the live API: the body takes `prompt` (draft or intent, optional), `modelId` (optional; with
it Prompt Spark conditions on the model, "contextual" mode, 3.75 CU; without it "structured" mode, 0.75 CU),
`images` (asset ids or data URLs; unknown asset ids fail with 404) and `numResults` (1 to 5, +0.125 CU each beyond
the first). The response is {"prompts": [str, ...], "mode": ..., "job": {...}, "creativeUnitsCost": ...}.
`?dryRun=true` returns the price only (HTTP 269 like every dry run)."""
import base64
import pathlib

from .assets import mime_for_path

PATH = "/generate/prompt"


def data_url(path):
    """Inline an image file so Prompt Spark can look at it without an upload round trip."""
    path = pathlib.Path(path)
    return f"data:{mime_for_path(path)};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _body(prompt, model_id, images, num_results):
    body = {"numResults": max(1, min(5, int(num_results or 1)))}
    if prompt and prompt.strip():
        body["prompt"] = prompt.strip()
    if model_id:
        body["modelId"] = model_id
    if images:
        body["images"] = list(images)
    return body


def parse_prompts(data):
    """Prompt strings out of a Prompt Spark response, tolerant of dict entries ({"prompt": ...} / {"text": ...})."""
    out = []
    for item in (data or {}).get("prompts") or []:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("prompt") or item.get("text") or ""
        else:
            text = str(item)
        text = " ".join(str(text).split())
        if text:
            out.append(text)
    return out


def spark(client, prompt=None, model_id=None, images=(), num_results=1):
    """Run Prompt Spark and return the prompt variants (spends credits)."""
    data = client.post(PATH, json_body=_body(prompt, model_id, images, num_results))
    prompts = parse_prompts(data)
    if not prompts:
        raise ValueError("Prompt Spark returned no prompt")
    return prompts


def estimate(client, prompt=None, model_id=None, images=(), num_results=1):
    """Dry run: the CU price of the call."""
    data = client.post(PATH, query={"dryRun": "true"}, json_body=_body(prompt, model_id, images, num_results))
    return float(data.get("creativeUnitsCost") or 0.0)
