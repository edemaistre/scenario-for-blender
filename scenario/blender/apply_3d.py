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


def _material_preview():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D' and area.spaces.active.shading.type == 'SOLID':
                area.spaces.active.shading.type = 'MATERIAL'


def on_3d_result(rec):
    """Import ONE mesh per job. Providers ship variants of the same result (Meshy: GLB + OBJ + texture PNGs;
    Rodin with material=All: a shaded GLB and a PBR GLB); importing them all stacked an untextured copy on top of
    the textured one. The best variant (glTF, most PBR textures) is imported, the others stay on disk and are
    offered as alternates in Results."""
    primary, alternates = placement.pick_primary_mesh(rec.files)
    rec.meta["primary_mesh"] = primary or ""
    rec.meta["mesh_alternates"] = alternates
    if primary is None:
        runtime.set_message("The job returned no importable mesh (GLB, FBX or OBJ)")
        return []
    prompt = (rec.meta.get("prompt") or "").strip()
    objects = import_model(bpy.context, primary, at_cursor=True)
    meshes = [o for o in objects if o.type == 'MESH']
    if prompt and len(meshes) == 1:
        meshes[0].name = f"Scenario {prompt[:40]}"
    textured = sum(1 for o in meshes for s in o.material_slots if s.material and any(n.type == 'TEX_IMAGE' and n.image for n in s.material.node_tree.nodes))
    _material_preview()
    extra = f", {len(alternates)} other mesh file(s) kept on disk" if alternates else ""
    runtime.set_message(f"Imported {len(meshes)} mesh(es) at the 3D cursor ({'textured' if textured else 'no textures'}){extra}")
    return objects
