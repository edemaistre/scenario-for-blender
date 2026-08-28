# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Floating composer: registration, draw handler lifecycle, keymap and breaker."""
import logging

import bpy

from .. import runtime
from .breaker import Breaker
from .modal import SCENARIO_OT_composer_modal
from .state import ComposerState

log = logging.getLogger("scenario.composer")
_handler = None
_keymap = None
_breaker = None


def _on_trip(reason):
    log.error("composer disabled: %s", reason)
    runtime.set_message(f"Floating composer disabled after an error ({reason}); re-enable it in Preferences")
    remove_handler()
    prefs = runtime.prefs()
    if prefs is not None:
        prefs.composer_enabled = False


def _draw():
    from . import draw

    if _breaker is not None:
        _breaker.guard(draw.draw_composer)


def add_handler():
    global _handler, _breaker
    if _handler is not None or bpy.app.background:
        return
    if _breaker is None:
        _breaker = Breaker("composer", on_trip=_on_trip)
    _breaker.reset()
    _handler = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')


def remove_handler():
    global _handler
    if _handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        except ValueError:
            pass
        _handler = None


def set_enabled(enabled):
    if enabled:
        add_handler()
    else:
        remove_handler()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _load_pre(*args):
    if runtime.state.composer is not None:
        runtime.state.composer.__init__()
    runtime.state.composer_modal_running = False


def register():
    global _keymap
    bpy.utils.register_class(SCENARIO_OT_composer_modal)
    runtime.state.composer = ComposerState()
    runtime.state.composer_modal_running = False
    prefs = runtime.prefs()
    if prefs is None or prefs.composer_enabled:
        add_handler()
    kc = bpy.context.window_manager.keyconfigs.addon if bpy.context.window_manager else None
    if kc is not None:
        km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
        _keymap = (km, km.keymap_items.new(SCENARIO_OT_composer_modal.bl_idname, 'MOUSEMOVE', 'ANY', head=True))
    if _load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_load_pre)


def unregister():
    global _keymap
    if _load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_load_pre)
    remove_handler()
    if _keymap is not None:
        km, kmi = _keymap
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
        _keymap = None
    runtime.state.composer = None
    bpy.utils.unregister_class(SCENARIO_OT_composer_modal)
