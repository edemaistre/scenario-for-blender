# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Modal operator that owns the mouse and keyboard while the pointer is on the composer or the prompt has focus."""
import bpy

from .. import runtime
from ...core.ui import composer_layout as cl


def _layout(context, state):
    from .draw import ui_scale

    region = context.region
    return cl.pill_placement(region.width, region.height, state.expanded, ui_scale(context))


def _redraw(context):
    if context.region is not None:
        context.region.tag_redraw()


def _open_sidebar(context):
    from ..popover import open_sidebar

    open_sidebar(context.area)


def _caret_index(context, state, layout, px):
    from .draw import caret_index_at, ui_scale

    return caret_index_at(px, layout.prompt_rect, state.field, ui_scale(context))


class SCENARIO_OT_composer_modal(bpy.types.Operator):
    bl_idname = "scenario.composer_modal"
    bl_label = "Scenario composer"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        prefs = runtime.prefs()
        return runtime.state.composer is not None and (prefs is None or prefs.composer_enabled) and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        state = runtime.state.composer
        if state is None or context.region is None or context.region.type != 'WINDOW':
            return {'PASS_THROUGH', 'CANCELLED'}
        layout = _layout(context, state)
        inside = layout.hit(event.mouse_region_x, event.mouse_region_y) is not None
        if not inside and not state.focused:
            return {'PASS_THROUGH', 'CANCELLED'}
        if getattr(runtime.state, "composer_modal_running", False):
            return {'PASS_THROUGH', 'CANCELLED'}
        runtime.state.composer_modal_running = True
        state.mouse = (event.mouse_region_x, event.mouse_region_y)
        context.window_manager.modal_handler_add(self)
        _redraw(context)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        runtime.state.composer_modal_running = False
        state = runtime.state.composer
        if state is not None:
            state.hover = None
            state.dragging = False
        _redraw(context)
        return {'FINISHED'}

    def modal(self, context, event):
        state = runtime.state.composer
        if state is None or context.region is None:
            return self._finish(context)
        scene = context.scene
        layout = _layout(context, state)
        if event.type == 'MOUSEMOVE':
            state.mouse = (event.mouse_region_x, event.mouse_region_y)
            if state.dragging and state.focused and layout.prompt_rect is not None:
                state.field.caret_at(_caret_index(context, state, layout, event.mouse_region_x), extend=True)
                _redraw(context)
                return {'RUNNING_MODAL'}
            hit = layout.hit(*state.mouse)
            if hit != state.hover:
                state.hover = hit
                _redraw(context)
            if hit is None and not state.focused:
                return self._finish(context)
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if state.dragging:
                state.dragging = False
                _redraw(context)
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'} if not state.focused else {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'DOUBLE_CLICK':
            hit = layout.hit(event.mouse_region_x, event.mouse_region_y)
            if hit == ("prompt",) and state.expanded:
                state.sync_from_lane(scene)
                state.focused = True
                state.field.select_word_at(_caret_index(context, state, layout, event.mouse_region_x))
                state.dragging = False
                _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            hit = layout.hit(event.mouse_region_x, event.mouse_region_y)
            if hit is None:
                state.focused = False
                state.commit_to_lane(scene)
                return self._finish(context)
            kind = hit[0]
            if kind == "expand":
                state.expanded = True
                state.sync_from_lane(scene)
            elif kind == "collapse":
                state.focused = False
                state.commit_to_lane(scene)
                state.expanded = False
            elif kind == "tab":
                state.commit_to_lane(scene)
                scene.scenario.lane = hit[1]
                state.sync_from_lane(scene)
            elif kind == "prompt":
                if not state.focused:
                    state.sync_from_lane(scene)
                state.focused = True
                state.field.caret_at(_caret_index(context, state, layout, event.mouse_region_x), extend=event.shift)
                state.dragging = True
            elif kind == "generate":
                state.commit_to_lane(scene)
                state.focused = False
                bpy.ops.scenario.generate(lane=state.lane_for(scene))
            elif kind == "model":
                # the model chip opens the search dialog; the sidebar shows the rest of the form
                _open_sidebar(context)
                try:
                    bpy.ops.scenario.pick_model('INVOKE_DEFAULT', lane=state.lane_for(scene))
                except (RuntimeError, AttributeError):
                    pass
            elif kind == "settings":
                _open_sidebar(context)
            _redraw(context)
            return {'RUNNING_MODAL'}
        if not state.focused:
            return {'PASS_THROUGH'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        field = state.field
        command = event.ctrl or event.oskey
        if event.type == 'ESC':
            state.focused = False
            state.dragging = False
            state.commit_to_lane(scene)
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type in ('RET', 'NUMPAD_ENTER'):
            state.commit_to_lane(scene)
            state.focused = False
            bpy.ops.scenario.generate(lane=state.lane_for(scene))
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == 'BACK_SPACE':
            field.backspace()
        elif event.type == 'DEL':
            field.delete()
        elif event.type == 'LEFT_ARROW':
            field.move(-1, extend=event.shift)
        elif event.type == 'RIGHT_ARROW':
            field.move(1, extend=event.shift)
        elif event.type == 'HOME':
            field.home(extend=event.shift)
        elif event.type == 'END':
            field.end(extend=event.shift)
        elif command and event.type == 'V':
            field.insert(context.window_manager.clipboard or "")
        elif command and event.type == 'A':
            field.select_all()
        elif command and event.type == 'C':
            context.window_manager.clipboard = field.copy()
            _redraw(context)
            return {'RUNNING_MODAL'}  # the text did not change
        elif command and event.type == 'X':
            context.window_manager.clipboard = field.cut()
        elif event.unicode and not (command or event.alt):
            field.insert(event.unicode)
        else:
            return {'RUNNING_MODAL'}
        state.commit_to_lane(scene)
        _redraw(context)
        return {'RUNNING_MODAL'}
