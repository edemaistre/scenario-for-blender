# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generations panel data: cloud job pages merged with local records."""
import threading

from . import runtime
from ..core import history as core_history
from ..core.api import jobs as jobs_api
from ..core.api.errors import ScenarioError

KIND_BY_LANE = {"image": "image", "video": "video", "3d": "3d", "material": "material"}


def _kinds():
    kinds = {}
    for lane, records in runtime.state.lane_models.items():
        kind = KIND_BY_LANE.get(lane)
        if kind:
            for record in records:
                kinds.setdefault(record.id, kind)
    return kinds


def _fetch(manager, token, append):
    try:
        client = runtime.make_client()
        rows, next_token = jobs_api.list_jobs(client, page_size=50, token=token)
    except ScenarioError as err:
        manager.events.put(("error", f"history: {err.reason}"))
        return
    manager.events.put(("history", {"jobs": rows, "token": next_token, "append": append}))


def refresh():
    manager = runtime.ensure_manager()
    threading.Thread(target=_fetch, args=(manager, None, False), daemon=True, name="scenario-history").start()
    return manager


def older():
    token = runtime.state.history_token
    if not token:
        return False
    manager = runtime.ensure_manager()
    threading.Thread(target=_fetch, args=(manager, token, True), daemon=True, name="scenario-history").start()
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
