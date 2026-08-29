# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class McpToolsTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.tb = submodule("mcp.tools_blender")
        self.ts = submodule("mcp.tools_scenario")
        self.sandbox = submodule("mcp.sandbox")
        bpy.ops.mesh.primitive_cube_add(location=(1, 2, 3))
        bpy.context.active_object.name = "Crate"

    def test_scene_summary_and_object_detail(self):
        summary = self.tb.scene_summary({})
        names = [o["name"] for o in summary["objects"]]
        self.assertIn("Crate", names)
        self.assertEqual(summary["frame_range"], [bpy.context.scene.frame_start, bpy.context.scene.frame_end])
        detail = self.tb.object_detail({"name": "Crate"})
        self.assertEqual(detail["type"], 'MESH')
        self.assertAlmostEqual(detail["location"][2], 3.0)
        self.assertIn("vertices", detail)
        with self.assertRaises(ValueError):
            self.tb.object_detail({"name": "Nope"})

    def test_blender_api_help_returns_docs_and_properties(self):
        op = self.tb.blender_api_help({"path": "bpy.ops.mesh.primitive_cube_add"})
        self.assertEqual(op["path"], "bpy.ops.mesh.primitive_cube_add")
        self.assertIn("properties", op)
        self.assertIn("size", [p["name"] for p in op["properties"]])
        data = self.tb.blender_api_help({"path": "bpy.data.objects"})
        self.assertTrue(data.get("members") or data.get("properties"))
        self.assertIn("error", self.tb.blender_api_help({"path": "bpy.nope.nope"}))
        self.assertIn("error", self.tb.blender_api_help({"path": ""}))

    def test_datablocks_summary_counts_the_scene(self):
        summary = self.tb.datablocks_summary({})
        self.assertGreaterEqual(summary["counts"]["objects"], 1)
        self.assertGreaterEqual(summary["counts"]["meshes"], 1)
        self.assertIn("filepath", summary)

    def test_new_tools_are_registered(self):
        names = [s.name for s in self.tb.SPECS]
        self.assertIn("blender_api_help", names)
        self.assertIn("datablocks_summary", names)

    def test_execute_python_captures_output_and_result_and_blocks_quit(self):
        out = self.sandbox.run_python("import bpy\nprint('hello')\nresult['count'] = len(bpy.data.objects)")
        self.assertEqual(out["result"]["count"], len(bpy.data.objects))
        self.assertIn("hello", out["stdout"])
        blocked = self.sandbox.run_python("import bpy\nbpy.ops.wm.quit_blender()")
        self.assertIn("blocked", (blocked.get("error") or "").lower())
        self.assertTrue(len(bpy.data.objects) >= 1)

    def test_execute_python_respects_preference(self):
        prefs = submodule("prefs").get_prefs()
        prefs.mcp_allow_python = False
        try:
            with self.assertRaises(PermissionError):
                self.tb.execute_python({"code": "result['x'] = 1"})
        finally:
            prefs.mcp_allow_python = True

    def test_select_and_set_frame(self):
        self.tb.select_objects({"names": ["Crate"]})
        self.assertTrue(bpy.data.objects["Crate"].select_get())
        self.tb.set_frame({"frame": 42})
        self.assertEqual(bpy.context.scene.frame_current, 42)

    def test_list_models_and_schema_use_loaded_catalog(self):
        runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        rec = catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"])
        handlers.dispatch(("catalog", {"privacy": "public", "records": [rec], "detailed": [rec]}))
        listed = self.ts.list_models({"lane": "material"})
        self.assertEqual(listed["models"][0]["id"], "model_patina-material")
        schema = self.ts.model_schema({"model_id": "model_patina-material"})
        self.assertIn("maps", [p["name"] for p in schema["parameters"]])
        self.assertTrue(any(s.name == "generate" for s in self.ts.SPECS))
        self.assertTrue(any(s.name == "scene_summary" for s in self.tb.SPECS))
