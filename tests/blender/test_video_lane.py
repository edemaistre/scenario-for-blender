# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest
from pathlib import Path

import bpy

from helpers import FIXTURES, reset_scene, submodule


class VideoLaneTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        data = json.loads((FIXTURES / "models" / "model_bytedance-seedance-2-0.json").read_text())["model"]
        rec = catalog.ModelRecord.from_api(data)
        handlers.dispatch(("catalog", {"privacy": "public", "records": [rec], "detailed": [rec]}))
        self.scene = bpy.context.scene
        self.scene.scenario.lane = "video"
        self.lane = self.scene.scenario.lane_state("video")

    def test_match_timeline_sets_duration_from_frame_range(self):
        self.scene.frame_start, self.scene.frame_end = 1, 150
        self.scene.render.fps, self.scene.render.fps_base = 24, 1.0
        schema = self.generation.schema_for(self.lane.model_id)
        value, note, seconds = self.generation.apply_match_timeline(self.scene, self.lane, schema)
        self.assertEqual(value, 7)
        self.assertAlmostEqual(seconds, 6.25, places=3)
        self.assertEqual(self.lane.params["duration"].enum_value, "7")
        self.assertTrue(self.lane.params["duration"].enabled)

    def test_clip_reference_becomes_a_pending_capture_then_a_file(self):
        ref = self.lane.references.add()
        ref.param_name, ref.source = "referenceVideos", 'VIEWPORT_CLIP'
        self.lane.prompt = "a wolf running"
        request = self.generation.build_request(self.scene, "video")
        self.assertEqual(request.captures, [{"param": "referenceVideos", "source": 'VIEWPORT_CLIP', "camera": None}])
        self.assertEqual(request.errors, [])
        made = []

        def runner(kind, context, scene):
            made.append(kind)
            target = Path(bpy.path.abspath(scene.render.filepath))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"mp4")

        self.generation.perform_captures(bpy.context, request, runner=runner)
        self.assertEqual(made, ["animation"])
        self.assertEqual(len(request.files["referenceVideos"]), 1)
        self.assertTrue(request.files["referenceVideos"][0].endswith(".mp4"))
        self.assertTrue(request.body["prompt"].startswith("@video1"))

    def test_estimate_skips_captures_and_marks_partial(self):
        ref = self.lane.references.add()
        ref.param_name, ref.source = "referenceVideos", 'CAMERA_CLIP'
        request = self.generation.build_request(self.scene, "video", for_estimate=True)
        self.assertTrue(request.partial)
        self.assertNotIn("referenceVideos", request.body)
