# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

import bpy
from mathutils import Vector

from helpers import reset_scene, submodule


def make_glb(path):
    bpy.ops.mesh.primitive_cube_add(location=(5, 5, 5))
    bpy.ops.export_scene.gltf(filepath=str(path), use_selection=True, export_format='GLB')
    bpy.ops.object.delete()


class Apply3DTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.apply_3d = submodule("blender.apply_3d")
        self.tmp = Path(tempfile.mkdtemp(prefix="scenario-3d-"))
        self.glb = self.tmp / "cube.glb"
        make_glb(self.glb)

    def test_import_places_bottom_center_on_cursor_in_scenario_collection(self):
        bpy.context.scene.cursor.location = (2.0, -3.0, 1.0)
        objects = self.apply_3d.import_model(bpy.context, str(self.glb), at_cursor=True)
        self.assertGreaterEqual(len(objects), 1)
        meshes = [o for o in objects if o.type == 'MESH']
        self.assertEqual(len(meshes), 1)
        obj = meshes[0]
        bpy.context.view_layer.update()
        corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        zmin = min(c.z for c in corners)
        xs = [c.x for c in corners]
        self.assertAlmostEqual(zmin, 1.0, places=3)
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 2.0, places=3)
        self.assertIn(obj.name, bpy.data.collections["Scenario"].objects)
        self.assertIsNotNone(bpy.context.view_layer.objects.active)

    def test_on_3d_result_imports_every_file(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="3d", kind="3d", model_id="model_meshy-7-txt23d", body={})
        rec.files = [str(self.glb)]
        rec.meta["prompt"] = "a cube"
        objects = self.apply_3d.on_3d_result(rec)
        self.assertGreaterEqual(len(objects), 1)
