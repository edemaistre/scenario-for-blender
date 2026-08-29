# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import reset_scene, submodule


class BlockoutTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.blockout = submodule("blender.blockout")

    def test_build_blockout_places_named_boxes_in_a_collection(self):
        boxes = [
            {"name": "Well", "position": [0.0, 0.0, 0.5], "size": [1.0, 1.0, 1.0]},
            {"name": "Gate", "position": [4.0, 0.0, 2.0], "size": [3.0, 0.4, 4.0]},
        ]
        created = self.blockout.build_blockout(bpy.context, boxes)
        self.assertEqual([o.name for o in created], ["Well", "Gate"])
        self.assertIn(self.blockout.COLLECTION, bpy.data.collections)
        coll = bpy.data.collections[self.blockout.COLLECTION]
        self.assertEqual(sorted(o.name for o in coll.objects), ["Gate", "Well"])
        gate = bpy.data.objects["Gate"]
        self.assertEqual(tuple(round(s, 3) for s in gate.scale), (3.0, 0.4, 4.0))  # unit cube -> scale is the metre size
        self.assertEqual(tuple(round(l, 3) for l in gate.location), (4.0, 0.0, 2.0))
        self.assertTrue(gate.get(self.blockout.MARK))
        self.assertTrue(all(o.type == 'MESH' for o in created))

    def test_on_blockout_event_builds_and_reports(self):
        runtime = submodule("blender.runtime")
        self.blockout.on_blockout_event({"boxes": [{"name": "Stall", "position": [0, 0, 0.5], "size": [2, 2, 1]}]})
        self.assertIn("Stall", bpy.data.objects)
        self.assertIn("Blockout", runtime.state.last_message)
