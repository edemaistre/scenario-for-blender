# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import GLB/FBX/OBJ results, place them at the 3D cursor inside a 'Scenario' collection."""
import logging

import bpy
from mathutils import Vector

from . import runtime
from ..core.scene import placement

log = logging.getLogger("scenario.3d")


def ensure_collection(scene, name="Scenario"):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def _run_importer(kind, path):
    if kind == "gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif kind == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif kind == "obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise RuntimeError(f"no importer for {path}")


def _world_bbox(objects):
    points = []
    for obj in objects:
        if obj.type != 'MESH':
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return None
    return (tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3)))


def import_model(context, path, at_cursor=True, collection_name="Scenario"):
    kind = placement.importer_for(path)
    before = set(bpy.data.objects.keys())
    _run_importer(kind, path)
    new_objects = [o for o in bpy.data.objects if o.name not in before]
    scene = context.scene
    coll = ensure_collection(scene, collection_name)
    for obj in new_objects:
        for other in list(obj.users_collection):
            if other != coll:
                other.objects.unlink(obj)
        if obj.name not in coll.objects:
            coll.objects.link(obj)
    context.view_layer.update()
    roots = [o for o in new_objects if o.parent is None or o.parent not in new_objects]
    if at_cursor and roots:
        bbox = _world_bbox(new_objects)
        if bbox is not None:
            dx, dy, dz = placement.bottom_center_offset(bbox[0], bbox[1], tuple(scene.cursor.location))
            for root in roots:
                root.location = (root.location.x + dx, root.location.y + dy, root.location.z + dz)
        context.view_layer.update()
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in new_objects:
        obj.select_set(True)
    if roots:
        context.view_layer.objects.active = roots[0]
    return new_objects


def on_3d_result(rec):
    imported = []
    prompt = (rec.meta.get("prompt") or "").strip()
    for path in rec.files:
        if placement.importer_for(path) is None:
            log.info("skipping non-mesh result %s", path)
            continue
        objects = import_model(bpy.context, path, at_cursor=True)
        meshes = [o for o in objects if o.type == 'MESH']
        if prompt and len(meshes) == 1:
            meshes[0].name = f"Scenario {prompt[:40]}"
        imported.extend(objects)
    runtime.set_message(f"Imported {len(imported)} object(s) at the 3D cursor")
    return imported
