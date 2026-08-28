# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import reset_scene, submodule


class BreakerTests(unittest.TestCase):
    def test_trips_after_consecutive_failures_and_on_stall(self):
        breaker_mod = submodule("blender.composer.breaker")
        trips = []
        clock = {"t": 0.0}
        b = breaker_mod.Breaker("t", failures=3, stall=2.0, on_trip=trips.append, clock=lambda: clock["t"])

        def boom():
            raise RuntimeError("x")

        for _ in range(3):
            b.guard(boom)
        self.assertTrue(b.tripped)
        self.assertEqual(len(trips), 1)
        b.reset()
        self.assertEqual(b.guard(lambda: 1), 1)  # first call is exempt from the stall rule

        def slow():
            clock["t"] += 2.5
            return "ok"

        b.guard(slow)
        self.assertTrue(b.tripped and "took" in b.reason)


class ComposerStateTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.state_mod = submodule("blender.composer.state")
        self.runtime = submodule("blender.runtime")

    def test_state_mirrors_prompt_both_ways(self):
        scene = bpy.context.scene
        scene.scenario.lane = "image"
        scene.scenario.lane_state("image").prompt = "from panel"
        state = self.state_mod.ComposerState()
        state.sync_from_lane(scene)
        self.assertEqual(state.field.text, "from panel")
        state.field.insert(" and composer")
        state.commit_to_lane(scene)
        self.assertEqual(scene.scenario.lane_state("image").prompt, "from panel and composer")
        scene.scenario.lane = "material"
        scene.scenario.lane_state("material").prompt = "copper"
        state.sync_from_lane(scene)
        self.assertEqual(state.field.text, "copper")

    def test_composer_registered_with_state_and_operator(self):
        self.assertIsNotNone(self.runtime.state.composer)
        self.assertTrue(hasattr(bpy.types, "SCENARIO_OT_composer_modal"))
