# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import addon, addon_name, submodule


class RegisterTests(unittest.TestCase):
    def test_extension_enabled_and_prefs_have_defaults(self):
        mod = addon()
        self.assertEqual(mod.__version__, "0.1.0")
        prefs = bpy.context.preferences.addons[addon_name()].preferences
        self.assertEqual(prefs.output_dir, "~/Downloads/Scenario")
        self.assertEqual(prefs.mcp_port, 9876)
        self.assertTrue(prefs.composer_enabled)

    def test_runtime_paths_live_outside_the_extension_dir(self):
        runtime = submodule("blender.runtime")
        paths = runtime.paths()
        self.assertTrue(str(paths.state_dir).endswith("state"))
        self.assertNotIn("extensions/user_default/scenario/", str(paths.state_dir).replace("\\", "/") + "/")
        self.assertTrue(paths.state_dir.exists())

    def test_credentials_resolve_from_prefs(self):
        runtime = submodule("blender.runtime")
        prefs = bpy.context.preferences.addons[addon_name()].preferences
        prefs.api_key, prefs.api_secret = "k", "s"
        try:
            self.assertTrue(runtime.credentials().valid)
        finally:
            prefs.api_key, prefs.api_secret = "", ""
