# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render Image and Render Video lanes: capture first, precise prompts, Prompt Spark when the look is empty."""
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def rec(name):
    catalog = submodule("core.api.catalog")
    return catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


class RenderLanesTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.render_lanes = submodule("blender.render_lanes")
        self.runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        records = [rec("model_google-gemini-3-1-flash"), rec("model_openai-gpt-image-2"), rec("model_bytedance-seedance-2-0"), rec("model_minimax-h3")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        self.scene = bpy.context.scene
        self.image_lane = self.scene.scenario.lane_state("render_image")
        self.video_lane = self.scene.scenario.lane_state("render_video")

    def test_lane_tabs_have_no_generations_or_mcp(self):
        props = submodule("blender.props")
        ids = [item[0] for item in props.LANE_ITEMS]
        self.assertEqual(ids, ["image", "video", "3d", "material", "render_image", "render_video", "edit3d"])
        self.assertIsNotNone(self.scene.scenario.lane_state("render_image"))
        self.assertIsNotNone(self.scene.scenario.lane_state("edit3d"))

    def test_render_image_request_puts_the_capture_first_and_writes_the_scene_prompt(self):
        self.image_lane.model_id = "model_google-gemini-3-1-flash"
        self.image_lane.prompt = "weathered steampunk copper"
        style = self.image_lane.references.add()
        style.param_name, style.source, style.filepath = "referenceImages", 'FILE', str(FIXTURES / "patina-copper-512" / "albedo.png")
        request = self.generation.build_request(self.scene, "render_image")
        self.assertEqual(request.errors, [])
        self.assertEqual(request.kind, "image")
        self.assertEqual(request.captures[0]["param"], "referenceImages")
        self.assertTrue(request.captures[0]["first"])
        self.assertEqual(request.captures[0]["source"], 'CAMERA')
        prompt = request.body["prompt"]
        self.assertTrue(prompt.startswith("Image 1 is a screenshot of a 3D viewport"))
        self.assertIn("weathered steampunk copper", prompt)
        self.assertIn("Image 2 is a style reference only", prompt)
        self.assertIsNone(request.spark)
        self.assertEqual(request.meta["render_lane"], "render_image")

    def test_empty_look_asks_prompt_spark_and_uses_the_default_look_meanwhile(self):
        self.image_lane.model_id = "model_google-gemini-3-1-flash"
        self.image_lane.prompt = ""
        self.image_lane.capture_source = 'VIEWPORT'
        request = self.generation.build_request(self.scene, "render_image")
        self.assertEqual(request.errors, [])
        self.assertEqual(request.spark, {"kind": "image", "style_count": 0})
        self.assertEqual(request.captures[0]["source"], 'VIEWPORT')
        self.assertIn("photorealistic", request.body["prompt"])
        self.image_lane.spark_enabled = False
        request = self.generation.build_request(self.scene, "render_image")
        self.assertIsNone(request.spark)

    def test_render_video_seedance_request_tags_inputs_and_uses_the_first_frame(self):
        self.video_lane.model_id = "model_bytedance-seedance-2-0"
        self.video_lane.prompt = "claymation"
        self.video_lane.first_frame_path = str(FIXTURES / "patina-copper-512" / "albedo.png")
        self.scene.frame_start, self.scene.frame_end = 1, 48
        request = self.generation.build_request(self.scene, "render_video")
        self.assertEqual(request.errors, [])
        self.assertEqual(request.kind, "video")
        self.assertEqual(request.captures[0]["param"], "referenceVideos")
        self.assertEqual(request.captures[0]["source"], 'CAMERA_CLIP')
        self.assertEqual(request.files["image"], [self.video_lane.first_frame_path])  # Seedance's single image input is the first frame
        prompt = request.body["prompt"]
        self.assertIn("@video1 is a playblast", prompt)
        self.assertIn("@image1 shows how the finished first frame must look", prompt)
        self.assertIn("claymation", prompt)
        self.assertEqual(request.body["duration"], 4)

    def test_render_video_without_tags_for_minimax(self):
        self.video_lane.model_id = "model_minimax-h3"
        self.video_lane.prompt = "oil painting"
        self.video_lane.first_frame_path = ""
        request = self.generation.build_request(self.scene, "render_video")
        self.assertEqual(request.captures[0]["param"], "referenceVideos")
        prompt = request.body["prompt"]
        self.assertTrue(prompt.startswith("The reference video is a playblast"))
        self.assertNotIn("@video1", prompt)
        self.assertIsNone(request.spark)

    def test_empty_video_look_adds_a_spark_still_capture(self):
        self.video_lane.model_id = "model_bytedance-seedance-2-0"
        self.video_lane.prompt = ""
        request = self.generation.build_request(self.scene, "render_video")
        roles = [c.get("role") for c in request.captures]
        self.assertIn("spark", roles)
        self.assertEqual(request.spark["kind"], "video")

    def test_render_image_result_becomes_the_video_first_frame(self):
        records = submodule("core.jobs.records")
        job = records.JobRecord.new(lane="render_image", kind="image", model_id="model_google-gemini-3-1-flash", body={}, meta={"render_lane": "render_image", "spark_look": "warm brass"})
        job.files = [str(FIXTURES / "patina-copper-512" / "albedo.png")]
        job.status = "success"
        self.render_lanes.on_result(job)
        self.assertEqual(self.video_lane.first_frame_path, job.files[0])
        self.assertEqual(self.image_lane.spark_look, "warm brass")

    def test_prepare_writes_the_spark_look_into_the_body(self):
        class FakeClient:
            def post(self, path, json_body=None, query=None):
                assert path == "/generate/prompt"
                assert json_body["images"][0].startswith("data:image/png;base64,")
                return {"prompts": ["brushed brass under studio light"]}

        records = submodule("core.jobs.records")
        job = records.JobRecord.new(lane="render_image", kind="image", model_id="m", body={"prompt": "placeholder"}, meta={})
        prepare = self.render_lanes.make_prepare({"kind": "image", "style_count": 1}, str(FIXTURES / "patina-copper-512" / "albedo.png"), "prompt")
        prepare(FakeClient(), job)
        self.assertIn("brushed brass under studio light", job.body["prompt"])
        self.assertIn("Image 2 is a style reference only", job.body["prompt"])
        self.assertEqual(job.meta["spark_look"], "brushed brass under studio light")

    def test_panels_are_registered_as_four_sections(self):
        for name in ("SCENARIO_PT_main", "SCENARIO_PT_jobs", "SCENARIO_PT_generations", "SCENARIO_PT_agents"):
            self.assertTrue(hasattr(bpy.types, name), name)
        self.assertFalse(hasattr(bpy.types, "SCENARIO_PT_results"))
