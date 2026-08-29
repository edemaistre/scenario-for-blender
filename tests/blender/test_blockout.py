# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import math
import unittest

import bpy

from helpers import reset_scene, submodule


def _el(name, category="other", primitive="box", position=(0, 0, 0.5), size=(1, 1, 1), rotation=0.0, group="Blockout"):
    return {"name": name, "category": category, "primitive": primitive,
            "position": list(position), "size": list(size), "rotation": rotation, "group": group}


class BlockoutTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.blockout = submodule("blender.blockout")
        self.core = submodule("core.scene.blockout")

    def test_build_places_primitives_grouped_and_coloured(self):
        els = [
            _el("Ground", "floor", "plane", (0, 0, -0.05), (12, 12, 0.1), group="Ground"),
            _el("Well", "water", "cylinder", (0, 0, 0.6), (1.6, 1.6, 1.2), rotation=30, group="Center"),
            _el("Roof", "structure", "wedge", (4, 0, 3), (3, 3, 1.5), group="Buildings"),
        ]
        created = self.blockout.build_blockout(bpy.context, els)
        self.assertEqual([o.name for o in created], ["Ground", "Well", "Roof"])
        root = bpy.data.collections[self.blockout.COLLECTION]
        self.assertEqual(sorted(c.name for c in root.children), ["Buildings", "Center", "Ground"])
        well = bpy.data.objects["Well"]
        self.assertGreater(len(well.data.vertices), 8)  # a cylinder, not a cube
        self.assertAlmostEqual(well.rotation_euler.z, math.radians(30), places=4)
        self.assertEqual(well[self.blockout.MARK], "water")
        self.assertEqual(tuple(round(c, 3) for c in well.color), tuple(round(c, 3) for c in self.core.CATEGORIES["water"][1]) + (1.0,))

    def test_rebuild_clears_the_previous_blockout(self):
        self.blockout.build_blockout(bpy.context, [_el("A", group="G")])
        self.blockout.build_blockout(bpy.context, [_el("B", group="G")])
        names = [o.name for o in bpy.data.collections[self.blockout.COLLECTION].children["G"].objects]
        self.assertEqual(names, ["B"])  # A was cleared

    def test_on_blockout_plan_stores_and_builds(self):
        runtime = submodule("blender.runtime")
        els = [_el("Stall", "prop", "box", (2, 0, 0.5), (2, 2, 1), group="Market")]
        self.blockout.on_blockout_plan({"elements": els})
        self.assertIn("Stall", bpy.data.objects)
        self.assertEqual(self.blockout.stored_plan(bpy.context.scene), els)
        self.assertIn("Blockout", runtime.state.last_message)

    def test_clear_removes_collection_and_plan(self):
        scene = bpy.context.scene
        self.blockout.on_blockout_plan({"elements": [_el("X")]})
        self.assertTrue(scene.scenario_blockout.plan_json)
        bpy.ops.scenario.blockout_clear()
        self.assertNotIn(self.blockout.COLLECTION, bpy.data.collections)
        self.assertEqual(scene.scenario_blockout.plan_json, "")

    def test_blockout_is_a_lane_tab_and_can_be_selected(self):
        props = submodule("blender.props")
        self.assertIn("blockout", [k for k, _l, _d in props.LANE_ITEMS])
        bpy.context.scene.scenario.lane = "blockout"  # selectable without error
        self.assertEqual(bpy.context.scene.scenario.lane, "blockout")
