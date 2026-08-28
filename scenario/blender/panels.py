# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Scenario tab: four panels. "Scenario" (what to generate), "Jobs" (what is running), "Generations" (what came
back, here and in the cloud), "Agents" (the MCP server). Lane tabs only cover generation."""
import os

import bpy

from . import generation, params_ui, props, runtime

KIND_ICON = {"image": 'IMAGE_DATA', "video": 'FILE_MOVIE', "3d": 'MESH_DATA', "material": 'MATERIAL'}
GENERATE_LANES = ("image", "video", "3d", "material")
SOURCE_ICON = {'FILE': 'FILE_IMAGE', 'VIEWPORT': 'RESTRICT_VIEW_OFF', 'CAMERA': 'CAMERA_DATA', 'VIEWPORT_CLIP': 'RENDER_ANIMATION', 'CAMERA_CLIP': 'RENDER_ANIMATION',
               'RENDER': 'RENDER_RESULT', 'ASSET': 'URL', 'MESH': 'MESH_DATA'}
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def draw_account_strip(layout, context):
    creds = runtime.credentials()
    row = layout.row(align=True)
    if not creds.valid:
        row.label(text="Add your API key in Preferences", icon='ERROR')
        row.operator("preferences.addon_show", text="", icon='PREFERENCES').module = runtime.PACKAGE
        return False
    if not runtime.online():
        row.label(text="Online access is disabled", icon='ERROR')
        return False
    row.label(text=runtime.state.account_label or "Scenario", icon='CHECKMARK')
    row.operator("scenario.refresh_catalog", text="", icon='FILE_REFRESH')
    row.operator("preferences.addon_show", text="", icon='PREFERENCES').module = runtime.PACKAGE
    return True


def thumbnail(path):
    """Preview icon id for an image file on disk (0 when there is none). Loads lazily into the shared preview collection."""
    if not path or not os.path.exists(path) or not path.lower().endswith(IMAGE_EXTS):
        return 0
    previews = runtime.previews()
    if path not in previews:
        previews.load(path, path, 'IMAGE')
    return previews[path].icon_id


_thumbnail = thumbnail


def draw_model_row(layout, lane_state, lane):
    """The model chooser: the search dialog when the picker module is present, the plain dropdown otherwise."""
    try:
        from . import model_picker

        model_picker.draw_model_row(layout, lane_state, lane)
    except ImportError:
        layout.prop(lane_state, "model_id", text="Model")
    record = runtime.state.records.get(lane_state.model_id)
    if record is not None and record.short_description:
        layout.label(text=record.short_description[:70], icon='INFO')


def draw_reference_row(box, lane_state, index, ref):
    row = box.row(align=True)
    path = bpy.path.abspath(ref.filepath) if ref.filepath else ""
    icon_id = thumbnail(path) if ref.source == 'FILE' else 0
    if icon_id:
        row.template_icon(icon_value=icon_id, scale=2.2)
        row.label(text=(ref.label or os.path.basename(path))[-34:])
    else:
        row.label(text=ref.label or ref.filepath or ref.source, icon=SOURCE_ICON.get(ref.source, 'DOT'))
    remove = row.operator("scenario.remove_reference", text="", icon='X')
    remove.lane, remove.index = props.lane_of(lane_state), index


def draw_references(layout, lane_state, schema, title_for=None, fixed_first=None, hide=()):
    """One box per file input. `fixed_first` names an implicit first entry (the capture, the selected mesh) that
    the lane adds itself; `title_for` overrides the box title; `hide` skips inputs entirely."""
    title_for, fixed_first = title_for or {}, fixed_first or {}
    refs = params_ui.collect_file_refs(lane_state, schema)
    lane = props.lane_of(lane_state)
    for spec in schema.specs:
        if not spec.is_file or spec.name in hide:
            continue
        box = layout.box()
        header = box.row()
        count = len(refs.get(spec.name, [])) + (1 if spec.name in fixed_first else 0)
        label = title_for.get(spec.name) or (spec.label + (" (required)" if spec.required_always else ""))
        icon = 'IMAGE_DATA' if (spec.kind or "image") == "image" else ('FILE_MOVIE' if spec.kind == "video" else ('MESH_DATA' if spec.kind == "3d" else 'FILE'))
        header.label(text=f"{label}  {count}" + (f"/{spec.max_length}" if spec.max_length else ""), icon=icon)
        if not (spec.ptype == "file" and spec.name in fixed_first):
            add = header.operator_menu_enum("scenario.add_reference", "source", text="Add", icon='ADD')
            add.lane, add.param_name = lane, spec.name
        if spec.name in fixed_first:
            row = box.row(align=True)
            row.enabled = False
            row.label(text=fixed_first[spec.name], icon='PINNED')
        for index, ref in enumerate(lane_state.references):
            if ref.param_name != spec.name:
                continue
            draw_reference_row(box, lane_state, index, ref)


def draw_clip_options(layout, context, lane_state, schema):
    from ..core.scene import capture_plan

    has_video_input = any(s.is_file and s.kind == "video" for s in schema.specs)
    uses_capture = any(r.source in props.CAPTURE_SOURCES for r in lane_state.references)
    if not has_video_input and not uses_capture:
        return
    box = layout.box()
    box.label(text="Blender input", icon='RENDER_ANIMATION')
    scene = context.scene
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    start, end, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                  preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    box.label(text=f"Clip: frames {start} to {end}, {seconds:.1f} s at 1280x720")
    if schema.by_name("duration") is not None:
        box.prop(lane_state, "match_timeline")
    box.prop(lane_state, "force_solid")


def generate_button_text(lane_state):
    if lane_state.estimate_state == 'READY':
        prefix = "from " if lane_state.estimate_partial else ""
        return f"Generate  ({prefix}{lane_state.estimate_cu:g} CU)"
    if lane_state.estimate_state == 'PENDING':
        return "Generate  (estimating...)"
    return "Generate"


def draw_generate_row(layout, lane_state, lane):
    row = layout.row(align=True)
    row.scale_y = 1.4
    row.operator("scenario.generate", text=generate_button_text(lane_state), icon='PLAY').lane = lane
    if lane_state.estimate_state in ('ERROR', 'UNAVAILABLE') and lane_state.estimate_error:
        layout.label(text=lane_state.estimate_error[:80], icon='INFO')
    if lane_state.last_error:
        layout.label(text=lane_state.last_error[:80], icon='ERROR')


def draw_loading(layout):
    if runtime.state.catalog_error:
        layout.label(text=runtime.state.catalog_error[:70], icon='ERROR')
        layout.operator("scenario.refresh_catalog", text="Retry loading models", icon='FILE_REFRESH')
    else:
        layout.label(text="Loading models...", icon='TIME')


def draw_generate_lane(layout, context, lane):
    lane_state = context.scene.scenario.lane_state(lane)
    if lane == "3d":
        layout.row(align=True).prop(context.scene.scenario, "three_d_mode", expand=True)
    draw_model_row(layout, lane_state, lane)
    schema = generation.schema_for(lane_state.model_id)
    if schema is None:
        layout.label(text=lane_state.last_error or "Loading the model description...", icon='ERROR' if lane_state.last_error else 'TIME')
        return
    row = layout.row(align=True)
    row.prop(lane_state, "prompt", text="")
    row.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL').lane = lane
    draw_references(layout, lane_state, schema)
    params_ui.draw_params(layout, lane_state, schema)
    if lane == "video":
        draw_clip_options(layout, context, lane_state, schema)
    if lane == "material":
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if meshes:
            layout.label(text=f"Applies to {len(meshes)} selected mesh(es)", icon='MATERIAL')
        else:
            layout.label(text="Select a mesh to apply the material on arrival", icon='INFO')
    draw_generate_row(layout, lane_state, lane)


def draw_edit3d_lane(layout, context):
    from . import mesh_export
    from ..core.api.catalog import edit3d_task, mesh_param

    scene = context.scene
    lane_state = scene.scenario.lane_state("edit3d")
    box = layout.box()
    objects = mesh_export.source_objects(context)
    if objects:
        names = ", ".join(o.name for o in objects[:3]) + (" +%d" % (len(objects) - 3) if len(objects) > 3 else "")
        box.label(text=f"Mesh: {names}", icon='MESH_DATA')
        box.label(text="Exported as GLB at generate time; the result lands next to it", icon='INFO')
    else:
        box.label(text="Select the mesh to edit in the viewport", icon='ERROR')
    grid = layout.grid_flow(columns=4, align=True)
    grid.prop(scene.scenario, "edit3d_task", expand=True)
    task = edit3d_task(scene.scenario.edit3d_task)
    layout.label(text=task[2], icon='INFO')
    if not runtime.state.lane_models.get("edit3d"):
        layout.label(text="No model for this task in the catalog", icon='ERROR')
        return
    draw_model_row(layout, lane_state, "edit3d")
    schema = generation.schema_for(lane_state.model_id)
    if schema is None:
        layout.label(text=lane_state.last_error or "Loading the model description...", icon='ERROR' if lane_state.last_error else 'TIME')
        return
    if schema.prompt_name:
        row = layout.row(align=True)
        row.prop(lane_state, "prompt", text="")
        row.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL').lane = "edit3d"
    record = runtime.state.records.get(lane_state.model_id)
    mesh_name = mesh_param(record) if record is not None else None
    draw_references(layout, lane_state, schema, fixed_first={mesh_name: "Selected mesh (exported at generate time)"} if mesh_name else None)
    params_ui.draw_params(layout, lane_state, schema)
    draw_generate_row(layout, lane_state, "edit3d")


def draw_mcp_lane(layout, context):
    from . import mcp_service

    st = mcp_service.status()
    box = layout.box()
    box.label(text="Let agents build in this Blender", icon='PLUGIN')
    if st["running"]:
        box.label(text=f"Running on {st['url']}", icon='CHECKMARK')
        box.label(text=f"Token {mcp_service.masked_token()}  ({st['calls']} tool calls served)")
        box.operator("scenario.mcp_stop", icon='PAUSE')
    else:
        box.label(text=st["error"] or "Stopped", icon='ERROR' if st["error"] else 'INFO')
        box.operator("scenario.mcp_start", icon='PLAY')
    prefs = runtime.prefs()
    if prefs is not None:
        box.prop(prefs, "mcp_allow_python")
    box = layout.box()
    box.label(text="Connect a client (copies the setup)", icon='COPYDOWN')
    col = box.column(align=True)
    for kind, label in (("claude_code", "Claude Code"), ("cursor", "Cursor"), ("claude_desktop", "Claude Desktop (stdio)"), ("codex", "Codex"), ("curl", "curl test")):
        col.operator("scenario.mcp_copy", text=label, icon='CONSOLE').kind = kind
    box.label(text="Tools: scene, objects, Python, screenshots, camera path, models, cost, generate, import", icon='INFO')


# -- results ------------------------------------------------------------------

def _draw_inputs(box, rec):
    inputs = [p for p in (rec.meta.get("inputs") or []) if isinstance(p, str)]
    if not inputs:
        return
    row = box.row(align=True)
    row.label(text="Inputs:", icon='IMPORT')
    shown = 0
    for path in inputs:
        icon_id = thumbnail(path)
        if icon_id:
            row.template_icon(icon_value=icon_id, scale=1.6)
            shown += 1
        else:
            row.label(text="", icon='FILE_MOVIE' if path.lower().endswith((".mp4", ".mov", ".webm")) else ('MESH_DATA' if path.lower().endswith((".glb", ".gltf", ".fbx", ".obj")) else 'FILE'))
        if shown >= 6:
            break


def draw_result(layout, rec):
    box = layout.box()
    title = rec.meta.get("prompt") or rec.meta.get("spark_look") or rec.meta.get("model_name") or rec.model_id
    header = box.row()
    header.label(text=title[:56], icon='CHECKMARK' if rec.is_success else 'ERROR')
    header.label(text=f"{rec.cu_cost:g} CU" if rec.cu_cost is not None else "", icon=KIND_ICON.get(rec.kind, 'FILE'))
    if rec.error:
        box.label(text=rec.error[:70])
    _draw_inputs(box, rec)
    if rec.kind == "image":
        for path in rec.files[:6]:
            icon_id = thumbnail(path)
            row = box.row(align=True)
            if icon_id:
                row.template_icon(icon_value=icon_id, scale=3.0)
            col = row.column(align=True)
            col.operator("scenario.show_image", text="Show").filepath = path
            col.operator("scenario.apply_texture", text="Apply as texture").filepath = path
            col.operator("scenario.add_plane", text="Add as plane").filepath = path
            col.operator("scenario.use_first_frame", text="Use as video first frame", icon='FILE_MOVIE').filepath = path
    elif rec.kind == "3d":
        primary = rec.meta.get("primary_mesh") or next((p for p in rec.files if p.lower().endswith((".glb", ".gltf", ".fbx", ".obj"))), "")
        if primary:
            box.label(text=os.path.basename(primary)[-48:], icon='MESH_DATA')
            row = box.row(align=True)
            row.operator("scenario.import_mesh_file", text="Add to scene", icon='IMPORT').filepath = primary
            names = rec.meta.get("objects") or []
            if names:
                row.operator("scenario.select_result_objects", text="Select", icon='RESTRICT_SELECT_OFF').names = "|".join(names)
        for alt in rec.meta.get("mesh_alternates") or []:
            row = box.row(align=True)
            row.label(text=os.path.basename(alt)[-40:], icon='FILE_3D')
            row.operator("scenario.import_mesh_file", text="Add").filepath = alt
        textures = [p for p in rec.files if p.lower().endswith(IMAGE_EXTS)]
        if textures:
            box.label(text=f"{len(textures)} texture file(s) on disk", icon='TEXTURE')
    elif rec.kind == "video":
        for path in rec.files[:3]:
            row = box.row(align=True)
            row.operator("scenario.play_video", text="Play", icon='PLAY').filepath = path
            row.operator("scenario.play_video_blender", text="Play in Blender", icon='BLENDER').filepath = path
    elif rec.kind == "material":
        box.label(text="PBR material", icon='MATERIAL')
        mat_name = rec.meta.get("material_name") or f"Scenario {(rec.meta.get('prompt') or rec.model_id).strip()[:40]}"
        if bpy.data.materials.get(mat_name):
            box.operator("scenario.retile_material", text="Tiling", icon='UV').material_name = mat_name
    elif rec.files:
        box.label(text=os.path.basename(rec.files[0]), icon='FILE')


def draw_history(layout, context):
    if not runtime.state.history:
        layout.label(text="Press Refresh to list this project's generations", icon='INFO')
        return
    for entry in runtime.state.history[:24]:
        box = layout.box()
        header = box.row()
        header.label(text=(entry.prompt or entry.model_id)[:48], icon=KIND_ICON.get(entry.kind, 'FILE'))
        header.label(text=f"{entry.cu_cost:g} CU" if entry.cu_cost is not None else entry.status)
        if entry.local_files and entry.kind == "image":
            icon_id = thumbnail(entry.local_files[0])
            if icon_id:
                box.template_icon(icon_value=icon_id, scale=3.0)
        if entry.is_success:
            op = box.operator("scenario.import_result", text="Import into scene" if not entry.local_files else "Bring into scene again", icon='IMPORT')
            op.job_id, op.kind, op.model_id, op.prompt = entry.job_id, entry.kind, entry.model_id, entry.prompt
        else:
            box.label(text=entry.status, icon='ERROR' if entry.status in ("failure", "failed", "canceled") else 'TIME')
    if runtime.state.history_token:
        layout.operator("scenario.history_older", icon='TRIA_DOWN')


# -- panels -------------------------------------------------------------------

class SCENARIO_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Scenario"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        if not draw_account_strip(layout, context):
            return
        scenario = context.scene.scenario
        grid = layout.grid_flow(columns=4, align=True)
        grid.prop(scenario, "lane", expand=True)
        lane = scenario.lane
        if not runtime.state.catalog_loaded:
            draw_loading(layout)
        elif lane in GENERATE_LANES:
            draw_generate_lane(layout, context, lane)
        elif lane == "render_image":
            from . import render_lanes

            render_lanes.draw_render_image_lane(layout, context)
        elif lane == "render_video":
            from . import render_lanes

            render_lanes.draw_render_video_lane(layout, context)
        elif lane == "edit3d":
            draw_edit3d_lane(layout, context)
        if runtime.state.last_message:
            layout.label(text=runtime.state.last_message[:80])


STATUS_TEXT = {"preparing": "Prompt Spark is writing the look", "submitting": "uploading and submitting", "queued": "queued", "in-progress": "rendering"}


class SCENARIO_PT_jobs(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Jobs"
    bl_order = 1

    def draw_header(self, context):
        active = sum(1 for r in runtime.state.jobs_view if not r.is_terminal)
        if active:
            self.layout.label(text=str(active))

    def draw(self, context):
        layout = self.layout
        active = [r for r in runtime.state.jobs_view if not r.is_terminal]
        if not active:
            layout.label(text="No job running", icon='CHECKMARK')
            return
        for rec in active:
            box = layout.box()
            row = box.row(align=True)
            row.label(text=(rec.meta.get("prompt") or rec.meta.get("model_name") or rec.model_id)[:44], icon=KIND_ICON.get(rec.kind, 'TIME'))
            status = STATUS_TEXT.get(rec.status, rec.status)
            progress = f" {int(rec.progress * 100)}%" if rec.status == "in-progress" else ""
            box.label(text=f"{rec.meta.get('model_name', rec.model_id)}: {status}{progress}", icon='TIME')


class SCENARIO_PT_generations(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Generations"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator("scenario.open_output_folder", text="Output folder", icon='FILE_FOLDER')
        row.operator("scenario.history_refresh", text="Refresh cloud", icon='FILE_REFRESH')
        row.prop(context.scene.scenario, "show_cloud_history", text="", icon='WORLD')
        layout.label(text="This session", icon='TIME')
        shown = 0
        for rec in runtime.state.jobs_view:
            if not rec.is_terminal:
                continue
            draw_result(layout, rec)
            shown += 1
            if shown >= 8:
                break
        if shown == 0:
            layout.label(text="Nothing generated yet in this session")
        if context.scene.scenario.show_cloud_history:
            layout.separator()
            layout.label(text="Project history (cloud)", icon='WORLD')
            draw_history(layout, context)


class SCENARIO_PT_agents(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Agents (MCP)"
    bl_order = 3
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_mcp_lane(self.layout, context)


CLASSES = (SCENARIO_PT_main, SCENARIO_PT_jobs, SCENARIO_PT_generations, SCENARIO_PT_agents)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
