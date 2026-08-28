# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import reset_scene, submodule


def _view3d_area():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                return area
    return None


class HeaderButtonTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.popover = submodule("blender.popover")

    def test_operator_replaces_the_popover_and_is_hooked_in_the_header(self):
        self.assertTrue(hasattr(bpy.types, "SCENARIO_OT_open_panel"))
        self.assertFalse(hasattr(bpy.types, "SCENARIO_PT_popover"))
        draw_funcs = [f.__name__ for f in bpy.types.VIEW3D_HT_header._dyn_ui_initialize()]
        self.assertIn(self.popover.draw_header_button.__name__, draw_funcs)

    def test_open_sidebar_shows_the_ui_region_of_a_3d_view(self):
        area = _view3d_area()
        if area is None:
            self.skipTest("no 3D viewport in the background screen")
        area.spaces.active.show_region_ui = False
        self.assertTrue(self.popover.open_sidebar(area))
        self.assertTrue(area.spaces.active.show_region_ui)
        self.assertFalse(self.popover.open_sidebar(None))
        other = next((a for s in bpy.data.screens for a in s.areas if a.type != 'VIEW_3D'), None)
        if other is not None:
            self.assertFalse(self.popover.open_sidebar(other))

    def test_operator_runs_in_a_3d_view_override(self):
        window = next(iter(bpy.context.window_manager.windows), None)
        area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None) if window is not None else None
        if area is None:
            self.skipTest("no window with a 3D viewport in background mode")
        area.spaces.active.show_region_ui = False
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        with bpy.context.temp_override(window=window, area=area, region=region):
            result = bpy.ops.scenario.open_panel()
        self.assertEqual(result, {'FINISHED'})
        self.assertTrue(area.spaces.active.show_region_ui)
