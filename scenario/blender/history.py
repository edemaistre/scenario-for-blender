# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generations panel data: cloud job pages merged with local records."""
from . import runtime
from ..core import history as core_history
from ..core.api import assets as assets_api
from ..core.api import jobs as jobs_api
from ..core.api.errors import ScenarioError

MAX_PROMPT_LOOKUPS = 30
_prompt_texts = {}  # asset_id -> prompt text, lives for the session

KIND_BY_LANE = {"image": "image", "video": "video", "3d": "3d", "material": "material"}


def _kinds():
    """model_id -> kind, most specific lane first so Patina (also txt2img) reads as material."""
    kinds = {}
    for lane in ("material", "3d", "video", "image"):
        kind = KIND_BY_LANE.get(lane)
        for record in runtime.state.lane_models.get(lane, []):
            kinds.setdefault(record.id, kind)
    return kinds


def _fetch(manager, client, token, append):
    try:
        rows, next_token = jobs_api.list_jobs(client, page_size=50, token=token)
        for asset_id in core_history.prompt_asset_ids(rows)[:MAX_PROMPT_LOOKUPS]:
            if asset_id in _prompt_texts:
                continue
            try:
                asset = assets_api.get_asset(client, asset_id)
                _prompt_texts[asset_id] = str((asset.get("metadata") or {}).get("preview") or "")
            except ScenarioError:
                _prompt_texts[asset_id] = ""
        core_history.resolve_prompts(rows, _prompt_texts)
    except ScenarioError as err:
        manager.events.put(("error", f"history: {err.reason}"))
        return
    manager.events.put(("history", {"jobs": rows, "token": next_token, "append": append}))


def refresh():
    manager = runtime.ensure_manager()
    manager._spawn(_fetch, manager, runtime.make_client(), None, False)
    return manager


def older():
    token = runtime.state.history_token
    if not token:
        return False
    manager = runtime.ensure_manager()
    manager._spawn(_fetch, manager, runtime.make_client(), token, True)
    return True


def on_history_event(payload):
    manager = runtime.ensure_manager()
    entries = core_history.entries_from_jobs(payload["jobs"], manager.registry.all(), kinds=_kinds())
    if payload.get("append"):
        known = {e.job_id for e in runtime.state.history}
        runtime.state.history.extend(e for e in entries if e.job_id not in known)
    else:
        runtime.state.history = entries
    runtime.state.history_token = payload.get("token")
