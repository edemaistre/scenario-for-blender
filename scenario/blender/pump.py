# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-thread pump: drains the job manager's event queue from a bpy.app.timers callback."""
import logging
import time

import bpy

from . import generation, handlers, props, runtime

log = logging.getLogger("scenario.pump")
ESTIMATE_DEBOUNCE = 0.7
ACTIVE_INTERVAL = 0.25
IDLE_INTERVAL = 0.6
_running = False


def start():
    global _running
    if bpy.app.background or _running:
        return
    bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)
    _running = True


def stop():
    global _running
    if _running:
        try:
            bpy.app.timers.unregister(_tick)
        except ValueError:
            pass
    _running = False


def _tick():
    try:
        _process()
    except Exception:  # an exception here would silently kill the timer
        log.exception("pump tick failed")
    manager = runtime.state.manager
    return ACTIVE_INTERVAL if manager is not None and manager.has_active() else IDLE_INTERVAL


def _process():
    manager = runtime.state.manager
    changed = False
    if manager is not None:
        for event in manager.drain():
            handlers.dispatch(event)
            changed = True
    if not runtime.state.catalog_loaded and not runtime.state.catalog_loading and runtime.credentials().valid:
        generation.request_catalog()
    now = time.time()
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            if lane != scene.scenario.lane:
                continue  # only the visible lane is priced; the others are quoted when shown
            lane_state = scene.scenario.lane_state(lane)
            if lane_state.estimate_state == 'PENDING' and lane_state.estimate_dirty_at and now - lane_state.estimate_dirty_at >= ESTIMATE_DEBOUNCE:
                lane_state.estimate_dirty_at = 0.0
                if runtime.credentials().valid and runtime.online():
                    generation.request_estimate(scene, lane)
                changed = True
    if changed:
        redraw()


def redraw():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in ('VIEW_3D', 'PREFERENCES'):
                for region in area.regions:
                    if region.type in ('UI', 'HEADER', 'WINDOW'):
                        region.tag_redraw()
