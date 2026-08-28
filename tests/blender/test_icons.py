# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario's modality icons load into Blender. Icon ids exist only with a GUI (background Blender allocates none,
verified on 5.1: image_size 64x64, icon_id 0), so headless tests check the pixels and the fallback path."""
import importlib
import importlib.util
import sys
import unittest

import bpy

from helpers import ROOT, addon_name


def icons_module():
    name = f"{addon_name()}.blender.icons"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scenario" / "blender" / "icons.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        parent_name, _, leaf = name.rpartition(".")
        setattr(sys.modules.get(parent_name) or importlib.import_module(parent_name), leaf, module)
    return module


class IconsTests(unittest.TestCase):
    def setUp(self):
        self.icons = icons_module()
        if not self.icons.loaded("image"):
            self.icons.register()

    def test_png_files_exist_in_both_sizes(self):
        for name in self.icons.ICON_NAMES:
            self.assertTrue(self.icons.icon_path(name).exists(), name)
            self.assertTrue((self.icons.ICON_DIR / f"{name}_32.png").exists(), name)

    def test_every_icon_loads_with_pixels(self):
        for name in self.icons.ICON_NAMES:
            self.assertTrue(self.icons.loaded(name), name)
        self.assertFalse(self.icons.loaded("nope"))
        self.assertEqual(self.icons.icon("nope"), 0)

    def test_icon_values_or_builtin_fallback(self):
        values = {name: self.icons.icon(name) for name in self.icons.ICON_NAMES}
        if bpy.app.background:
            self.assertEqual(set(values.values()), {0})
            self.assertEqual(self.icons.kwargs("video"), {"icon": 'FILE_MOVIE'})
        else:
            self.assertTrue(all(v > 0 for v in values.values()), values)
            self.assertEqual(len(set(values.values())), len(values))
            self.assertIn("icon_value", self.icons.kwargs("video"))
        self.assertEqual(self.icons.kwargs("nope"), {"icon": 'QUESTION'})
        self.assertEqual(self.icons.builtin("audio"), 'SPEAKER')
        self.assertEqual(self.icons.builtin("3d"), 'MESH_DATA')

    def test_register_twice_is_harmless_and_unregister_clears(self):
        self.icons.register()
        self.assertTrue(self.icons.loaded("3d"))
        self.icons.unregister()
        self.assertFalse(self.icons.loaded("3d"))
        self.icons.register()
        self.assertTrue(self.icons.loaded("3d"))
