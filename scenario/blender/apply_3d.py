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


JOB_TAG = "scenario_job"


def tag_objects(objects, local_id):
    """Stamp the objects with the job that created them, so Select and Delete find them after renames."""
    for obj in objects:
        try:
            obj[JOB_TAG] = local_id
        except (TypeError, AttributeError):
            pass


def objects_of_job(local_id):
    return [o for o in bpy.data.objects if o.get(JOB_TAG) == local_id]


def import_model(context, path, at_cursor=True, collection_name="Scenario", local_id=""):
    kind = placement.importer_for(path)
    before = set(bpy.data.objects.keys())
    _run_importer(kind, path)
    new_objects = [o for o in bpy.data.objects if o.name not in before]
    if local_id:
        tag_objects(new_objects, local_id)
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


def place_next_to(context, objects, source):
    """Move `objects` so they sit to the right (+X) of `source`, bottoms aligned: an edited mesh lands beside its original."""
    src_box = _world_bbox([source] + [c for c in source.children_recursive if c.type == 'MESH'])
    new_box = _world_bbox(objects)
    if src_box is None or new_box is None:
        return
    gap = max(0.1, 0.15 * (src_box[1][0] - src_box[0][0]))
    dx = src_box[1][0] + gap - new_box[0][0]
    dy = src_box[0][1] - new_box[0][1]
    dz = src_box[0][2] - new_box[0][2]
    roots = [o for o in objects if o.parent is None or o.parent not in objects]
    for root in roots:
        root.location = (root.location.x + dx, root.location.y + dy, root.location.z + dz)
    context.view_layer.update()


def on_3d_result(rec):
    """Import ONE mesh per job. Providers ship variants of the same result (Meshy: GLB + OBJ + texture PNGs;
    Rodin with material=All: a shaded GLB and a PBR GLB); importing them all stacked an untextured copy on top of
    the textured one. The best variant (glTF, most PBR textures) is imported, the others stay on disk and are
    offered as alternates in Generations. Edit 3D results are placed next to the mesh they came from."""
    primary, alternates = placement.pick_primary_mesh(rec.files)
    rec.meta["primary_mesh"] = primary or ""
    rec.meta["mesh_alternates"] = alternates
    if primary is None:
        runtime.set_message("The job returned no importable mesh (GLB, FBX or OBJ)")
        return []
    prompt = (rec.meta.get("prompt") or "").strip()
    source = bpy.data.objects.get(rec.meta.get("source_object") or "")
    objects = import_model(bpy.context, primary, at_cursor=source is None, local_id=rec.local_id)
    if source is not None:
        place_next_to(bpy.context, objects, source)
    meshes = [o for o in objects if o.type == 'MESH']
    if source is not None and meshes:
        label = (rec.meta.get("model_name") or "edit").split(" - ")[-1][:24]
        for mesh in meshes:
            mesh.name = f"{source.name} {label}"
    elif prompt and len(meshes) == 1:
        meshes[0].name = f"Scenario {prompt[:40]}"
    rec.meta["objects"] = [o.name for o in objects]
    textured = sum(1 for o in meshes for s in o.material_slots if s.material and any(n.type == 'TEX_IMAGE' and n.image for n in s.material.node_tree.nodes))
    _material_preview()
    extra = f", {len(alternates)} other mesh file(s) kept on disk" if alternates else ""
    where = f"next to {source.name}" if source is not None else "at the 3D cursor"
    runtime.set_message(f"Imported {len(meshes)} mesh(es) {where} ({'textured' if textured else 'no textures'}){extra}")
    return objects
