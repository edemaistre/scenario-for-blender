# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def rec(name):
    catalog = submodule("core.api.catalog")
    return catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


class ThreeDLaneTests(unittest.TestCase):
    def setUp(self):
        reset_scene()

    def test_three_d_models_by_mode(self):
        generation = submodule("blender.generation")
        records = [rec("model_meshy-7-txt23d"), rec("model_meshy-7-img23d"), rec("model_tripo-v3-1-image-to-3d")]
        self.assertEqual([r.id for r in generation.three_d_models('TEXT', records)], ["model_meshy-7-txt23d"])
        image_ids = [r.id for r in generation.three_d_models('IMAGE', records)]
        self.assertIn("model_tripo-v3-1-image-to-3d", image_ids)
        multi_ids = [r.id for r in generation.three_d_models('MULTI', records)]
        self.assertIn("model_meshy-7-img23d", multi_ids)
        self.assertNotIn("model_meshy-7-txt23d", multi_ids)

    def test_mode_change_refreshes_model_enum(self):
        runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        records = [rec("model_meshy-7-txt23d"), rec("model_meshy-7-img23d")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        scene = bpy.context.scene
        scene.scenario.three_d_mode = 'TEXT'
        self.assertEqual([i[0] for i in runtime.enum_items(("models", "3d"))], ["model_meshy-7-txt23d"])
        scene.scenario.three_d_mode = 'MULTI'
        self.assertEqual([i[0] for i in runtime.enum_items(("models", "3d"))], ["model_meshy-7-img23d"])

    def test_list_only_models_are_classified_by_name(self):
        generation = submodule("blender.generation")
        catalog = submodule("core.api.catalog")
        multi = catalog.ModelRecord.from_api({"id": "model_tripo-v3-1-multiview-to-3d", "name": "Tripo 3.1 Multi View", "capabilities": ["img23d"]})
        single = catalog.ModelRecord.from_api({"id": "model_hitem-3d-3-0", "name": "Hitem3D 3.0", "capabilities": ["img23d"]})
        self.assertEqual([r.id for r in generation.three_d_models('MULTI', [multi, single])], ["model_tripo-v3-1-multiview-to-3d"])
        self.assertEqual([r.id for r in generation.three_d_models('IMAGE', [multi, single])], ["model_hitem-3d-3-0"])

    def test_rodin_material_override_applies_when_allowed(self):
        params_ui = submodule("blender.params_ui")
        params = submodule("core.schema.params")
        catalog = submodule("core.api.catalog")
        rec = catalog.ModelRecord.from_api({"id": "model_rodin-hyper3d-v2-5-text-to-3d", "name": "Rodin", "capabilities": ["txt23d"],
                                            "inputs": [{"name": "prompt", "type": "string", "prompt": True, "required": {"always": True}},
                                                       {"name": "material", "type": "string", "allowedValues": ["PBR", "Shaded", "All", "None"], "default": "All"}]})
        schema = params.parse_schema(rec)
        lane = bpy.context.scene.scenario.lane_state("3d")
        params_ui.sync_params(lane, schema, rec.id)
        self.assertEqual(lane.params["material"].enum_value, "PBR")
        self.assertTrue(lane.params["material"].enabled)
