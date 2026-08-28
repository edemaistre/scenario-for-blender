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
