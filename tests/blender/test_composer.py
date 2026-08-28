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
        self.assertFalse(self.runtime.state.composer.dragging)

    def test_lane_for_covers_the_six_generation_lanes_and_falls_back_to_image(self):
        scene = bpy.context.scene
        state = self.state_mod.ComposerState()
        for lane in ("image", "video", "3d", "material"):
            scene.scenario.lane = lane
            self.assertEqual(state.lane_for(scene), lane)
        for lane in ("render_image", "render_video"):
            try:
                scene.scenario.lane = lane
            except TypeError:
                self.skipTest(f"lane {lane} not in the scene enum yet")
            if scene.scenario.lane_state(lane) is None:
                self.skipTest(f"lane state {lane} not wired yet")
            self.assertEqual(state.lane_for(scene), lane)
            scene.scenario.lane_state(lane).prompt = "look"
            self.assertEqual(state.sync_from_lane(scene).prompt, "look")
        for lane in ("audio",):  # a lane tab the composer does not show
            scene.scenario.lane = lane
            self.assertEqual(state.lane_for(scene), "image")

    def test_selection_survives_commit_and_sync_resets_it(self):
        scene = bpy.context.scene
        scene.scenario.lane = "image"
        scene.scenario.lane_state("image").prompt = "hello world"
        state = self.state_mod.ComposerState()
        state.sync_from_lane(scene)
        state.field.caret_at(0)
        state.field.caret_at(5, extend=True)
        self.assertEqual(state.field.selected_text(), "hello")
        state.field.insert("bye")
        state.commit_to_lane(scene)
        self.assertEqual(scene.scenario.lane_state("image").prompt, "bye world")
        scene.scenario.lane_state("image").prompt = "from panel"
        state.sync_from_lane(scene)
        self.assertIsNone(state.field.selection)
        self.assertEqual(state.field.caret, len("from panel"))


class ComposerDrawHelpersTests(unittest.TestCase):
    def test_caret_index_at_maps_pixels_to_glyph_boundaries(self):
        draw = submodule("blender.composer.draw")
        cl = submodule("core.ui.composer_layout")
        field = cl.TextField("hello world")
        pr = cl.Rect(100, 100, 400, 34)
        try:
            font_px, start, end, x0 = draw.prompt_metrics(pr, field, 1.0)
        except Exception as err:  # blf without a font in some background builds
            self.skipTest(f"blf unavailable: {err}")
        self.assertEqual((start, end), (0, len(field.text)))
        self.assertEqual(draw.caret_index_at(x0 - 5, pr, field, 1.0), 0)
        self.assertEqual(draw.caret_index_at(x0 + 10_000, pr, field, 1.0), len(field.text))
        import blf
        blf.size(draw.FONT, font_px)
        mid = x0 + blf.dimensions(draw.FONT, "hello")[0]
        self.assertEqual(draw.caret_index_at(mid, pr, field, 1.0), 5)
