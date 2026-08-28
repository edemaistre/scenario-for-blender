# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import sys
import unittest

import bpy

from helpers import ROOT, reset_scene, submodule


def load_shot_planner():
    """The installed extension when it ships the module, else the source tree (so the test runs before a reinstall)."""
    try:
        module = submodule("blender.shot_planner")
    except ImportError:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        module = importlib.import_module("scenario.blender.shot_planner")
    if not hasattr(bpy.types.Scene, "scenario_shot"):
        module.register()
    return module


class ShotPlannerTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.sp = load_shot_planner()
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.0))
        self.scene = bpy.context.scene
        self.props = self.scene.scenario_shot
        self.fps = self.scene.render.fps / (self.scene.render.fps_base or 1.0)

    def _location_keys(self, cam):
        curves = [fc for fc in self.sp.fcurves_of(cam) if fc.data_path == "location"]
        self.assertEqual(len(curves), 3)
        return sorted({int(k.co[0]) for k in curves[0].keyframe_points})

    def test_markers_are_numbered_cameras_and_build_a_marker_path(self):
        self.scene.cursor.location = (4.0, -4.0, 2.0)
        bpy.ops.scenario.shot_add_marker()
        self.scene.cursor.location = (-4.0, -4.0, 3.0)
        bpy.ops.scenario.shot_add_marker()
        markers = self.sp.marker_objects(self.scene)
        self.assertEqual([m.name for m in markers], ["Shot 1", "Shot 2"])
        self.assertEqual([int(m["scenario_shot_index"]) for m in markers], [1, 2])
        self.assertTrue(all(m.type == 'CAMERA' and m.show_name for m in markers))
        self.assertIn(markers[0].name, bpy.data.collections["Scenario Shots"].objects)
        self.props.duration = 5.0
        bpy.ops.scenario.shot_build_path()
        cam = self.sp.shot_camera(self.scene)
        self.assertIsNotNone(cam)
        self.assertEqual(self.scene.camera, cam)
        frames = self._location_keys(cam)
        self.assertEqual(frames[0], 1)
        self.assertEqual(frames[-1], round(5.0 * self.fps))
        self.assertEqual(self.scene.frame_end, frames[-1])
        self.assertEqual(self.scene.frame_start, 1)
        self.assertEqual(cam["scenario_shot_source"], "markers")
        # the path starts at marker 1 and ends at marker 2
        self.scene.frame_set(1)
        self.assertAlmostEqual((cam.matrix_world.translation - markers[0].matrix_world.translation).length, 0.0, places=4)
        self.scene.frame_set(frames[-1])
        self.assertAlmostEqual((cam.matrix_world.translation - markers[1].matrix_world.translation).length, 0.0, places=4)
        constraint = cam.constraints.get("Scenario Aim")
        self.assertIsNotNone(constraint)
        self.assertEqual(constraint.target.name, "Shot Target")

    def test_preset_path_without_markers_orbits_the_subject(self):
        self.props.preset = 'orbit'
        self.props.duration = 4.0
        self.props.focal = 35.0
        bpy.ops.scenario.shot_build_path()
        cam = self.sp.shot_camera(self.scene)
        frames = self._location_keys(cam)
        self.assertEqual(len(frames), 13)
        self.assertEqual(frames[-1], round(4.0 * self.fps))
        self.assertEqual(cam["scenario_shot_source"], "orbit")
        target = bpy.data.objects["Shot Target"]
        self.assertAlmostEqual(target.location.z, 1.0, places=4)
        self.scene.frame_set(1)
        first = cam.matrix_world.translation.copy()
        self.scene.frame_set(frames[-1])
        self.assertAlmostEqual((cam.matrix_world.translation - first).length, 0.0, places=3)
        self.scene.frame_set(frames[6])
        self.assertGreater((cam.matrix_world.translation - first).length, 1.0)

    def test_aim_off_keyframes_rotation_and_no_target(self):
        self.props.aim_at_subject = False
        self.props.preset = 'dolly_in'
        bpy.ops.scenario.shot_build_path()
        cam = self.sp.shot_camera(self.scene)
        paths = {fc.data_path for fc in self.sp.fcurves_of(cam)}
        self.assertIn("rotation_euler", paths)
        self.assertIsNone(cam.constraints.get("Scenario Aim"))
        self.assertIsNone(bpy.data.objects.get("Shot Target"))
        # the camera looks at the cube: its -Z axis points from the camera towards the centre
        self.scene.frame_set(1)
        forward = cam.matrix_world.to_quaternion() @ __import__("mathutils").Vector((0.0, 0.0, -1.0))
        towards = (__import__("mathutils").Vector((0.0, 0.0, 1.0)) - cam.matrix_world.translation).normalized()
        self.assertGreater(forward.dot(towards), 0.99)

    def test_from_description_sets_the_settings_and_builds(self):
        self.props.description = "slow push in closer, 8s at 50mm"
        bpy.ops.scenario.shot_from_description()
        self.assertEqual(self.props.preset, 'dolly_in')
        self.assertAlmostEqual(self.props.duration, 12.0, places=3)
        self.assertAlmostEqual(self.props.focal, 50.0, places=3)
        cam = self.sp.shot_camera(self.scene)
        self.assertIsNotNone(cam)
        self.assertAlmostEqual(cam.data.lens, 50.0, places=3)
        self.assertEqual(self.scene.frame_end, round(12.0 * self.fps))

    def test_marker_lens_is_keyframed_when_markers_differ(self):
        self.scene.cursor.location = (3.0, -3.0, 1.0)
        bpy.ops.scenario.shot_add_marker()
        self.scene.cursor.location = (-3.0, -3.0, 1.0)
        bpy.ops.scenario.shot_add_marker()
        markers = self.sp.marker_objects(self.scene)
        markers[1]["scenario_focal"] = 85.0
        markers[1]["scenario_hold"] = 1.0
        self.props.duration = 6.0
        bpy.ops.scenario.shot_build_path()
        cam = self.sp.shot_camera(self.scene)
        lens_curves = [fc for fc in self.sp.fcurves_of(cam.data) if fc.data_path == "lens"]
        self.assertEqual(len(lens_curves), 1)
        frames = self._location_keys(cam)
        self.assertEqual(len(frames), 3)  # marker 1, marker 2, marker 2 held
        self.assertEqual(frames[-1] - frames[-2], round(1.0 * self.fps))

    def test_remove_clear_and_renumber(self):
        for x in (1.0, 2.0, 3.0):
            self.scene.cursor.location = (x, -3.0, 1.0)
            bpy.ops.scenario.shot_add_marker()
        markers = self.sp.marker_objects(self.scene)
        self.sp.remove_marker(markers[0])
        self.sp.renumber_markers(self.scene)
        self.assertEqual([m.name for m in self.sp.marker_objects(self.scene)], ["Shot 1", "Shot 2"])
        bpy.ops.scenario.shot_remove_last_marker()
        self.assertEqual(len(self.sp.marker_objects(self.scene)), 1)
        bpy.ops.scenario.shot_clear_markers()
        self.assertEqual(self.sp.marker_objects(self.scene), [])
        self.assertEqual([o for o in bpy.data.objects if o.name.startswith("Shot ")], [])

    def test_subject_bbox_falls_back_without_meshes(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.assertEqual(self.sp.subject_bbox(bpy.context), self.sp.FALLBACK_BOX)

    def test_rebuild_replaces_the_previous_path(self):
        bpy.ops.scenario.shot_build_path()
        self.props.preset = 'pan'
        self.props.duration = 3.0
        bpy.ops.scenario.shot_build_path()
        cam = self.sp.shot_camera(self.scene)
        frames = self._location_keys(cam)
        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[-1], round(3.0 * self.fps))
        self.assertEqual(len([c for c in cam.constraints if c.name == "Scenario Aim"]), 1)
        self.assertEqual(len([o for o in bpy.data.objects if o.type == 'CAMERA' and o.name.startswith("Scenario Shot Camera")]), 1)
