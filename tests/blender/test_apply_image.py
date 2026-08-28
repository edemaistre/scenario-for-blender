# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule

ALBEDO = str(FIXTURES / "patina-copper-512" / "albedo.png")


class ApplyImageTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.apply_image = submodule("blender.apply_image")

    def test_load_image_packs(self):
        img = self.apply_image.load_image(ALBEDO)
        self.assertEqual(tuple(img.size), (512, 512))
        self.assertTrue(img.packed_file is not None)

    def test_apply_as_texture_links_base_color(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        img = self.apply_image.load_image(ALBEDO)
        mat = self.apply_image.apply_as_texture(cube, img)
        self.assertEqual(cube.active_material, mat)
        tex = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
        bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        self.assertEqual(tex.image, img)
        link = next(l for l in mat.node_tree.links if l.to_node == bsdf and l.to_socket.name == "Base Color")
        self.assertEqual(link.from_node, tex)

    def test_add_as_plane_matches_aspect_and_cursor(self):
        img = self.apply_image.load_image(ALBEDO)
        bpy.context.scene.cursor.location = (1.0, 2.0, 3.0)
        plane = self.apply_image.add_as_plane(bpy.context, img)
        self.assertEqual(plane.type, 'MESH')
        self.assertAlmostEqual(plane.scale.x / plane.scale.y, 1.0, places=4)
        self.assertAlmostEqual(tuple(plane.location)[2], 3.0, places=4)
        self.assertEqual(len(plane.data.materials), 1)

    def test_on_image_result_loads_every_file(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="image", kind="image", model_id="model_x", body={})
        rec.files = [ALBEDO, str(FIXTURES / "patina-copper-512" / "normal.png")]
        rec.job_id = "job_t"
        names = self.apply_image.on_image_result(rec)
        self.assertEqual(len(names), 2)
        self.assertTrue(all(name in bpy.data.images for name in names))
