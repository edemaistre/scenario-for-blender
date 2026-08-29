# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gaussian splats land as point clouds; a generation's parameters reload into the form; image actions route references."""
import json
import os
import tempfile
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def rec(name):
    catalog = submodule("core.api.catalog")
    return catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


class SplatImportTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.runtime = submodule("blender.runtime")
        self.runtime.state.reset()

    def test_spz_result_becomes_a_coloured_point_cloud(self):
        spz = submodule("core.scene.spz")
        apply_3d = submodule("blender.apply_3d")
        records = submodule("core.jobs.records")
        path = os.path.join(tempfile.mkdtemp(prefix="scenario-spz-"), "world.spz")
        positions = [(float(i) * 0.1, 1.0, float(i % 3)) for i in range(50)]
        spz.write_spz(path, positions, [(0.9, 0.2, 0.1)] * 50, scales=[0.02] * 50)
        job = records.JobRecord.new(lane="3d", kind="3d", model_id="model_worldlabs-marble-1-0-draft", body={}, meta={"prompt": "a world"})
        job.files = [path]
        job.status = "success"
        objects = apply_3d.on_3d_result(job)
        self.assertEqual(len(objects), 1)
        obj = objects[0]
        self.assertEqual(len(obj.data.vertices), 50)
        self.assertIn("color", obj.data.color_attributes)
        self.assertEqual(obj["scenario_splat_points"], 50)
        # Y-up file became Z-up: the file's y=1 is Blender's z=1
        self.assertAlmostEqual(min(v.co.z for v in obj.data.vertices) - min(v.co.z for v in obj.data.vertices), 0.0)
        self.assertTrue(any(m.type == 'NODES' for m in obj.modifiers))
        self.assertIn("World loaded as a point cloud", self.runtime.state.last_message)

    def test_placement_ranks_splats_after_meshes(self):
        placement = submodule("core.scene.placement")
        self.assertEqual(placement.importer_for("x.spz"), "spz")
        self.assertEqual(placement.importer_for("x.ply"), "ply")


class ReloadAndImageActionTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        records = [rec("model_openai-gpt-image-2"), rec("model_tripo-v3-1-image-to-3d"), rec("model_meshy-7-txt23d")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        self.scene = bpy.context.scene

    def test_reload_generation_restores_model_prompt_settings_and_references(self):
        records = submodule("core.jobs.records")
        image = str(FIXTURES / "patina-copper-512" / "albedo.png")
        job = records.JobRecord.new(lane="image", kind="image", model_id="model_openai-gpt-image-2",
                                    body={"prompt": "a copper kettle", "numOutputs": 2, "quality": "high", "referenceImages": ["asset_ref1"]},
                                    meta={"prompt": "a copper kettle", "model_name": "GPT Image 2", "inputs": [image]})
        job.status = "success"
        self.runtime.state.jobs_view.insert(0, job)
        self.scene.scenario.lane = "video"
        bpy.ops.scenario.reload_generation(local_id=job.local_id)
        self.assertEqual(self.scene.scenario.lane, "image")
        lane = self.scene.scenario.lane_state("image")
        self.assertEqual(lane.model_id, "model_openai-gpt-image-2")
        self.assertEqual(lane.prompt, "a copper kettle")
        self.assertEqual(lane.params["numOutputs"].int_value, 2)
        self.assertEqual(lane.params["quality"].enum_value, "high")
        refs = [(r.param_name, r.source, r.filepath) for r in lane.references]
        self.assertEqual(refs, [("referenceImages", 'FILE', image)])

    def test_reload_edit3d_restores_the_task_and_model(self):
        # reloading a Meshy 7 Retexture generation from a different Edit task must switch the task so the model is in
        # the enum and restores, keep the settings, and NOT restore the mesh as a stale asset (it comes from selection)
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        records = [rec("model_meshy-7-retexture"), rec("model_tripo-retopology"), rec("model_meshy-7-txt23d")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        recs = submodule("core.jobs.records")
        job = recs.JobRecord.new(lane="edit3d", kind="3d", model_id="model_meshy-7-retexture",
                                 body={"textStylePrompt": "rusty iron", "model": "asset_oldmesh", "textureResolution": "4k", "enablePbr": True},
                                 meta={"prompt": "rusty iron", "model_name": "Meshy 7 - Retexture", "inputs": []})
        job.status = "success"
        self.runtime.state.jobs_view.insert(0, job)
        self.scene.scenario.lane = "3d"
        self.scene.scenario.three_d_mode = 'EDIT'
        self.scene.scenario.edit3d_task = 'REMESH'  # a different task; the retexture model is not in its list
        bpy.ops.scenario.reload_generation(local_id=job.local_id)
        self.assertEqual(self.scene.scenario.edit3d_task, 'RETEXTURE')
        lane = self.scene.scenario.lane_state("edit3d")
        self.assertEqual(lane.model_id, "model_meshy-7-retexture")
        self.assertEqual(lane.prompt, "rusty iron")
        self.assertEqual(lane.params["textureResolution"].enum_value, "4k")
        self.assertTrue(lane.params["enablePbr"].bool_value)
        self.assertEqual([r.param_name for r in lane.references], [])  # no stale mesh asset restored

    def test_convert_to_3d_opens_the_3d_tab_in_image_mode_with_the_picture(self):
        image = str(FIXTURES / "patina-copper-512" / "albedo.png")
        self.scene.scenario.lane = "image"
        bpy.ops.scenario.convert_to_3d(filepath=image)
        self.assertEqual(self.scene.scenario.lane, "3d")
        self.assertEqual(self.scene.scenario.three_d_mode, 'IMAGE')
        lane = self.scene.scenario.lane_state("3d")
        self.assertTrue(any(r.filepath == image and r.source == 'FILE' for r in lane.references))

    def test_use_as_reference_targets_the_image_lane(self):
        image = str(FIXTURES / "patina-copper-512" / "albedo.png")
        bpy.ops.scenario.use_as_reference(filepath=image, target='image')
        lane = self.scene.scenario.lane_state("image")
        self.assertEqual(self.scene.scenario.lane, "image")
        self.assertEqual([r.param_name for r in lane.references], ["referenceImages"])

    def test_quick_settings_operator_exists_with_a_description(self):
        self.assertTrue(hasattr(bpy.types, "SCENARIO_OT_quick_settings"))
        self.assertTrue(getattr(bpy.types.SCENARIO_OT_quick_settings, "bl_description", "") or bpy.types.SCENARIO_OT_quick_settings.bl_rna.description)
