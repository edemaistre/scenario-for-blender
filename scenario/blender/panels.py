# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""N-panel: account strip, lane tabs, schema-driven lane forms, running jobs, results."""
import os

import bpy

from . import generation, params_ui, props, runtime

LANE_PLACEHOLDER = {}
KIND_ICON = {"image": 'IMAGE_DATA', "video": 'FILE_MOVIE', "3d": 'MESH_DATA', "material": 'MATERIAL'}
GENERATE_LANES = ("image", "video", "3d", "material")


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


def draw_references(layout, lane_state, schema):
    refs = params_ui.collect_file_refs(lane_state, schema)
    for spec in schema.specs:
        if not spec.is_file:
            continue
        box = layout.box()
        header = box.row()
        count = len(refs.get(spec.name, []))
        label = spec.label + (" (required)" if spec.required_always else "")
        header.label(text=f"{label}  {count}" + (f"/{spec.max_length}" if spec.max_length else ""), icon='IMAGE_DATA' if spec.kind == 'image' else 'FILE')
        add = header.operator_menu_enum("scenario.add_reference", "source", text="Add", icon='ADD')
        add.lane, add.param_name = lane_state.lane, spec.name
        for index, ref in enumerate(lane_state.references):
            if ref.param_name != spec.name:
                continue
            row = box.row(align=True)
            row.label(text=ref.label or ref.filepath or ref.source, icon='DOT')
            remove = row.operator("scenario.remove_reference", text="", icon='X')
            remove.lane, remove.index = lane_state.lane, index


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


def draw_generate_lane(layout, context, lane):
    lane_state = context.scene.scenario.lane_state(lane)
    if not runtime.state.catalog_loaded:
        if runtime.state.catalog_error:
            layout.label(text=runtime.state.catalog_error[:70], icon='ERROR')
            layout.operator("scenario.refresh_catalog", text="Retry loading models", icon='FILE_REFRESH')
        else:
            layout.label(text="Loading models...", icon='TIME')
        return
    if lane == "3d":
        layout.row(align=True).prop(context.scene.scenario, "three_d_mode", expand=True)
    layout.prop(lane_state, "model_id", text="Model")
    record = runtime.state.records.get(lane_state.model_id)
    if record is not None and record.short_description:
        layout.label(text=record.short_description[:70], icon='INFO')
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
    row = layout.row(align=True)
    row.scale_y = 1.4
    row.operator("scenario.generate", text=generate_button_text(lane_state), icon='PLAY').lane = lane
    if lane_state.estimate_state in ('ERROR', 'UNAVAILABLE') and lane_state.estimate_error:
        layout.label(text=lane_state.estimate_error[:80], icon='INFO')
    if lane_state.last_error:
        layout.label(text=lane_state.last_error[:80], icon='ERROR')


def draw_history(layout, context):
    row = layout.row(align=True)
    row.operator("scenario.history_refresh", icon='FILE_REFRESH')
    row.operator("scenario.open_output_folder", text="", icon='FILE_FOLDER')
    if not runtime.state.history:
        layout.label(text="Press Refresh to list this project's generations")
        return
    for entry in runtime.state.history[:24]:
        box = layout.box()
        header = box.row()
        header.label(text=(entry.prompt or entry.model_id)[:48], icon=KIND_ICON.get(entry.kind, 'FILE'))
        header.label(text=f"{entry.cu_cost:g} CU" if entry.cu_cost is not None else entry.status)
        if entry.local_files and entry.kind == "image":
            icon_id = _thumbnail(entry.local_files[0])
            if icon_id:
                box.template_icon(icon_value=icon_id, scale=3.0)
        if entry.is_success:
            op = box.operator("scenario.import_result", text="Import into scene" if not entry.local_files else "Bring into scene again", icon='IMPORT')
            op.job_id, op.kind, op.model_id, op.prompt = entry.job_id, entry.kind, entry.model_id, entry.prompt
        else:
            box.label(text=entry.status, icon='ERROR' if entry.status in ("failure", "failed", "canceled") else 'TIME')
    if runtime.state.history_token:
        layout.operator("scenario.history_older", icon='TRIA_DOWN')


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
    box.label(text="Tools: scene, objects, Python, screenshots, models, cost, generate, import", icon='INFO')


class SCENARIO_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Scenario"

    def draw(self, context):
        layout = self.layout
        if not draw_account_strip(layout, context):
            return
        scenario = context.scene.scenario
        grid = layout.grid_flow(columns=4, align=True)
        grid.prop(scenario, "lane", expand=True)
        lane = scenario.lane
        if lane in GENERATE_LANES:
            draw_generate_lane(layout, context, lane)
        elif lane == "history":
            draw_history(layout, context)
        elif lane == "mcp":
            draw_mcp_lane(layout, context)
        elif lane == "render":
            from . import render_to_real

            if not runtime.state.catalog_loaded:
                layout.label(text="Loading models...", icon='TIME')
            else:
                render_to_real.draw_render_lane(layout, context)
        else:
            layout.label(text=LANE_PLACEHOLDER.get(lane, ""), icon='INFO')
        if runtime.state.last_message:
            layout.label(text=runtime.state.last_message[:80])


class SCENARIO_PT_jobs(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Running"
    bl_parent_id = "SCENARIO_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return any(not r.is_terminal for r in runtime.state.jobs_view)

    def draw(self, context):
        for rec in runtime.state.jobs_view:
            if rec.is_terminal:
                continue
            row = self.layout.row()
            row.label(text=f"{rec.meta.get('model_name', rec.model_id)}  {rec.status} {int(rec.progress * 100)}%", icon='TIME')


class SCENARIO_PT_results(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Results"
    bl_parent_id = "SCENARIO_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.operator("scenario.open_output_folder", icon='FILE_FOLDER')
        shown = 0
        for rec in runtime.state.jobs_view:
            if not rec.is_terminal:
                continue
            box = layout.box()
            title = rec.meta.get("prompt") or rec.meta.get("model_name") or rec.model_id
            box.label(text=title[:60], icon='CHECKMARK' if rec.is_success else 'ERROR')
            if rec.error:
                box.label(text=rec.error[:70])
            for path in rec.files[:6]:
                if rec.kind == "image":
                    icon_id = _thumbnail(path)
                    row = box.row(align=True)
                    if icon_id:
                        row.template_icon(icon_value=icon_id, scale=3.0)
                    col = row.column(align=True)
                    col.operator("scenario.show_image", text="Show").filepath = path
                    col.operator("scenario.apply_texture", text="Apply as texture").filepath = path
                    col.operator("scenario.add_plane", text="Add as plane").filepath = path
                elif rec.kind == "3d":
                    if path == rec.files[0]:
                        primary = rec.meta.get("primary_mesh") or ""
                        if primary:
                            box.label(text="Imported: " + os.path.basename(primary)[-48:], icon='MESH_DATA')
                        for alt in rec.meta.get("mesh_alternates") or []:
                            row = box.row(align=True)
                            row.label(text=os.path.basename(alt)[-40:], icon='FILE_3D')
                            row.operator("scenario.import_mesh_file", text="Import").filepath = alt
                        textures = [p for p in rec.files if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
                        if textures:
                            box.label(text=f"{len(textures)} texture file(s) on disk", icon='TEXTURE')
                elif rec.kind == "video":
                    row = box.row(align=True)
                    row.operator("scenario.play_video", text="Play", icon='PLAY').filepath = path
                    row.operator("scenario.play_video_blender", text="Play in Blender", icon='BLENDER').filepath = path
                elif rec.kind == "material":
                    if path == rec.files[0]:
                        box.label(text="PBR material", icon='MATERIAL')
                        mat_name = rec.meta.get("material_name") or f"Scenario {(rec.meta.get('prompt') or rec.model_id).strip()[:40]}"
                        if bpy.data.materials.get(mat_name):
                            box.operator("scenario.retile_material", text="Tiling", icon='UV').material_name = mat_name
                else:
                    box.label(text=os.path.basename(path), icon='FILE')
            shown += 1
            if shown >= 8:
                break
        if shown == 0:
            layout.label(text="Nothing generated yet")


def _thumbnail(path):
    if not os.path.exists(path) or not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return 0
    previews = runtime.previews()
    if path not in previews:
        previews.load(path, path, 'IMAGE')
    return previews[path].icon_id


CLASSES = (SCENARIO_PT_main, SCENARIO_PT_jobs, SCENARIO_PT_results)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
