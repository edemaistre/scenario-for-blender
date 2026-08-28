# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Edit 3D lane: the selected mesh is exported at generate time, the result lands next to it."""
import json
import os
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def rec(name):
    catalog = submodule("core.api.catalog")
    return catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


class Edit3DLaneTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        records = [rec("model_meshy-7-retexture"), rec("model_tripo-retopology"), rec("model_meshy-rigging"), rec("model_meshy-7-txt23d")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        self.scene = bpy.context.scene
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
        self.cube = bpy.context.active_object
        self.cube.name = "Hero"

    def test_task_tabs_filter_the_models(self):
        self.scene.scenario.edit3d_task = 'RETEXTURE'
        self.assertEqual([i[0] for i in self.runtime.enum_items(("models", "edit3d"))], ["model_meshy-7-retexture"])
        self.scene.scenario.edit3d_task = 'REMESH'
        self.assertEqual([i[0] for i in self.runtime.enum_items(("models", "edit3d"))], ["model_tripo-retopology"])
        self.scene.scenario.edit3d_task = 'ALL'
        self.assertEqual(len(self.runtime.enum_items(("models", "edit3d"))), 3)

    def test_request_sends_the_selected_mesh_as_the_model_input(self):
        self.scene.scenario.edit3d_task = 'RETEXTURE'
        lane = self.scene.scenario.lane_state("edit3d")
        lane.model_id = "model_meshy-7-retexture"
        lane.prompt = "rusty iron plates"
        request = self.generation.build_request(self.scene, "edit3d")
        self.assertEqual(request.errors, [])
        self.assertEqual(request.kind, "3d")
        self.assertEqual(request.captures[0], {"param": "model", "source": 'MESH', "camera": None, "first": True})
        self.assertEqual(request.body.get("textStylePrompt"), "rusty iron plates")

    def test_request_without_a_mesh_selected_is_refused(self):
        self.scene.scenario.edit3d_task = 'REMESH'
        lane = self.scene.scenario.lane_state("edit3d")
        lane.model_id = "model_tripo-retopology"
        self.cube.select_set(False)
        bpy.context.view_layer.objects.active = None
        request = self.generation.build_request(self.scene, "edit3d")
        self.assertIn("Select the mesh to edit", request.errors)

    def test_export_and_result_placed_next_to_the_source(self):
        mesh_export = submodule("blender.mesh_export")
        apply_3d = submodule("blender.apply_3d")
        records = submodule("core.jobs.records")
        path = mesh_export.export_glb(bpy.context, [self.cube])
        self.assertTrue(os.path.exists(path) and os.path.getsize(path) > 0)
        self.assertTrue(self.cube.select_set)  # selection restored, the cube is still there
        job = records.JobRecord.new(lane="edit3d", kind="3d", model_id="model_meshy-7-retexture", body={}, meta={"source_object": "Hero", "model_name": "Meshy 7 - Retexture", "prompt": "rusty"})
        job.files = [path]
        job.status = "success"
        objects = apply_3d.on_3d_result(job)
        meshes = [o for o in objects if o.type == 'MESH']
        self.assertEqual(len(meshes), 1)
        self.assertIn("Hero", meshes[0].name)
        self.assertEqual(job.meta["objects"], [o.name for o in objects])
        # to the right of the source (its bbox spans x in [-1, 1]), bottoms aligned
        new_min_x = min((meshes[0].matrix_world @ v.co).x for v in meshes[0].data.vertices)
        new_min_z = min((meshes[0].matrix_world @ v.co).z for v in meshes[0].data.vertices)
        self.assertGreater(new_min_x, 1.0)
        self.assertAlmostEqual(new_min_z, 0.0, places=3)

    def test_mesh_param_for_the_curated_models(self):
        catalog = submodule("core.api.catalog")
        self.assertEqual(catalog.mesh_param(rec("model_meshy-7-retexture")), "model")
        self.assertEqual(catalog.mesh_param(rec("model_tripo-retopology")), "model")
        self.assertIsNone(catalog.mesh_param(rec("model_meshy-7-txt23d")))


class ResultObjectTagTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.runtime = submodule("blender.runtime")
        self.runtime.state.reset()

    def test_imported_objects_carry_the_job_tag_and_can_be_selected_and_deleted(self):
        mesh_export = submodule("blender.mesh_export")
        apply_3d = submodule("blender.apply_3d")
        records = submodule("core.jobs.records")
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        cube = bpy.context.active_object
        path = mesh_export.export_glb(bpy.context, [cube])
        job = records.JobRecord.new(lane="3d", kind="3d", model_id="model_meshy-7-txt23d", body={}, meta={"prompt": "a crate"})
        job.files = [path]
        job.status = "success"
        self.runtime.state.jobs_view.insert(0, job)
        objects = apply_3d.on_3d_result(job)
        self.assertTrue(objects)
        self.assertEqual(sorted(o.name for o in apply_3d.objects_of_job(job.local_id)), sorted(o.name for o in objects))
        for obj in objects:
            obj.name = "renamed " + obj.name  # the tag survives renames
        bpy.ops.scenario.select_result_objects(names="", local_id=job.local_id)
        self.assertEqual(sorted(o.name for o in bpy.context.selected_objects), sorted(o.name for o in objects))
        bpy.ops.scenario.delete_result_objects(names="", local_id=job.local_id)
        self.assertEqual(apply_3d.objects_of_job(job.local_id), [])
        self.assertIn(cube.name, bpy.data.objects)
