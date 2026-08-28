# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import importlib.util
import sys
import unittest

import bpy

from helpers import ROOT, addon_name, reset_scene, submodule


def load_module(dotted, rel_file):
    """Import a module of the installed extension; when the installed build predates the file, load it from the repo
    under the installed package name so its relative imports resolve against the running add-on."""
    name = f"{addon_name()}.{dotted}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scenario" / rel_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module


def picker_module():
    load_module("core.api.model_filter", "core/api/model_filter.py")
    picker = load_module("blender.model_picker", "blender/model_picker.py")
    if not hasattr(bpy.types, "SCENARIO_OT_pick_model"):
        picker.register()
    return picker


def fake_records():
    catalog = submodule("core.api.catalog")
    return [
        catalog.ModelRecord.from_api({"id": "model_openai-gpt-image-2", "name": "GPT Image 2", "capabilities": ["txt2img", "img2img"], "tags": ["sc:featured", "sc:third-party"],
                                      "shortDescription": "Best-in-class prompt adherence", "inputs": [{"name": "prompt", "type": "string", "prompt": True, "required": {"always": True}}]}),
        catalog.ModelRecord.from_api({"id": "model_z-image", "name": "Z-Image", "capabilities": ["txt2img"], "tags": ["sc:third-party"], "shortDescription": "Fast open model",
                                      "inputs": [{"name": "prompt", "type": "string", "prompt": True, "required": {"always": True}}]}),
        catalog.ModelRecord.from_api({"id": "model_chibis", "name": "3D Chibis", "capabilities": ["txt2img"], "tags": ["sc:scenario"], "shortDescription": "Cute chibi characters",
                                      "inputs": [{"name": "prompt", "type": "string", "prompt": True, "required": {"always": True}}]}),
    ]


class ModelPickerTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.picker = picker_module()
        runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        records = fake_records()
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        self.runtime = runtime
        wm = bpy.context.window_manager
        wm.scenario_picker_chip = 'all'
        wm.scenario_picker_query = ""

    def test_registered_classes_and_window_manager_props(self):
        self.assertTrue(hasattr(bpy.types, "SCENARIO_UL_models"))
        self.assertTrue(hasattr(bpy.types, "SCENARIO_OT_pick_model"))
        wm = bpy.context.window_manager
        for name in ("scenario_picker_items", "scenario_picker_index", "scenario_picker_query", "scenario_picker_chip"):
            self.assertTrue(hasattr(wm, name), name)

    def test_prepare_fills_rows_featured_first_and_highlights_current(self):
        scene = bpy.context.scene
        lane_state = scene.scenario.lane_state("image")
        lane_state.model_id = "model_z-image"
        items = self.picker.prepare(bpy.context, "image")
        self.assertEqual([i.model_id for i in items], ["model_openai-gpt-image-2", "model_chibis", "model_z-image"])
        self.assertEqual(items[bpy.context.window_manager.scenario_picker_index].model_id, "model_z-image")
        self.assertEqual(items[0].icon_name, 'IMAGE_DATA')
        self.assertEqual(items[0].description, "Best-in-class prompt adherence")

    def test_query_and_chip_refilter_live(self):
        self.picker.prepare(bpy.context, "image")
        wm = bpy.context.window_manager
        wm.scenario_picker_query = "chibi"
        self.assertEqual([i.model_id for i in wm.scenario_picker_items], ["model_chibis"])
        wm.scenario_picker_query = ""
        wm.scenario_picker_chip = 'featured'
        self.assertEqual([i.model_id for i in wm.scenario_picker_items], ["model_openai-gpt-image-2"])
        wm.scenario_picker_chip = 'all'
        self.assertEqual(len(wm.scenario_picker_items), 3)

    def test_execute_sets_model_key_and_records_recent(self):
        scene = bpy.context.scene
        lane_state = scene.scenario.lane_state("image")
        self.picker.prepare(bpy.context, "image")
        wm = bpy.context.window_manager
        wm.scenario_picker_index = [i.model_id for i in wm.scenario_picker_items].index("model_chibis")
        result = bpy.ops.scenario.pick_model(lane="image")
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(lane_state.model_key, "model_chibis")
        self.assertEqual(lane_state.model_id, "model_chibis")
        recent = self.picker._recent()
        self.assertEqual(recent.ids("image")[0], "model_chibis")
        wm.scenario_picker_chip = 'recent'
        self.assertEqual([i.model_id for i in wm.scenario_picker_items][0], "model_chibis")

    def test_execute_without_rows_is_cancelled(self):
        wm = bpy.context.window_manager
        self.picker.prepare(bpy.context, "image")
        wm.scenario_picker_query = "nothing-matches-this"
        self.assertEqual(len(wm.scenario_picker_items), 0)
        self.assertEqual(bpy.ops.scenario.pick_model(lane="image"), {'CANCELLED'})

    def test_draw_model_row_and_thumbnail_helpers_do_not_touch_the_network(self):
        scene = bpy.context.scene
        lane_state = scene.scenario.lane_state("image")
        lane_state.model_id = "model_openai-gpt-image-2"
        record = self.runtime.state.records["model_openai-gpt-image-2"]
        self.assertFalse(self.picker.ensure_thumbnail(record))       # no thumbnail url on the record: nothing to fetch
        self.assertEqual(self.picker.thumbnail_icon(record.id), 0)
        # drawing into a real layout is only possible during a draw call; the row helper must at least resolve its labels
        self.assertEqual(self.picker.model_filter.modality_icon(record), 'IMAGE_DATA')
        self.assertTrue(callable(self.picker.draw_model_row))
