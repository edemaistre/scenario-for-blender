# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt tools: Spark / Rewrite / Translate operators run off-thread and write the prompt back through an event."""
import importlib
import importlib.util
import queue
import sys
import unittest

import bpy

from helpers import ROOT, addon_name, reset_scene, submodule


def load_module(dotted, rel_file):
    """Import a module of the installed extension; when the installed build predates the file, load it from the repo
    under the installed package name so its relative imports resolve against the running add-on."""
    name = f"{addon_name()}.{dotted}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scenario" / rel_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module


def prompt_tools_module():
    load_module("core.api.llm", "core/api/llm.py")
    module = load_module("blender.prompt_tools", "blender/prompt_tools.py")
    if not hasattr(bpy.types, "SCENARIO_OT_prompt_spark"):
        module.register()
    return module


class StubManager:
    """Runs workers synchronously and keeps the events queue the pump would drain."""

    def __init__(self):
        self.events = queue.Queue()
        self.paths = None

    def _spawn(self, target, *args):
        target(*args)
        return None

    def drain(self):
        out = []
        while not self.events.empty():
            out.append(self.events.get_nowait())
        return out


class FakeClient:
    def __init__(self, spark_prompts=("A brass teapot robot, studio light",)):
        self.posts = []
        self.gets = []
        self.spark_prompts = list(spark_prompts)

    def post(self, path, json_body=None, query=None, **kw):
        self.posts.append((path, json_body, query))
        if path == "/generate/prompt":
            return {"prompts": self.spark_prompts, "mode": "structured"}
        if path.startswith("/generate/custom/model_scenario-llm"):
            return {"job": {"jobId": "job_llm", "status": "success", "metadata": {"assetIds": ["asset_txt"]}}}
        raise AssertionError(f"unexpected POST {path}")

    def get(self, path, query=None, **kw):
        self.gets.append(path)
        if path == "/assets/asset_txt":
            return {"asset": {"id": "asset_txt", "metadata": {"type": "text", "preview": "a copper teapot"}}}
        if path.startswith("/assets/asset_bogus"):
            errors = submodule("core.api.errors")
            raise errors.ScenarioError(404, f"Asset {path.rsplit('/', 1)[-1]} not found")
        raise AssertionError(f"unexpected GET {path}")


class PromptToolsTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.tools = prompt_tools_module()
        self.runtime = submodule("blender.runtime")
        self.runtime.state.reset()
        self.manager = StubManager()
        self.runtime.state.manager = self.manager
        self.client = FakeClient()
        self._make_client = self.runtime.make_client
        self.runtime.make_client = lambda: self.client
        self.prefs = bpy.context.preferences.addons[addon_name()].preferences
        self.prefs.api_key, self.prefs.api_secret = "k", "s"
        # _network_poll needs Allow Online Access; a fresh headless user dir starts with it off
        self.system = bpy.context.preferences.system
        self._online = self.system.use_online_access
        self.system.use_online_access = True
        self.scene = bpy.context.scene
        self.lane = self.scene.scenario.lane_state("image")

    def tearDown(self):
        self.runtime.make_client = self._make_client
        self.runtime.state.manager = None
        self.prefs.api_key, self.prefs.api_secret = "", ""
        self.system.use_online_access = self._online

    def _dispatch_prompt_events(self):
        events = self.manager.drain()
        for name, payload in events:
            if name == "prompt":
                self.tools.on_prompt_event(payload)
        return events

    def test_spark_generate_writes_the_prompt_with_the_lane_model_as_context(self):
        self.lane.prompt = "a teapot robot"
        result = bpy.ops.scenario.prompt_spark(lane="image", mode='GENERATE')
        self.assertEqual(result, {'FINISHED'})
        path, body, _query = self.client.posts[0]
        self.assertEqual(path, "/generate/prompt")
        self.assertEqual(body["prompt"], "a teapot robot")
        self.assertEqual(body["numResults"], 1)
        self.assertEqual(body.get("modelId"), self.lane.model_id if self.lane.model_id != "NONE" else None)
        events = self._dispatch_prompt_events()
        self.assertEqual([n for n, _ in events], ["prompt"])
        self.assertEqual(self.lane.prompt, "A brass teapot robot, studio light")
        self.assertIn("Prompt written", self.runtime.state.last_message)

    def test_spark_generate_without_text_sends_no_intent(self):
        self.lane.prompt = ""
        bpy.ops.scenario.prompt_spark(lane="image", mode='GENERATE')
        _path, body, _query = self.client.posts[0]
        self.assertNotIn("prompt", body)
        self._dispatch_prompt_events()
        self.assertEqual(self.lane.prompt, "A brass teapot robot, studio light")

    def test_rewrite_needs_a_prompt(self):
        self.lane.prompt = ""
        self.assertEqual(bpy.ops.scenario.prompt_spark(lane="image", mode='REWRITE'), {'CANCELLED'})
        self.assertEqual(self.client.posts, [])
        self.lane.prompt = "robot"
        self.assertEqual(bpy.ops.scenario.prompt_spark(lane="image", mode='REWRITE'), {'FINISHED'})
        self._dispatch_prompt_events()
        self.assertEqual(self.lane.prompt, "A brass teapot robot, studio light")
        self.assertIn("rewritten", self.runtime.state.last_message)

    def test_translate_uses_the_scenario_llm_and_writes_the_translation(self):
        self.lane.prompt = "une théière en cuivre"
        self.assertEqual(bpy.ops.scenario.prompt_translate(lane="image"), {'FINISHED'})
        path, body, query = self.client.posts[0]
        self.assertEqual(path, "/generate/custom/model_scenario-llm")
        self.assertEqual(body["textInputs"], ["une théière en cuivre"])
        self.assertIsNone(query)
        self._dispatch_prompt_events()
        self.assertEqual(self.lane.prompt, "a copper teapot")
        self.assertIn("translated", self.runtime.state.last_message)

    def test_translate_needs_a_prompt_and_events_reach_every_scene(self):
        self.lane.prompt = ""
        self.assertEqual(bpy.ops.scenario.prompt_translate(lane="image"), {'CANCELLED'})
        other = bpy.data.scenes.new("Other")
        self.tools.on_prompt_event({"lane": "image", "text": "shared text", "mode": 'GENERATE'})
        self.assertEqual(self.lane.prompt, "shared text")
        self.assertEqual(other.scenario.lane_state("image").prompt, "shared text")
        self.tools.on_prompt_event({"lane": "image", "text": "", "mode": 'GENERATE'})  # empty results never wipe a prompt
        self.assertEqual(self.lane.prompt, "shared text")

    def test_api_failure_becomes_an_error_event_not_an_exception(self):
        def failing_post(path, json_body=None, query=None, **kw):
            errors = submodule("core.api.errors")
            raise errors.ScenarioError(402, "Not enough credits")

        self.client.post = failing_post
        self.lane.prompt = "robot"
        self.assertEqual(bpy.ops.scenario.prompt_spark(lane="image", mode='REWRITE'), {'FINISHED'})
        events = self._dispatch_prompt_events()
        self.assertEqual(events[0][0], "error")
        self.assertIn("Not enough credits", events[0][1])
        self.assertEqual(self.lane.prompt, "robot")

    def test_poll_follows_the_network_rules(self):
        self.assertTrue(bpy.ops.scenario.prompt_spark.poll())
        self.prefs.api_key = ""
        self.assertFalse(bpy.ops.scenario.prompt_spark.poll())
        self.assertFalse(bpy.ops.scenario.prompt_translate.poll())

    def test_descriptions_match_the_web_app_and_state_the_cost(self):
        cls = bpy.types.SCENARIO_OT_prompt_spark if hasattr(bpy.types, "SCENARIO_OT_prompt_spark") else None
        self.assertIsNotNone(cls)
        self.assertEqual(self.tools.MODE_ITEMS[0][2], "Generate a new prompt. Prompt Spark, up to 3.75 CU")
        self.assertEqual(self.tools.MODE_ITEMS[1][2], "Rewrite your prompt. Prompt Spark, up to 3.75 CU")
        self.assertEqual(self.tools.SCENARIO_OT_prompt_translate.bl_description, "Translate to English. Scenario LLM, 0.5 CU")
        for op_cls in self.tools.CLASSES:
            self.assertTrue(op_cls.bl_description, op_cls.bl_idname)
        self.assertTrue(callable(self.tools.draw_prompt_row))

    def test_spark_asset_answer_falls_back_to_the_scenario_llm(self):
        """Live 2026-08-29: Rewrite pasted 'asset_XpjL5Dzw...' into the field. Now the id is resolved or the LLM writes instead."""
        self.client = FakeClient(spark_prompts=["asset_bogus"])
        self.runtime.make_client = lambda: self.client
        self.lane.prompt = "a cute robot, low poly"
        self.assertEqual(bpy.ops.scenario.prompt_spark(lane="image", mode='REWRITE'), {'FINISHED'})
        paths = [p for p, _b, _q in self.client.posts]
        self.assertEqual(paths[0], "/generate/prompt")
        self.assertTrue(paths[1].startswith("/generate/custom/model_scenario-llm"))
        self.assertIn("/assets/asset_bogus", self.client.gets)
        llm_body = self.client.posts[1][1]
        self.assertIn("Rewrite the user's prompt", llm_body["instruction"])
        self.assertEqual(llm_body["textInputs"], ["a cute robot, low poly"])
        events = self._dispatch_prompt_events()
        self.assertEqual(events[0][0], "prompt")
        self.assertEqual(events[0][1]["source"], "llm")
        self.assertEqual(self.lane.prompt, "a copper teapot")
        self.assertIn("Scenario LLM", self.runtime.state.last_message)

    def test_an_asset_id_never_reaches_the_prompt_field(self):
        self.lane.prompt = "keep me"
        self.tools.on_prompt_event({"lane": "image", "text": "asset_XpjL5DzwFNe4V6mbQ9qMUy7t", "mode": 'REWRITE'})
        self.assertEqual(self.lane.prompt, "keep me")
        self.assertEqual(self.tools.usable_text(" asset_abc "), "")
        self.assertEqual(self.tools.usable_text("  two words "), "two words")

    def test_fallback_instruction_mentions_the_model(self):
        text = self.tools.fallback_instruction('GENERATE', "Meshy 7 - Text-to-3D", " (textured meshes)", "a robot")
        self.assertIn("Meshy 7 - Text-to-3D", text)
        self.assertIn("(textured meshes)", text)
        self.assertIn("The user's idea: a robot.", text)
        self.assertTrue(self.tools.fallback_instruction('REWRITE', "Gemini 3.1", "", None).startswith("Rewrite the user's prompt"))
