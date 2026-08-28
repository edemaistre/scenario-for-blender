# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class MaterialLaneTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        data = json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"]
        rec = catalog.ModelRecord.from_api(data)
        handlers.dispatch(("catalog", {"privacy": "public", "records": [rec], "detailed": [rec]}))

    def test_material_request_records_selected_meshes(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        lane = bpy.context.scene.scenario.lane_state("material")
        lane.prompt = "mossy stone"
        request = self.generation.build_request(bpy.context.scene, "material")
        self.assertEqual(request.model_id, "model_patina-material")
        self.assertEqual(request.body["maps"], ["basecolor", "normal", "roughness", "metalness", "height"])
        self.assertEqual(request.errors, [])
        meta = self.generation.request_meta(bpy.context, "material")
        self.assertEqual(meta["target_objects"], [cube.name])

    def test_retile_operator_changes_mapping_scale(self):
        mp = submodule("core.scene.material_plan")
        apply_material = submodule("blender.apply_material")
        manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
        files = [(a["type"], str(FIXTURES / "patina-copper-512" / a["file"])) for a in manifest["assets"]]
        mat = apply_material.build_material(mp.plan_material("T", files))
        bpy.ops.scenario.retile_material(material_name=mat.name, scale=2.5)
        mapping = next(n for n in mat.node_tree.nodes if n.type == 'MAPPING')
        self.assertEqual(tuple(mapping.inputs["Scale"].default_value), (2.5, 2.5, 2.5))
