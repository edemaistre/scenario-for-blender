# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt Spark: Scenario's prompt writer (POST /generate/prompt). No bpy.

Verified 2026-08-28 against the live API: the body takes `prompt` (draft or intent, optional), `modelId` (optional; with
it Prompt Spark conditions on the model, "contextual" mode, 3.75 CU when the model supports it, otherwise it stays in
"structured" mode at 0.75 CU), `images` (asset ids or data URLs; unknown asset ids fail with 404) and `numResults`
(1 to 5, +0.125 CU each beyond the first). The response is {"prompts": [...], "mode": ..., "job": {...},
"creativeUnitsCost": ...}. `?dryRun=true` returns the price only (HTTP 269 like every dry run).

The `prompts` entries are usually strings. For some models the API answers with asset ids instead (2026-08-29:
`modelId=model_meshy-7-txt23d` returned `["asset_cuteLowPolyRobot"]`, an id that does not resolve); a real text asset
carries its text in `metadata.preview`. `spark()` resolves what it can and never hands an `asset_` id back as a prompt."""
import base64
import pathlib

from .assets import get_asset, mime_for_path
from .errors import ScenarioError

PATH = "/generate/prompt"
NO_PROMPT = "Prompt Spark returned no usable prompt for this model"


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


def is_asset_ref(text):
    """An `asset_...` id standing where a prompt should be."""
    return isinstance(text, str) and text.startswith("asset_") and " " not in text.strip()


def parse_prompts(data):
    """Prompt strings out of a Prompt Spark response, tolerant of dict entries ({"prompt": ...} / {"text": ...})."""
    out = []
    for item in (data or {}).get("prompts") or []:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("prompt") or item.get("text") or item.get("assetId") or ""
        else:
            text = str(item)
        text = " ".join(str(text).split())
        if text:
            out.append(text)
    return out


def resolve_prompts(client, prompts):
    """Replace `asset_` ids by the text of the asset (`metadata.preview` or `metadata.text`); drop the ones that do
    not exist or carry no text. Plain strings pass through."""
    out = []
    for text in prompts:
        if not is_asset_ref(text):
            out.append(text)
            continue
        try:
            asset = get_asset(client, text.strip())
        except ScenarioError:
            continue
        meta = (asset or {}).get("metadata") or {}
        value = meta.get("preview") or meta.get("text") or ""
        value = " ".join(str(value).split())
        if value and not is_asset_ref(value):
            out.append(value)
    return out


def spark(client, prompt=None, model_id=None, images=(), num_results=1):
    """Run Prompt Spark and return the prompt variants as text (spends credits).

    Raises ValueError(NO_PROMPT) when the answer holds nothing usable, so callers can fall back to another writer."""
    data = client.post(PATH, json_body=_body(prompt, model_id, images, num_results))
    prompts = resolve_prompts(client, parse_prompts(data))
    if not prompts:
        raise ValueError(NO_PROMPT)
    return prompts


def estimate(client, prompt=None, model_id=None, images=(), num_results=1):
    """Dry run: the CU price of the call."""
    data = client.post(PATH, query={"dryRun": "true"}, json_body=_body(prompt, model_id, images, num_results))
    return float(data.get("creativeUnitsCost") or 0.0)
