# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement math and importer selection for 3D results. No bpy."""
import pathlib

_IMPORTERS = {".glb": "gltf", ".gltf": "gltf", ".fbx": "fbx", ".obj": "obj"}


def importer_for(path):
    return _IMPORTERS.get(pathlib.Path(str(path)).suffix.lower())


def bottom_center_offset(bbox_min, bbox_max, target):
    cx = (bbox_min[0] + bbox_max[0]) / 2.0
    cy = (bbox_min[1] + bbox_max[1]) / 2.0
    return (float(target[0] - cx), float(target[1] - cy), float(target[2] - bbox_min[2]))
