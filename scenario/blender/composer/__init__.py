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


def save_layout():
    """Remember where the user put the composer (offset from the default spot, card width) in the preferences."""
    state, prefs = runtime.state.composer, runtime.prefs()
    if state is None or prefs is None:
        return False
    prefs.composer_offset_x, prefs.composer_offset_y = float(state.offset[0]), float(state.offset[1])
    prefs.composer_width = int(state.width or 0)
    return True


def load_layout():
    """Apply the remembered placement to the composer state (0 width means the default)."""
    state, prefs = runtime.state.composer, runtime.prefs()
    if state is None or prefs is None:
        return False
    state.offset = (float(getattr(prefs, "composer_offset_x", 0.0)), float(getattr(prefs, "composer_offset_y", 0.0)))
    width = int(getattr(prefs, "composer_width", 0) or 0)
    state.width = width if width > 0 else None
    return True


def _load_pre(*args):
    if runtime.state.composer is not None:
        runtime.state.composer.__init__()
        load_layout()
    runtime.state.composer_modal_running = False


class SCENARIO_OT_composer_reset_layout(bpy.types.Operator):
    bl_idname = "scenario.composer_reset_layout"
    bl_label = "Reset composer placement"
    bl_description = "Put the floating composer back at the bottom centre of the viewport with its default width"

    def execute(self, context):
        state = runtime.state.composer
        if state is not None:
            state.cancel_drag()
            state.reset_layout()
        save_layout()
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        return {'FINISHED'}


def register():
    global _keymap
    bpy.utils.register_class(SCENARIO_OT_composer_modal)
    bpy.utils.register_class(SCENARIO_OT_composer_reset_layout)
    runtime.state.composer = ComposerState()
    runtime.state.composer_modal_running = False
    load_layout()
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
    bpy.utils.unregister_class(SCENARIO_OT_composer_reset_layout)
    bpy.utils.unregister_class(SCENARIO_OT_composer_modal)
