# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: connection test, catalog refresh, generate, references, results."""
import os

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty

from . import apply_image, generation, params_ui, props, runtime
from ..core.api.errors import ScenarioError


class SCENARIO_OT_test_connection(bpy.types.Operator):
    bl_idname = "scenario.test_connection"
    bl_label = "Test Scenario connection"
    bl_description = "Check the API key against Scenario and show the team and project it belongs to"

    def execute(self, context):
        if not runtime.online():
            self.report({'ERROR'}, "Allow Online Access is disabled in Blender's preferences")
            return {'CANCELLED'}
        try:
            data = runtime.make_client().get("/teams", timeout=15)
        except ScenarioError as err:
            runtime.state.account_label = ""
            self.report({'ERROR'}, f"Scenario: {err.reason}")
            return {'CANCELLED'}
        teams = data.get("teams") or []
        if not teams:
            runtime.state.account_label = "Connected (no team visible)"
        else:
            team = teams[0]
            projects = team.get("projects") or []
            project = projects[0]["name"] if projects else "?"
            runtime.state.account_label = f"{team.get('name', 'team')} / {project} ({team.get('plan', '')})"
        runtime.state.catalog_loaded = False
        self.report({'INFO'}, runtime.state.account_label)
        return {'FINISHED'}


class SCENARIO_OT_refresh_catalog(bpy.types.Operator):
    bl_idname = "scenario.refresh_catalog"
    bl_label = "Refresh models"
    bl_description = "Reload the model list from Scenario"

    def execute(self, context):
        runtime.state.catalog_loading = False
        if generation.request_catalog():
            self.report({'INFO'}, "Refreshing models")
            return {'FINISHED'}
        self.report({'WARNING'}, runtime.state.last_message or "Could not refresh (check preferences)")
        return {'CANCELLED'}


class SCENARIO_OT_generate(bpy.types.Operator):
    bl_idname = "scenario.generate"
    bl_label = "Generate"
    bl_description = "Submit this generation to Scenario"
    lane: StringProperty(default="image")

    @classmethod
    def poll(cls, context):
        return runtime.online() and runtime.credentials().valid

    def execute(self, context):
        try:
            rec = generation.submit_generation(context, self.lane)
        except ScenarioError as err:
            context.scene.scenario.lane_state(self.lane).last_error = err.reason
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Generating with {rec.meta.get('model_name', rec.model_id)}")
        return {'FINISHED'}


def _network_poll(cls, context):
    return runtime.online() and runtime.credentials().valid


class SCENARIO_OT_set_lane(bpy.types.Operator):
    bl_idname = "scenario.set_lane"
    bl_label = "Lane"
    bl_options = {'INTERNAL'}
    lane: StringProperty()

    def execute(self, context):
        context.scene.scenario.lane = self.lane
        return {'FINISHED'}


class SCENARIO_OT_add_reference(bpy.types.Operator):
    bl_idname = "scenario.add_reference"
    bl_label = "Add reference"
    bl_description = "Attach a file, the render result or a viewport capture to this parameter"
    lane: StringProperty()
    param_name: StringProperty()
    source: EnumProperty(items=props.ADDABLE_SOURCES, default='FILE')
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.mp4;*.mov;*.webm;*.glb;*.fbx;*.obj", options={'HIDDEN'})

    def invoke(self, context, event):
        if self.source == 'FILE':
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        return self.execute(context)

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        ref = lane_state.references.add()
        ref.param_name, ref.source = self.param_name, self.source
        if self.source == 'FILE':
            ref.filepath = self.filepath
            ref.label = os.path.basename(self.filepath)
        else:
            ref.label = {k: v for k, v, _ in props.REFERENCE_SOURCES}[self.source]
        props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_remove_reference(bpy.types.Operator):
    bl_idname = "scenario.remove_reference"
    bl_label = "Remove reference"
    lane: StringProperty()
    index: IntProperty()

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        if 0 <= self.index < len(lane_state.references):
            lane_state.references.remove(self.index)
            props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_toggle_multi(bpy.types.Operator):
    bl_idname = "scenario.toggle_multi"
    bl_label = "Toggle option"
    lane: StringProperty()
    param_name: StringProperty()
    value: StringProperty()

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        index = lane_state.params.find(self.param_name)
        if index < 0:
            return {'CANCELLED'}
        item = lane_state.params[index]
        selected = params_ui.multi_selection(item)
        if self.value in selected:
            selected.remove(self.value)
        else:
            selected.append(self.value)
        params_ui.set_multi_selection(item, selected)
        props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_open_output_folder(bpy.types.Operator):
    bl_idname = "scenario.open_output_folder"
    bl_label = "Open output folder"

    def execute(self, context):
        path = runtime.paths().output_dir
        path.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.path_open(filepath=str(path))
        return {'FINISHED'}


class SCENARIO_OT_show_image(bpy.types.Operator):
    bl_idname = "scenario.show_image"
    bl_label = "Show image"
    filepath: StringProperty()

    def execute(self, context):
        image = apply_image.load_image(self.filepath)
        apply_image.show_in_image_editor(image)
        return {'FINISHED'}


class SCENARIO_OT_apply_texture(bpy.types.Operator):
    bl_idname = "scenario.apply_texture"
    bl_label = "Apply as texture"
    bl_description = "Create a material with this image as Base Color on the active mesh"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        apply_image.apply_as_texture(context.active_object, apply_image.load_image(self.filepath))
        return {'FINISHED'}


class SCENARIO_OT_add_plane(bpy.types.Operator):
    bl_idname = "scenario.add_plane"
    bl_label = "Add as plane"
    bl_description = "Add a view-facing plane at the 3D cursor with this image (Object Mode)"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        apply_image.add_as_plane(context, apply_image.load_image(self.filepath))
        return {'FINISHED'}


class SCENARIO_OT_expand_prompt(bpy.types.Operator):
    bl_idname = "scenario.expand_prompt"
    bl_label = "Edit prompt"
    lane: StringProperty()
    prompt: StringProperty(name="Prompt")

    def invoke(self, context, event):
        self.prompt = context.scene.scenario.lane_state(self.lane).prompt
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        self.layout.prop(self, "prompt", text="")

    def execute(self, context):
        context.scene.scenario.lane_state(self.lane).prompt = self.prompt
        return {'FINISHED'}


class SCENARIO_OT_retile_material(bpy.types.Operator):
    bl_idname = "scenario.retile_material"
    bl_label = "Set material tiling"
    bl_description = "Scale the UV mapping of a Scenario material"
    bl_options = {'REGISTER', 'UNDO'}
    material_name: StringProperty()
    scale: FloatProperty(name="Tiling", default=1.0, min=0.01, max=100.0)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from . import apply_material

        mat = bpy.data.materials.get(self.material_name)
        if mat is None:
            self.report({'ERROR'}, "Material not found")
            return {'CANCELLED'}
        apply_material.set_tiling(mat, self.scale)
        return {'FINISHED'}


class SCENARIO_OT_history_refresh(bpy.types.Operator):
    bl_idname = "scenario.history_refresh"
    bl_label = "Refresh generations"

    @classmethod
    def poll(cls, context):
        return _network_poll(cls, context)

    def execute(self, context):
        from . import history

        history.refresh()
        return {'FINISHED'}


class SCENARIO_OT_history_older(bpy.types.Operator):
    bl_idname = "scenario.history_older"
    bl_label = "Load older"

    @classmethod
    def poll(cls, context):
        return _network_poll(cls, context)

    def execute(self, context):
        from . import history

        return {'FINISHED'} if history.older() else {'CANCELLED'}


class SCENARIO_OT_import_result(bpy.types.Operator):
    bl_idname = "scenario.import_result"
    bl_label = "Import into scene"
    bl_description = "Download this generation (if needed) and bring it into the scene"
    job_id: StringProperty()
    kind: StringProperty(default="image")
    model_id: StringProperty()
    prompt: StringProperty()

    @classmethod
    def poll(cls, context):
        return _network_poll(cls, context) and context.mode == 'OBJECT'

    def execute(self, context):
        from . import handlers
        from ..core.jobs.records import JobRecord

        manager = runtime.ensure_manager()
        existing = next((r for r in manager.registry.all() if r.job_id == self.job_id and r.files), None)
        if existing is not None:
            existing.meta["target_objects"] = [o.name for o in context.selected_objects if o.type == 'MESH']
            handlers.dispatch(("job_done", existing))
            return {'FINISHED'}
        rec = JobRecord.new(lane=self.kind, kind=self.kind, model_id=self.model_id, body={}, meta={"prompt": self.prompt, "model_name": self.model_id})
        rec.job_id, rec.status = self.job_id, "in-progress"
        rec.meta["target_objects"] = [o.name for o in context.selected_objects if o.type == 'MESH']
        manager.registry.add(rec)
        manager.registry.save()
        try:
            manager.track(rec)
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        runtime.state.jobs_view.insert(0, rec)
        self.report({'INFO'}, "Downloading generation")
        return {'FINISHED'}


class SCENARIO_OT_play_video(bpy.types.Operator):
    bl_idname = "scenario.play_video"
    bl_label = "Play"
    bl_description = "Open the video with the system player"
    filepath: StringProperty()

    def execute(self, context):
        from . import apply_video

        apply_video.play_with_os(self.filepath)
        return {'FINISHED'}


class SCENARIO_OT_play_video_blender(bpy.types.Operator):
    bl_idname = "scenario.play_video_blender"
    bl_label = "Play in Blender"
    bl_description = "Open the video in Blender's animation player"
    filepath: StringProperty()

    def execute(self, context):
        from . import apply_video

        apply_video.play_with_blender(self.filepath)
        return {'FINISHED'}


class SCENARIO_OT_render_concept(bpy.types.Operator):
    bl_idname = "scenario.render_concept"
    bl_label = "Render concept"
    bl_description = "Capture the view and restyle it with the concept model"

    @classmethod
    def poll(cls, context):
        return runtime.online() and runtime.credentials().valid

    def execute(self, context):
        from . import render_to_real

        try:
            render_to_real.submit_concept(context)
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


class SCENARIO_OT_render_video(bpy.types.Operator):
    bl_idname = "scenario.render_video"
    bl_label = "Playblast and Generate"
    bl_description = "Playblast the timeline and send it with the concept image to Seedance 2.0"

    @classmethod
    def poll(cls, context):
        return runtime.online() and runtime.credentials().valid

    def execute(self, context):
        from . import render_to_real

        try:
            render_to_real.submit_video(context)
        except ScenarioError as err:
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        return {'FINISHED'}


class SCENARIO_OT_mcp_start(bpy.types.Operator):
    bl_idname = "scenario.mcp_start"
    bl_label = "Start MCP server"

    def execute(self, context):
        from . import mcp_service

        server = mcp_service.start()
        if server is None:
            self.report({'ERROR'}, runtime.state.mcp_error or "Could not start")
            return {'CANCELLED'}
        self.report({'INFO'}, f"MCP server on {server.url}")
        return {'FINISHED'}


class SCENARIO_OT_mcp_stop(bpy.types.Operator):
    bl_idname = "scenario.mcp_stop"
    bl_label = "Stop MCP server"

    def execute(self, context):
        from . import mcp_service

        mcp_service.stop()
        return {'FINISHED'}


class SCENARIO_OT_mcp_copy(bpy.types.Operator):
    bl_idname = "scenario.mcp_copy"
    bl_label = "Copy MCP setup"
    bl_description = "Copy the connection setup for this client to the clipboard"
    kind: StringProperty(default="claude_code")

    def execute(self, context):
        from . import mcp_service

        text = mcp_service.client_configs().get(self.kind, "")
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"Copied {self.kind.replace('_', ' ')} setup")
        return {'FINISHED'}


CLASSES = (SCENARIO_OT_set_lane, SCENARIO_OT_mcp_start, SCENARIO_OT_mcp_stop, SCENARIO_OT_mcp_copy, SCENARIO_OT_render_concept, SCENARIO_OT_render_video, SCENARIO_OT_play_video, SCENARIO_OT_play_video_blender, SCENARIO_OT_history_refresh, SCENARIO_OT_history_older, SCENARIO_OT_import_result, SCENARIO_OT_test_connection, SCENARIO_OT_refresh_catalog, SCENARIO_OT_generate, SCENARIO_OT_add_reference,
           SCENARIO_OT_remove_reference, SCENARIO_OT_toggle_multi, SCENARIO_OT_open_output_folder, SCENARIO_OT_show_image,
           SCENARIO_OT_apply_texture, SCENARIO_OT_add_plane, SCENARIO_OT_expand_prompt, SCENARIO_OT_retile_material)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
