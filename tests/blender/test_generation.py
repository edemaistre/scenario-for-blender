# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class GenerationTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        self.catalog = submodule("core.api.catalog")
        self.handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        patina = json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"]
        gemini = json.loads((FIXTURES / "models" / "model_google-gemini-3-1-flash.json").read_text())["model"]
        records = [self.catalog.ModelRecord.from_api(patina), self.catalog.ModelRecord.from_api(gemini)]
        self.handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))

    def test_catalog_event_fills_lane_enums_and_syncs_params(self):
        items = self.runtime.enum_items(("models", "image"))
        ids = [i[0] for i in items]
        self.assertEqual(ids[0], "model_google-gemini-3-1-flash")
        self.assertIn("model_patina-material", ids)
        self.assertEqual([i[0] for i in self.runtime.enum_items(("models", "material"))], ["model_patina-material"])
        lane = bpy.context.scene.scenario.lane_state("image")
        self.assertEqual(lane.model_id, "model_google-gemini-3-1-flash")
        self.assertIn("resolution", [p.name for p in lane.params])

    def test_estimate_event_updates_lane_state(self):
        lane = bpy.context.scene.scenario.lane_state("image")
        lane.estimate_key = "image:k1"
        lane.estimate_state = 'PENDING'
        est = submodule("core.jobs.manager").EstimateResult(key="image:k1", cu_cost=13.25)
        self.handlers.dispatch(("estimate", est))
        self.assertEqual(lane.estimate_state, 'READY')
        self.assertAlmostEqual(lane.estimate_cu, 13.25)
        bad = submodule("core.jobs.manager").EstimateResult(key="image:k1", error="Input prompt is required")
        self.handlers.dispatch(("estimate", bad))
        self.assertEqual(lane.estimate_state, 'ERROR')
        self.assertIn("prompt", lane.estimate_error)

    def test_build_request_from_scene_state(self):
        lane = bpy.context.scene.scenario.lane_state("image")
        lane.prompt = "a copper teapot"
        lane.params["resolution"].enum_value = "2K"
        ref = lane.references.add()
        ref.param_name, ref.source, ref.filepath = "referenceImages", 'FILE', str(FIXTURES / "patina-copper-512" / "albedo.png")
        request = self.generation.build_request(bpy.context.scene, "image")
        self.assertEqual(request.model_id, "model_google-gemini-3-1-flash")
        self.assertEqual(request.body["prompt"], "a copper teapot")
        self.assertEqual(request.body["resolution"], "2K")
        self.assertEqual(request.files["referenceImages"], [str(FIXTURES / "patina-copper-512" / "albedo.png")])
        self.assertIn("referenceImages", request.array_params)
        self.assertEqual(request.errors, [])

    def test_job_done_event_for_image_loads_images(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="image", kind="image", model_id="model_x", body={})
        rec.job_id, rec.status = "job_done_1", "success"
        rec.files = [str(FIXTURES / "patina-copper-512" / "albedo.png")]
        self.handlers.dispatch(("job_done", rec))
        self.assertTrue(any(img.filepath.endswith("albedo.png") for img in bpy.data.images))
        self.assertTrue(any(r.job_id == "job_done_1" for r in self.runtime.state.jobs_view))

    def test_estimate_dirty_timestamp_fits_a_float_property(self):
        props = submodule("blender.props")
        lane = bpy.context.scene.scenario.lane_state("image")
        props.mark_estimate_dirty(lane)
        self.assertLess(lane.estimate_dirty_at, 1e6)  # relative clock, not an epoch (FloatProperty is 32-bit)
        self.assertGreaterEqual(props.clock() - lane.estimate_dirty_at, 0.0)
        self.assertEqual(lane.estimate_key, "")
