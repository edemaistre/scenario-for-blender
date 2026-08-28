# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Modal operator that owns the mouse and keyboard while the pointer is on the composer or the prompt has focus."""
import bpy

from .. import runtime
from ...core.ui import composer_layout as cl


def _layout(context, state):
    from .draw import ui_scale

    region = context.region
    return cl.pill_placement(region.width, region.height, state.expanded, ui_scale(context),
                             offset=state.offset, width=state.width if state.expanded else None)


def _redraw(context):
    if context.region is not None:
        context.region.tag_redraw()


def _open_sidebar(context):
    from ..popover import open_sidebar

    open_sidebar(context.area)


def _caret_index(context, state, layout, px):
    from .draw import caret_index_at, ui_scale

    return caret_index_at(px, layout.prompt_rect, state.field, ui_scale(context))


def _cursor(context, name):
    window = getattr(context, "window", None)
    if window is None:
        return
    try:
        if name is None:
            window.cursor_modal_restore()
        else:
            window.cursor_modal_set(name)
    except (AttributeError, TypeError, RuntimeError):
        pass


def _save_layout():
    from . import save_layout

    save_layout()


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
            if state.drag_mode is not None:
                state.cancel_drag()
                _cursor(context, None)
        _redraw(context)
        return {'FINISHED'}

    # -- placement drags -------------------------------------------------------
    def _drag_move(self, context, state, event):
        """Mouse moved while the button is held on the card background, the pill or the grip."""
        start = state.drag_start
        dx = event.mouse_region_x - start["mouse"][0]
        dy = event.mouse_region_y - start["mouse"][1]
        scale = _layout(context, state).scale
        if state.drag_mode == "pending":
            if abs(dx) < cl.DRAG_THRESHOLD * scale and abs(dy) < cl.DRAG_THRESHOLD * scale:
                return
            state.drag_mode = "move"
            _cursor(context, 'SCROLL_XY')
        state.moved = True
        region = context.region
        if state.drag_mode == "move":
            state.offset = (start["offset"][0] + dx, start["offset"][1] + dy)
        elif state.drag_mode == "resize":
            base = start["width"] or cl.CARD_WIDTH * scale
            state.width = cl.clamp_width(base + dx, region.width, scale, expanded=True)
        _redraw(context)

    def _drag_release(self, context, state, scene):
        kind, mode, moved = state.end_drag()
        _cursor(context, None)
        if mode in ("move", "resize") and moved:
            # keep the placement inside the region as the layout clamps it, then remember it
            layout = _layout(context, state)
            base_x = (context.region.width - layout.pill_rect.w) / 2
            base_y = cl.MARGIN * layout.scale
            state.offset = (layout.pill_rect.x - base_x, layout.pill_rect.y - base_y)
            _save_layout()
        elif kind == "expand" and not moved:
            state.expanded = True
            state.sync_from_lane(scene)
        _redraw(context)

    def modal(self, context, event):
        state = runtime.state.composer
        if state is None or context.region is None:
            return self._finish(context)
        scene = context.scene
        layout = _layout(context, state)
        if state.drag_mode is not None:
            if event.type == 'MOUSEMOVE':
                state.mouse = (event.mouse_region_x, event.mouse_region_y)
                self._drag_move(context, state, event)
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._drag_release(context, state, scene)
                return {'RUNNING_MODAL'}
            if event.type == 'ESC' and event.value == 'PRESS':
                state.cancel_drag()
                _cursor(context, None)
                _redraw(context)
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}
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
            elif hit in (("drag",), ("resize",)):
                # double-click on the card background puts the composer back at its default place and size
                state.cancel_drag()
                state.reset_layout()
                _save_layout()
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
                # a click expands the pill; a move beyond the threshold drags it instead (decided on release)
                state.begin_drag((event.mouse_region_x, event.mouse_region_y), "expand")
            elif kind == "drag":
                if state.focused:
                    state.focused = False
                    state.commit_to_lane(scene)
                state.begin_drag((event.mouse_region_x, event.mouse_region_y), "drag")
            elif kind == "resize":
                state.begin_drag((event.mouse_region_x, event.mouse_region_y), "resize")
                _cursor(context, 'MOVE_X')
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
