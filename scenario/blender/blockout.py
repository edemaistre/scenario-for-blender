# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blockout from prompt: the Scenario LLM turns a scene description into grey boxes placed in the viewport, a rough
greybox a level designer refines by hand or replaces with generated 3D assets one box at a time."""
import bpy
from bpy.props import StringProperty

from . import runtime
from ..core.api.errors import ScenarioError
from ..core.scene import blockout as core

COLLECTION = "Blockout"
MARK = "scenario_blockout"
_CUBE_MESH = "Scenario Blockout Cube"


def _unit_cube_mesh():
    """A shared 1 m cube; each box is one object linked to it with its own location and scale (no ops, pump-safe)."""
    mesh = bpy.data.meshes.get(_CUBE_MESH)
    if mesh is None:
        mesh = bpy.data.meshes.new(_CUBE_MESH)
        verts = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
                 (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
        faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
    return mesh


def build_blockout(context, boxes):
    """Create one grey box object per entry in a fresh 'Blockout' collection. Returns the created objects."""
    scene = context.scene
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
        scene.collection.children.link(coll)
    mesh = _unit_cube_mesh()
    created = []
    for box in boxes:
        obj = bpy.data.objects.new(box["name"], mesh)
        obj.location = box["position"]
        obj.scale = box["size"]  # the mesh is a unit cube, so scale is the box's metre size
        obj[MARK] = True
        obj.display_type = 'SOLID'
        coll.objects.link(obj)
        created.append(obj)
    return created


def on_blockout_event(payload):
    """Place the boxes on the main thread (called by the pump)."""
    boxes = payload.get("boxes") or []
    created = build_blockout(bpy.context, boxes)
    runtime.set_message(f"Blockout: {len(created)} box(es) placed in the '{COLLECTION}' collection")


class SCENARIO_OT_blockout(bpy.types.Operator):
    bl_idname = "scenario.blockout"
    bl_label = "Blockout from prompt"
    bl_description = "Lay out a rough greybox of the scene as grey boxes from a text description (Scenario LLM, about 0.5 CU)"
    description: StringProperty(name="Scene", description="Describe the scene to block out, e.g. 'a small market square: a well, a gate, four stalls'")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=440, title="Blockout from prompt", confirm_text="Block out")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "description", text="")
        layout.label(text="Grey boxes land in a 'Blockout' collection. About 0.5 CU.", icon='INFO')

    def execute(self, context):
        desc = self.description.strip()
        if not desc:
            self.report({'WARNING'}, "Describe the scene to block out first")
            return {'CANCELLED'}
        from ..core.api import llm
        try:
            client = runtime.make_client()  # reads bpy here, never on the worker
            manager = runtime.ensure_manager()
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        instruction = core.INSTRUCTION + desc

        def worker(manager, client):
            try:
                boxes = core.parse_blockout(llm.run_text(client, instruction))
            except (ScenarioError, ValueError) as err:
                manager.events.put(("error", f"Blockout failed: {getattr(err, 'reason', err)}"))
                return
            if not boxes:
                manager.events.put(("error", "The blockout came back empty; try a more concrete description"))
                return
            manager.events.put(("blockout", {"boxes": boxes}))

        runtime.set_message("Blocking out the scene...")
        manager._spawn(worker, manager, client)
        return {'FINISHED'}


CLASSES = (SCENARIO_OT_blockout,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
