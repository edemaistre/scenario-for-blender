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
            hit = layout.hit(*state.mouse)
            if hit != state.hover:
                state.hover = hit
                _redraw(context)
            if hit is None and not state.focused:
                return self._finish(context)
            return {'PASS_THROUGH'}
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
                state.sync_from_lane(scene)
                state.focused = True
            elif kind == "generate":
                state.commit_to_lane(scene)
                state.focused = False
                bpy.ops.scenario.generate(lane=state.lane_for(scene))
            elif kind == "model":
                context.space_data.show_region_ui = True
                for region in context.area.regions:
                    if region.type == 'UI':
                        try:
                            region.active_panel_category = "Scenario"
                        except (AttributeError, TypeError):
                            pass
            _redraw(context)
            return {'RUNNING_MODAL'}
        if not state.focused:
            return {'PASS_THROUGH'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        field = state.field
        if event.type == 'ESC':
            state.focused = False
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
            field.move(-1)
        elif event.type == 'RIGHT_ARROW':
            field.move(1)
        elif event.type == 'HOME':
            field.home()
        elif event.type == 'END':
            field.end()
        elif (event.ctrl or event.oskey) and event.type == 'V':
            field.insert(context.window_manager.clipboard or "")
        elif (event.ctrl or event.oskey) and event.type == 'A':
            field.select_all()
        elif event.unicode and not (event.ctrl or event.oskey or event.alt):
            field.insert(event.unicode)
        else:
            return {'RUNNING_MODAL'}
        state.commit_to_lane(scene)
        _redraw(context)
        return {'RUNNING_MODAL'}
