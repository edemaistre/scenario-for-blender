# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import submodule


class PopoverTests(unittest.TestCase):
    def test_popover_panel_registered_and_header_hooked(self):
        popover = submodule("blender.popover")
        self.assertTrue(hasattr(bpy.types, "SCENARIO_PT_popover"))
        self.assertIn('INSTANCED', bpy.types.SCENARIO_PT_popover.bl_options)
        draw_funcs = [f.__name__ for f in bpy.types.VIEW3D_HT_header._dyn_ui_initialize()]
        self.assertIn(popover.draw_header_button.__name__, draw_funcs)
