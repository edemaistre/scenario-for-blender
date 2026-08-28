# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import placement


def test_bottom_center_offset_moves_bbox_bottom_to_target():
    dx, dy, dz = placement.bottom_center_offset((-1, -2, 0.5), (3, 2, 4.5), (10, 20, 30))
    assert (dx, dy, dz) == (9.0, 20.0, 29.5)


def test_importer_for_extension():
    assert placement.importer_for("a.glb") == "gltf" and placement.importer_for("b.GLTF") == "gltf"
    assert placement.importer_for("c.fbx") == "fbx" and placement.importer_for("d.obj") == "obj"
    assert placement.importer_for("e.vox") is None
