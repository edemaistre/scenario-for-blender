# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

import bpy

from helpers import reset_scene, submodule


class CaptureTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.capture = submodule("blender.capture")
        self.tmp = Path(tempfile.mkdtemp(prefix="scenario-cap-"))
        self.calls = []

    def fake_runner(self, kind, context, scene):
        r = scene.render
        self.calls.append({"kind": kind, "res": (r.resolution_x, r.resolution_y, r.resolution_percentage), "fmt": r.image_settings.file_format,
                           "video": self.capture.is_video_output(r), "codec": r.ffmpeg.codec, "path": r.filepath, "range": (scene.frame_start, scene.frame_end), "stamp": r.use_stamp})
        target = Path(bpy.path.abspath(r.filepath))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4" if kind == "animation" else b"png")

    def test_playblast_sets_720p_h264_and_restores_everything(self):
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1920, 1080, 50
        scene.render.use_stamp = True
        scene.frame_start, scene.frame_end = 1, 48
        scene.frame_set(7)
        scene.render.filepath = "//renders/"
        out = self.tmp / "clip.mp4"
        info = self.capture.capture_playblast(bpy.context, str(out), source='VIEWPORT', frame_start=1, frame_end=24, runner=self.fake_runner)
        call = self.calls[0]
        self.assertEqual(call["kind"], "animation")
        self.assertEqual(call["res"], (1280, 720, 100))
        self.assertTrue(call["video"])
        self.assertEqual(call["codec"], 'H264')
        self.assertFalse(call["stamp"])
        self.assertEqual(call["range"], (1, 24))
        self.assertEqual(info["frame_start"], 1)
        self.assertEqual(info["frame_end"], 24)
        fps = scene.render.fps / scene.render.fps_base
        self.assertAlmostEqual(info["seconds"], 24 / fps, places=3)
        self.assertTrue(out.exists())
        self.assertEqual((scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage), (1920, 1080, 50))
        self.assertTrue(scene.render.use_stamp)
        self.assertEqual((scene.frame_start, scene.frame_end), (1, 48))
        self.assertEqual(scene.render.filepath, "//renders/")
        self.assertFalse(self.capture.is_video_output(scene.render))
        self.assertEqual(scene.frame_current, 7)

    def test_still_uses_png_and_camera_source_requires_camera(self):
        bpy.ops.object.camera_add()
        out = self.tmp / "still.png"
        path = self.capture.capture_still(bpy.context, str(out), source='CAMERA', runner=self.fake_runner)
        self.assertEqual(self.calls[0]["kind"], "still")
        self.assertEqual(self.calls[0]["fmt"], 'PNG')
        self.assertTrue(Path(path).exists())
        for obj in list(bpy.data.objects):
            if obj.type == 'CAMERA':
                bpy.data.objects.remove(obj)
        with self.assertRaises(RuntimeError):
            self.capture.capture_still(bpy.context, str(self.tmp / "x.png"), source='CAMERA', runner=self.fake_runner)

    def test_capture_dir_is_under_cache(self):
        self.assertTrue(str(self.capture.capture_dir()).endswith("captures"))
