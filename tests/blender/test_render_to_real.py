# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class RenderToRealTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.rtr = submodule("blender.render_to_real")
        self.runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        records = [catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{n}.json").read_text())["model"])
                   for n in ("model_google-gemini-3-1-flash", "model_bytedance-seedance-2-0")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        self.scene = bpy.context.scene
        self.lane = self.scene.scenario.lane_state("render")
        self.lane.prompt = "cyborg wolf in a ruined city"

    def test_concept_request_uses_a_viewport_still_and_the_style_prompt(self):
        request = self.rtr.concept_request(bpy.context)
        self.assertEqual(request.model_id, "model_google-gemini-3-1-flash")
        self.assertEqual(request.kind, "image")
        self.assertEqual(request.captures[0]["param"], "referenceImages")
        self.assertIn("cyborg wolf", request.body["prompt"])
        self.assertEqual(request.errors, [])

    def test_video_request_wraps_prompt_and_uses_concept_and_playblast(self):
        self.lane.concept_path = str(FIXTURES / "patina-copper-512" / "albedo.png")
        self.scene.frame_start, self.scene.frame_end = 1, 96
        request = self.rtr.video_request(bpy.context)
        self.assertEqual(request.model_id, "model_bytedance-seedance-2-0")
        self.assertEqual(request.kind, "video")
        self.assertEqual(request.captures[0]["param"], "referenceVideos")
        self.assertEqual(request.files["referenceImages"], [self.lane.concept_path])
        self.assertIn("@video1", request.body["prompt"])
        self.assertIn("grayscale playblast", request.body["prompt"])
        self.assertEqual(request.body["duration"], 4)
        self.assertEqual(request.errors, [])

    def test_concept_result_is_remembered_on_the_lane(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="render", kind="image", model_id="model_google-gemini-3-1-flash", body={}, meta={"render_step": "concept"})
        rec.files = [str(FIXTURES / "patina-copper-512" / "albedo.png")]
        rec.status = "success"
        self.rtr.on_result(rec)
        self.assertEqual(self.lane.concept_path, rec.files[0])
