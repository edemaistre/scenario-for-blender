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
        return _network_poll(cls, context)

    def execute(self, context):
        lane = self.lane
        if lane == "3d" and context.scene.scenario.three_d_mode == 'EDIT':
            lane = "edit3d"  # the 3D tab in Edit mode drives the edit3d lane
        try:
            rec = generation.submit_generation(context, lane)
        except ScenarioError as err:
            context.scene.scenario.lane_state(lane).last_error = err.reason
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Generating with {rec.meta.get('model_name', rec.model_id)}")
        return {'FINISHED'}


def probe_mode():
    """Automated GUI checks set SCENARIO_GUI_PROBE=1 so a stray Enter or click cannot spend credits."""
    return os.environ.get("SCENARIO_GUI_PROBE") == "1"


def _network_poll(cls, context):
    return runtime.online() and runtime.credentials().valid and not probe_mode()


class SCENARIO_OT_set_lane(bpy.types.Operator):
    bl_idname = "scenario.set_lane"
    bl_label = "Lane"
    bl_description = "Switch the Scenario tab to this lane"
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
    bl_description = "Remove this reference from the form"
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
    bl_description = "Toggle this option in the list parameter"
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
    bl_description = "Open the folder where generations are saved"

    def execute(self, context):
        path = runtime.paths().output_dir
        path.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.path_open(filepath=str(path))
        return {'FINISHED'}


class SCENARIO_OT_show_image(bpy.types.Operator):
    bl_idname = "scenario.show_image"
    bl_label = "Show image"
    bl_description = "Open this image in an Image Editor"
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
    bl_description = "Edit the prompt in a wider field"
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
    bl_description = "Reload the project's generations from Scenario"

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
    bl_description = "Load the previous page of the project's generations"

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


class SCENARIO_OT_use_first_frame(bpy.types.Operator):
    bl_idname = "scenario.use_first_frame"
    bl_label = "Use as video first frame"
    bl_description = "Start the Render Video clip from this image: it becomes the first frame reference"
    filepath: StringProperty()

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state("render_video")
        lane_state.first_frame_path = self.filepath
        lane_state.use_first_frame = True
        props.mark_estimate_dirty(lane_state)
        self.report({'INFO'}, "First frame set for Render Video")
        return {'FINISHED'}


class SCENARIO_OT_clear_first_frame(bpy.types.Operator):
    bl_idname = "scenario.clear_first_frame"
    bl_label = "Clear first frame"
    bl_description = "Forget the first frame; the clip starts from the playblast alone"

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state("render_video")
        lane_state.first_frame_path = ""
        props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_copy_text(bpy.types.Operator):
    bl_idname = "scenario.copy_text"
    bl_label = "Copy"
    bl_description = "Copy to the clipboard"
    text: StringProperty()
    what: StringProperty(default="text")

    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({'INFO'}, f"Copied {self.what}")
        return {'FINISHED'}


class SCENARIO_OT_toggle_result(bpy.types.Operator):
    bl_idname = "scenario.toggle_result"
    bl_label = "Collapse or expand"
    bl_description = "Collapse or expand this generation"
    bl_options = {'INTERNAL'}
    local_id: StringProperty()

    def execute(self, context):
        for rec in runtime.state.jobs_view:
            if rec.local_id == self.local_id:
                rec.meta["collapsed"] = not rec.meta.get("collapsed", False)
                break
        return {'FINISHED'}


class SCENARIO_OT_result_details(bpy.types.Operator):
    bl_idname = "scenario.result_details"
    bl_label = "Generation details"
    bl_description = "Everything about this generation: model, prompt, settings, references, asset ids, files"
    local_id: StringProperty()

    def _rec(self):
        return next((r for r in runtime.state.jobs_view if r.local_id == self.local_id), None)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=620)

    def draw(self, context):
        import json

        rec = self._rec()
        layout = self.layout
        if rec is None:
            layout.label(text="This generation is no longer in the session list", icon='ERROR')
            return
        from . import panels

        header = layout.box()
        row = header.row(align=True)
        row.label(text=panels._short_prompt(rec, 60), icon=panels.KIND_ICON.get(rec.kind, 'FILE'))
        row.label(text=f"{rec.cu_cost:g} CU" if rec.cu_cost is not None else rec.status)
        row = header.row(align=True)
        row.label(text=rec.meta.get('model_name') or rec.model_id, icon='NODE_MATERIAL')
        row.label(text=rec.status, icon='CHECKMARK' if rec.is_success else 'ERROR')
        if rec.meta.get("prompt"):
            op = row.operator("scenario.copy_text", text="", icon='COPYDOWN')
            op.text, op.what = rec.meta["prompt"], "prompt"
        col = layout.column(align=True)
        col.label(text=f"Model id: {rec.model_id}")
        if rec.job_id:
            row = col.row(align=True)
            row.label(text=f"Job: {rec.job_id}")
            op = row.operator("scenario.copy_text", text="", icon='COPYDOWN')
            op.text, op.what = rec.job_id, "job id"
        for key, label in (("prompt", "Prompt"), ("spark_look", "Prompt Spark look"), ("look", "Look")):
            value = rec.meta.get(key)
            if value:
                box = layout.box()
                box.label(text=label, icon='TEXT')
                for line in _wrap(str(value), 88):
                    box.label(text=line)
        settings = {k: v for k, v in rec.body.items() if not (isinstance(v, str) and v.startswith("asset_")) and not (isinstance(v, list) and v and str(v[0]).startswith("asset_"))}
        prompt_keys = {"prompt", "textStylePrompt", "instruction"}
        settings = {k: v for k, v in settings.items() if k not in prompt_keys}
        if settings:
            box = layout.box()
            box.label(text="Settings sent", icon='PREFERENCES')
            for key, value in settings.items():
                box.label(text=f"{key}: {json.dumps(value) if not isinstance(value, str) else value}"[:96])
        refs = {k: v for k, v in rec.body.items() if (isinstance(v, str) and v.startswith("asset_")) or (isinstance(v, list) and v and str(v[0]).startswith("asset_"))}
        inputs = rec.meta.get("inputs") or []
        if refs or inputs:
            box = layout.box()
            box.label(text="References", icon='IMAGE_REFERENCE')
            for key, value in refs.items():
                for asset_id in (value if isinstance(value, list) else [value]):
                    row = box.row(align=True)
                    row.label(text=f"{key}: {asset_id}")
                    op = row.operator("scenario.copy_text", text="", icon='COPYDOWN')
                    op.text, op.what = asset_id, "asset id"
            for path in inputs:
                box.label(text=os.path.basename(path), icon='FILE')
        if rec.asset_ids:
            box = layout.box()
            box.label(text="Result assets", icon='OUTLINER_OB_IMAGE')
            for asset_id in rec.asset_ids:
                row = box.row(align=True)
                row.label(text=f"{asset_id}  {rec.asset_types.get(asset_id, '')}")
                op = row.operator("scenario.copy_text", text="", icon='COPYDOWN')
                op.text, op.what = asset_id, "asset id"
        if rec.files:
            box = layout.box()
            box.label(text="Files", icon='FILE_FOLDER')
            for path in rec.files:
                box.label(text=os.path.basename(path))
        if rec.error:
            layout.label(text=rec.error[:110], icon='ERROR')
        errors = rec.meta.get("download_errors") or {}
        for asset_id, reason in list(errors.items())[:4]:
            layout.label(text=f"{asset_id}: {str(reason)[:80]}", icon='ERROR')

    def execute(self, context):
        return {'FINISHED'}


def _wrap(text, width):
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width and current:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines[:12]


class SCENARIO_OT_add_sound_strip(bpy.types.Operator):
    bl_idname = "scenario.add_sound_strip"
    bl_label = "Add to sequencer"
    bl_description = "Add this audio file as a sound strip at the current frame"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty()

    def execute(self, context):
        from . import apply_audio

        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}
        strip = apply_audio.add_to_sequencer(context, self.filepath)
        self.report({'INFO'}, f"Sound strip {strip.name} added on channel {strip.channel}")
        return {'FINISHED'}


def _job_objects(local_id, names):
    """Objects of a generation: by the job tag stamped on import, else by the names recorded at import time."""
    from . import apply_3d

    found = apply_3d.objects_of_job(local_id) if local_id else []
    if not found:
        found = [bpy.data.objects[n] for n in (n for n in names.split("|") if n) if n in bpy.data.objects]
    return found


class SCENARIO_OT_select_result_objects(bpy.types.Operator):
    bl_idname = "scenario.select_result_objects"
    bl_label = "Select in scene"
    bl_description = "Select the objects this generation created (then move, hide or delete them like any object)"
    names: StringProperty(description="Object names separated by |")
    local_id: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        found = _job_objects(self.local_id, self.names)
        if not found:
            self.report({'WARNING'}, "Those objects are no longer in the file (use Add to scene to import them again)")
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in found:
            obj.select_set(True)
        context.view_layer.objects.active = found[0]
        self.report({'INFO'}, f"Selected {len(found)} object(s)")
        return {'FINISHED'}


class SCENARIO_OT_delete_result_objects(bpy.types.Operator):
    bl_idname = "scenario.delete_result_objects"
    bl_label = "Delete from scene"
    bl_description = "Delete the objects this generation created (the files stay in the output folder)"
    bl_options = {'REGISTER', 'UNDO'}
    names: StringProperty(description="Object names separated by |")
    local_id: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        count = len(_job_objects(self.local_id, self.names))
        if count == 0:
            self.report({'WARNING'}, "Those objects are no longer in the file")
            return {'CANCELLED'}
        return context.window_manager.invoke_confirm(self, event, title=f"Delete {count} object(s) of this generation?", confirm_text="Delete")

    def execute(self, context):
        found = _job_objects(self.local_id, self.names)
        for obj in found:
            bpy.data.objects.remove(obj, do_unlink=True)
        self.report({'INFO'}, f"Deleted {len(found)} object(s)")
        return {'FINISHED'}


class SCENARIO_OT_mcp_start(bpy.types.Operator):
    bl_idname = "scenario.mcp_start"
    bl_label = "Start MCP server"
    bl_description = "Start the local MCP server so agents can connect to this Blender"

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
    bl_description = "Stop the local MCP server"

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


class SCENARIO_OT_import_mesh_file(bpy.types.Operator):
    bl_idname = "scenario.import_mesh_file"
    bl_label = "Import mesh file"
    bl_description = "Import this mesh at the 3D cursor"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty()
    local_id: StringProperty(description="Generation the objects belong to (for Select and Delete)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        from . import apply_3d

        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}
        objects = apply_3d.import_model(context, self.filepath, at_cursor=True, local_id=self.local_id)
        if self.local_id:
            for rec in runtime.state.jobs_view:
                if rec.local_id == self.local_id:
                    rec.meta["objects"] = list(rec.meta.get("objects") or []) + [o.name for o in objects]
        self.report({'INFO'}, f"Imported {len(objects)} object(s)")
        return {'FINISHED'}


CLASSES = (SCENARIO_OT_import_mesh_file, SCENARIO_OT_set_lane, SCENARIO_OT_mcp_start, SCENARIO_OT_mcp_stop, SCENARIO_OT_mcp_copy, SCENARIO_OT_use_first_frame, SCENARIO_OT_clear_first_frame, SCENARIO_OT_select_result_objects,
           SCENARIO_OT_copy_text, SCENARIO_OT_toggle_result, SCENARIO_OT_result_details, SCENARIO_OT_add_sound_strip, SCENARIO_OT_delete_result_objects, SCENARIO_OT_play_video, SCENARIO_OT_play_video_blender, SCENARIO_OT_history_refresh, SCENARIO_OT_history_older, SCENARIO_OT_import_result, SCENARIO_OT_test_connection, SCENARIO_OT_refresh_catalog, SCENARIO_OT_generate, SCENARIO_OT_add_reference,
           SCENARIO_OT_remove_reference, SCENARIO_OT_toggle_multi, SCENARIO_OT_open_output_folder, SCENARIO_OT_show_image,
           SCENARIO_OT_apply_texture, SCENARIO_OT_add_plane, SCENARIO_OT_expand_prompt, SCENARIO_OT_retile_material)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
