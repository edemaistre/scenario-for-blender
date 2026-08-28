# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A native floating composer: a header button opening a popover with model, prompt and Generate."""
import bpy

from . import panels, runtime


class SCENARIO_PT_popover(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Scenario"
    bl_options = {'INSTANCED'}
    bl_ui_units_x = 22

    def draw(self, context):
        layout = self.layout
        scenario = context.scene.scenario
        if not runtime.credentials().valid:
            layout.label(text="Add your API key in Preferences", icon='ERROR')
            return
        row = layout.row(align=True)
        row.prop(scenario, "lane", text="")
        lane = scenario.lane if scenario.lane in panels.GENERATE_LANES else "image"
        lane_state = scenario.lane_state(lane)
        if not runtime.state.catalog_loaded:
            layout.label(text="Loading models...", icon='TIME')
            return
        layout.prop(lane_state, "model_id", text="")
        layout.prop(lane_state, "prompt", text="")
        layout.operator("scenario.generate", text=panels.generate_button_text(lane_state), icon='PLAY').lane = lane
        if lane_state.last_error:
            layout.label(text=lane_state.last_error[:60], icon='ERROR')


def draw_header_button(self, context):
    if context.space_data is None or context.space_data.type != 'VIEW_3D':
        return
    self.layout.popover(panel="SCENARIO_PT_popover", text="Scenario", icon='SHADERFX')


def register():
    bpy.utils.register_class(SCENARIO_PT_popover)
    bpy.types.VIEW3D_HT_header.append(draw_header_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_header_button)
    bpy.utils.unregister_class(SCENARIO_PT_popover)
