# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt to Blockout: the Scenario LLM designs a structured greybox (rich primitives, categories, groups) that the
builder places in the viewport, colour-coded and organised into sub-collections, to refine or replace with generated
assets. The design runs off the main thread (LLM); the build runs on the main thread from the stored plan."""
import json
from math import radians

import bpy
import bmesh
from bpy.props import EnumProperty, StringProperty

from . import runtime
from ..core.api.errors import ScenarioError
from ..core.scene import blockout as core

COLLECTION = "Blockout"
MARK = "scenario_blockout"
_MESHES = {}


# -- primitive meshes (shared unit shapes in a 1 m cube; per-object scale gives the metre size) -----------------------
def _hand_mesh(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def _bmesh_mesh(name, build):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def _build_box():
    verts = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
             (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _hand_mesh("Scenario Blockout box", verts, faces)


def _build_wedge():
    # a ramp / lean-to roof rising from -x (low) to +x (high)
    verts = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
             (0.5, -0.5, 0.5), (0.5, 0.5, 0.5)]
    faces = [(0, 1, 2, 3), (1, 4, 5, 2), (0, 4, 1), (3, 2, 5), (0, 3, 5, 4)]
    return _hand_mesh("Scenario Blockout wedge", verts, faces)


def _mesh_for(primitive):
    mesh = _MESHES.get(primitive)
    try:
        if mesh is not None and mesh.name in bpy.data.meshes:
            return mesh
    except ReferenceError:
        pass  # the cached mesh was removed (e.g. a fresh file); rebuild it
    if primitive == "wedge":
        mesh = _build_wedge()
    elif primitive == "cylinder":
        mesh = _bmesh_mesh("Scenario Blockout cylinder", lambda bm: bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=24, radius1=0.5, radius2=0.5, depth=1.0))
    elif primitive == "cone":
        mesh = _bmesh_mesh("Scenario Blockout cone", lambda bm: bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=24, radius1=0.5, radius2=0.0, depth=1.0))
    elif primitive == "sphere":
        mesh = _bmesh_mesh("Scenario Blockout sphere", lambda bm: bmesh.ops.create_uvsphere(
            bm, u_segments=20, v_segments=12, radius=0.5))
    else:  # box and plane share the cube (a plane is just a thin box)
        mesh = _build_box()
    _MESHES[primitive] = mesh
    return mesh


# -- collections ------------------------------------------------------------------------------------------------------
def _sub_collection(name, parent):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in {c.name for c in parent.children}:
        parent.children.link(coll)
    return coll


def clear_blockout(scene):
    """Remove the Blockout collection, its sub-collections and their objects. Returns how many objects were removed."""
    root = bpy.data.collections.get(COLLECTION)
    if root is None:
        return 0
    removed = 0
    for coll in list(root.children) + [root]:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    for coll in list(root.children):
        bpy.data.collections.remove(coll)
    bpy.data.collections.remove(root)
    return removed


def _colour_the_viewport():
    """Show the per-object greybox colours: switch every 3D viewport's solid shading to colour by object."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.color_type = 'OBJECT'


def build_blockout(context, elements):
    """Place every element as a coloured primitive, grouped into sub-collections under 'Blockout'. Returns the objects."""
    scene = context.scene
    clear_blockout(scene)
    root = _sub_collection(COLLECTION, scene.collection)
    groups, created = {}, []
    for el in elements:
        group = el.get("group") or COLLECTION
        category = el.get("category") or core.DEFAULT_CATEGORY
        if group == COLLECTION:
            gcoll = root  # ungrouped elements sit directly in the root, never a sub-collection named after it
        else:
            gcoll = groups.get(group)
            if gcoll is None:
                gcoll = _sub_collection(group, root)
                groups[group] = gcoll
        obj = bpy.data.objects.new(el.get("name") or "Block", _mesh_for(el.get("primitive") or "box"))
        obj.location = el.get("position") or (0.0, 0.0, 0.0)
        obj.scale = el.get("size") or (1.0, 1.0, 1.0)
        obj.rotation_euler = (0.0, 0.0, radians(el.get("rotation", 0.0) or 0.0))
        r, g, b = core.CATEGORIES.get(category, core.CATEGORIES[core.DEFAULT_CATEGORY])[1]
        obj.color = (r, g, b, 1.0)
        obj[MARK] = category
        obj.display_type = 'SOLID'
        gcoll.objects.link(obj)
        created.append(obj)
    if created and not bpy.app.background:
        _colour_the_viewport()
    return created


# -- state ------------------------------------------------------------------------------------------------------------
def _store(scene, elements):
    scene.scenario_blockout.plan_json = json.dumps(elements)


def stored_plan(scene):
    try:
        data = json.loads(scene.scenario_blockout.plan_json or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def on_blockout_plan(payload):
    """Store the designed plan and build it (main thread, called by the pump)."""
    elements = payload.get("elements") or []
    scene = bpy.context.scene
    _store(scene, elements)
    created = build_blockout(bpy.context, elements)
    summary = core.plan_summary(elements)
    runtime.set_message(f"Blockout: {len(created)} elements in {len(summary['by_group'])} group(s)")


# -- operators --------------------------------------------------------------------------------------------------------
def _design(context, prompt, previous=None):
    """Resolve the client on the main thread, then design the plan off-thread and build it through an event."""
    from ..core.api import llm

    props = context.scene.scenario_blockout
    client = runtime.make_client()
    manager = runtime.ensure_manager()
    text = core.instruction(prompt, props.scene_type, props.scale, previous=previous)

    def worker(manager, client):
        try:
            elements = core.parse_plan(llm.run_text(client, text))
        except (ScenarioError, ValueError) as err:
            manager.events.put(("error", f"Blockout failed: {getattr(err, 'reason', err)}"))
            return
        if not elements:
            manager.events.put(("error", "The blockout came back empty; try a more concrete description"))
            return
        manager.events.put(("blockout_plan", {"elements": elements}))

    runtime.set_message("Designing the blockout..." if previous is None else "Refining the blockout...")
    manager._spawn(worker, manager, client)


class SCENARIO_OT_blockout_design(bpy.types.Operator):
    bl_idname = "scenario.blockout_design"
    bl_label = "Design blockout"
    bl_description = "Design a greybox of the scene from the description with the Scenario LLM, then place it (about 0.5 CU)"

    def execute(self, context):
        props = context.scene.scenario_blockout
        prompt = props.prompt.strip()
        if not prompt:
            self.report({'WARNING'}, "Describe the scene to block out first")
            return {'CANCELLED'}
        try:
            _design(context, prompt)
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


class SCENARIO_OT_blockout_refine(bpy.types.Operator):
    bl_idname = "scenario.blockout_refine"
    bl_label = "Refine blockout"
    bl_description = "Apply the refinement to the current blockout with the Scenario LLM, then rebuild it (about 0.5 CU)"

    def execute(self, context):
        props = context.scene.scenario_blockout
        change = props.refine.strip()
        previous = stored_plan(context.scene)
        if not change:
            self.report({'WARNING'}, "Describe the change to make")
            return {'CANCELLED'}
        if not previous:
            self.report({'WARNING'}, "Design a blockout first, then refine it")
            return {'CANCELLED'}
        try:
            _design(context, change, previous=previous)
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        props.refine = ""
        return {'FINISHED'}


class SCENARIO_OT_blockout_build(bpy.types.Operator):
    bl_idname = "scenario.blockout_build"
    bl_label = "Rebuild blockout"
    bl_description = "Rebuild the greybox from the current plan without calling the LLM again"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        elements = core.parse_plan(json.dumps(stored_plan(context.scene)))
        if not elements:
            self.report({'WARNING'}, "No blockout plan yet; design one first")
            return {'CANCELLED'}
        created = build_blockout(context, elements)
        self.report({'INFO'}, f"Rebuilt {len(created)} elements")
        return {'FINISHED'}


class SCENARIO_OT_blockout_clear(bpy.types.Operator):
    bl_idname = "scenario.blockout_clear"
    bl_label = "Clear blockout"
    bl_description = "Delete the Blockout collection and forget the plan"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed = clear_blockout(context.scene)
        context.scene.scenario_blockout.plan_json = ""
        self.report({'INFO'}, f"Cleared {removed} object(s)")
        return {'FINISHED'}


CLASSES = (SCENARIO_OT_blockout_design, SCENARIO_OT_blockout_refine, SCENARIO_OT_blockout_build, SCENARIO_OT_blockout_clear)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
