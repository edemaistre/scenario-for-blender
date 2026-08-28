# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def patina_schema():
    catalog = submodule("core.api.catalog")
    params = submodule("core.schema.params")
    data = json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"]
    return params.parse_schema(catalog.ModelRecord.from_api(data))


class ParamsUiTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.params_ui = submodule("blender.params_ui")
        self.params = submodule("core.schema.params")
        self.props = submodule("blender.props")
        self.lane = bpy.context.scene.scenario.lane_state("material")

    def test_sync_creates_items_with_defaults_and_labels(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        names = [item.name for item in self.lane.params]
        self.assertIn("width", names)
        self.assertNotIn("prompt", names)
        self.assertNotIn("image", names)
        width = self.lane.params["width"]
        self.assertEqual(width.int_value, 1024)
        self.assertEqual((width.fmin, width.fmax), (512.0, 2048.0))
        maps = self.lane.params["maps"]
        self.assertEqual(self.params_ui.multi_selection(maps), ["basecolor", "normal", "roughness", "metalness", "height"])
        tiling = self.lane.params["tilingMode"]
        self.assertEqual(tiling.enum_value, "both")
        upscale = self.lane.params["upscaleFactor"]
        self.assertEqual(upscale.enum_value, "0")

    def test_collect_values_builds_the_recorded_body(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.lane.prompt = "weathered copper patina with verdigris streaks"
        self.lane.params["width"].int_value = 512
        self.lane.params["height"].int_value = 512
        values, enabled = self.params_ui.collect_values(self.lane, schema)
        body = self.params.build_body(schema.specs, values, files={}, enabled=enabled)
        recorded = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())["job"]["metadata"]["input"]
        recorded = {k: v for k, v in recorded.items() if k not in ("modelId", "seed")}
        for key, value in recorded.items():
            self.assertEqual(body.get(key), value, key)

    def test_disabled_optional_is_omitted_and_clamping_applies(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.lane.params["upscaleFactor"].enabled = False
        self.lane.params["width"].int_value = 100_000
        self.assertEqual(self.lane.params["width"].int_value, 2048)
        values, enabled = self.params_ui.collect_values(self.lane, schema)
        self.assertFalse(enabled["upscaleFactor"])

    def test_sync_keeps_compatible_values_across_models_and_drops_others(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.lane.params["width"].int_value = 768
        catalog = submodule("core.api.catalog")
        gemini = json.loads((FIXTURES / "models" / "model_google-gemini-3-1-flash.json").read_text())["model"]
        gschema = self.params.parse_schema(catalog.ModelRecord.from_api(gemini))
        self.params_ui.sync_params(self.lane, gschema, "model_google-gemini-3-1-flash")
        self.assertNotIn("width", [i.name for i in self.lane.params])
        self.assertEqual(self.lane.params["resolution"].enum_value, "1K")
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.assertEqual(self.lane.params["width"].int_value, 1024)

    def test_references_group_by_param(self):
        schema = patina_schema()
        ref = self.lane.references.add()
        ref.param_name, ref.source, ref.filepath = "image", 'FILE', "/tmp/a.png"
        refs = self.params_ui.collect_file_refs(self.lane, schema)
        self.assertEqual([r.filepath for r in refs["image"]], ["/tmp/a.png"])
        self.assertEqual(refs.get("mask", []), [])

    def test_optional_enum_with_empty_default_starts_disabled(self):
        catalog = submodule("core.api.catalog")
        meshy = json.loads((FIXTURES / "models" / "model_meshy-7-txt23d.json").read_text())["model"]
        schema = self.params.parse_schema(catalog.ModelRecord.from_api(meshy))
        lane = bpy.context.scene.scenario.lane_state("3d")
        self.params_ui.sync_params(lane, schema, "model_meshy-7-txt23d")
        pose = lane.params["poseMode"]
        self.assertIn(pose.enum_value, ("a-pose", "t-pose"))
        self.assertFalse(pose.enabled)
        values, enabled = self.params_ui.collect_values(lane, schema)
        body = self.params.build_body(schema.specs, values, files={}, enabled=enabled)
        self.assertNotIn("poseMode", body)
        self.assertEqual(body["topology"], "triangle")

    def test_optional_params_without_default_start_disabled(self):
        catalog = submodule("core.api.catalog")
        gpt = json.loads((FIXTURES / "models" / "model_openai-gpt-image-2.json").read_text())["model"]
        schema = self.params.parse_schema(catalog.ModelRecord.from_api(gpt))
        lane = bpy.context.scene.scenario.lane_state("image")
        self.params_ui.sync_params(lane, schema, "model_openai-gpt-image-2")
        self.assertFalse(lane.params["width"].enabled)
        self.assertEqual(lane.params["width"].int_value, 1024)
        self.assertTrue(lane.params["numOutputs"].enabled)
        values, enabled = self.params_ui.collect_values(lane, schema)
        body = self.params.build_body(schema.specs, dict(values, prompt="x"), files={}, enabled=enabled)
        self.assertNotIn("width", body)
        self.assertEqual(body["numOutputs"], 1)
