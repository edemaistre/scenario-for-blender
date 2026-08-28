# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def typed_files():
    manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
    return [(a["type"], str(FIXTURES / "patina-copper-512" / a["file"])) for a in manifest["assets"]]


def node_of(mat, ntype):
    return [n for n in mat.node_tree.nodes if n.type == ntype]


def link_into(mat, node, socket_name):
    return next((l for l in mat.node_tree.links if l.to_node == node and l.to_socket.name == socket_name), None)


class ApplyMaterialTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.mp = submodule("core.scene.material_plan")
        self.apply_material = submodule("blender.apply_material")

    def test_build_material_wires_pbr_graph(self):
        mat = self.apply_material.build_material(self.mp.plan_material("Copper", typed_files()))
        bsdf = node_of(mat, 'BSDF_PRINCIPLED')[0]
        images = node_of(mat, 'TEX_IMAGE')
        self.assertEqual(len(images), 5)
        base = link_into(mat, bsdf, "Base Color")
        self.assertEqual(base.from_node.image.colorspace_settings.name, "sRGB")
        rough = link_into(mat, bsdf, "Roughness")
        self.assertEqual(rough.from_node.type, 'INVERT')
        smooth_tex = link_into(mat, rough.from_node, "Color").from_node
        self.assertEqual(smooth_tex.image.colorspace_settings.name, "Non-Color")
        self.assertEqual(link_into(mat, bsdf, "Metallic").from_node.type, 'TEX_IMAGE')
        self.assertEqual(link_into(mat, bsdf, "Normal").from_node.type, 'NORMAL_MAP')
        output = node_of(mat, 'OUTPUT_MATERIAL')[0]
        self.assertEqual(link_into(mat, output, "Displacement").from_node.type, 'DISPLACEMENT')
        mapping = node_of(mat, 'MAPPING')
        self.assertEqual(len(mapping), 1)
        for tex in images:
            self.assertIsNotNone(link_into(mat, tex, "Vector"))

    def test_assign_to_selected_meshes_and_tiling(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        bpy.ops.mesh.primitive_uv_sphere_add()
        sphere = bpy.context.active_object
        mat = self.apply_material.build_material(self.mp.plan_material("Copper", typed_files()))
        self.apply_material.assign_to_objects(mat, [cube, sphere])
        self.assertEqual(cube.active_material, mat)
        self.assertEqual(sphere.active_material, mat)
        self.apply_material.set_tiling(mat, 3.0)
        mapping = node_of(mat, 'MAPPING')[0]
        self.assertEqual(tuple(mapping.inputs["Scale"].default_value), (3.0, 3.0, 3.0))

    def test_on_material_result_uses_recorded_targets(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="material", kind="material", model_id="model_patina-material", body={"prompt": "copper"})
        manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
        rec.asset_ids = [a["assetId"] for a in manifest["assets"]]
        rec.asset_types = {a["assetId"]: a["type"] for a in manifest["assets"]}
        rec.files = [str(FIXTURES / "patina-copper-512" / a["file"]) for a in manifest["assets"]]
        rec.meta["target_objects"] = [cube.name]
        rec.meta["prompt"] = "weathered copper"
        mat = self.apply_material.on_material_result(rec)
        self.assertEqual(cube.active_material, mat)
        self.assertTrue(mat.name.startswith("Scenario weathered copper"))
