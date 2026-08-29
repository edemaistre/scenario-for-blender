# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Scenario tab: four panels. "Scenario" (what to generate), "Jobs" (what is running), "Generations" (what came
back, here and in the cloud), "Agents" (the MCP server). Lane tabs only cover generation."""
import os

import bpy

from . import generation, params_ui, props, runtime

KIND_ICON = {"image": 'IMAGE_DATA', "video": 'FILE_MOVIE', "3d": 'MESH_DATA', "material": 'MATERIAL', "audio": 'SPEAKER'}
GENERATE_LANES = ("image", "video", "3d", "material", "audio")
SOURCE_ICON = {'FILE': 'FILE_IMAGE', 'VIEWPORT': 'RESTRICT_VIEW_OFF', 'CAMERA': 'CAMERA_DATA', 'VIEWPORT_CLIP': 'RENDER_ANIMATION', 'CAMERA_CLIP': 'RENDER_ANIMATION',
               'RENDER': 'RENDER_RESULT', 'ASSET': 'URL', 'MESH': 'MESH_DATA'}
# short labels for the reference-add buttons (the enum labels read as list entries; these read as actions)
ADD_SOURCE_LABEL = {'FILE': "Upload", 'MESH': "Selected mesh", 'RENDER': "Render", 'VIEWPORT': "Viewport", 'CAMERA': "Camera",
                    'VIEWPORT_CLIP': "Viewport clip", 'CAMERA_CLIP': "Camera clip"}
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MESH_EXTS = (".glb", ".gltf", ".fbx", ".obj", ".spz", ".ply")
AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".flac")


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
    label = runtime.state.account_label or ("Connected" if runtime.state.catalog_loaded else "Connecting...")
    row.label(text=label, icon='CHECKMARK' if runtime.state.catalog_loaded else 'SORTTIME')
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


def equal_segments(parent, struct, prop, values):
    """One continuous segmented control filling the row: a `prop_enum` per value in an align=True row (Blender merges
    the borders), with a chain of even splits so the cells share the full width. Rows with fewer values get wider
    cells, so cell sizes differ from row to row. Text and icons are Blender's own for the enum item."""
    row = parent.row(align=True)
    container, n = row, len(values)
    for i, value in enumerate(values):
        remaining = n - i
        seg = container.split(factor=1.0 / remaining, align=True) if remaining > 1 else container
        seg.prop_enum(struct, prop, value)
        container = seg


def draw_enum_tabs(layout, struct, prop, rows):
    """Tab rows: each row a continuous full-width segmented control (cells wider when the row holds fewer values)."""
    col = layout.column(align=True)
    for values in rows:
        equal_segments(col, struct, prop, values)


def draw_prompt_row(layout, lane_state, lane, text="", placeholder=None):
    """Prompt with the Spark / Rewrite / Translate buttons (plain prompt when prompt_tools is missing)."""
    try:
        from . import prompt_tools

        prompt_tools.draw_prompt_row(layout, lane_state, lane, text=text, placeholder=placeholder)
    except ImportError:
        row = layout.row(align=True)
        if text:
            row.label(text=text)
        row.prop(lane_state, "prompt", text="")


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


def draw_references(layout, lane_state, schema, title_for=None, fixed_first=None, hide=(), boxed=True):
    """One file input per group. `fixed_first` names an implicit first entry (the capture, the selected mesh) that
    the lane adds itself; `title_for` overrides the title; `hide` skips inputs entirely. `boxed=False` draws flat,
    without a box, for callers that are already inside one (avoids nesting coloured boxes)."""
    from . import mesh_export

    title_for, fixed_first = title_for or {}, fixed_first or {}
    refs = params_ui.collect_file_refs(lane_state, schema)
    lane = props.lane_of(lane_state)
    # A 3D input is fed by the scene selection automatically (any lane), so a selected mesh is used without a click.
    # Only when the user has attached an explicit file/asset for that input is the selection not shown.
    selected = mesh_export.source_objects(bpy.context)
    if selected and lane != "edit3d":  # the Edit lane passes its own pinned label
        names = ", ".join(o.name for o in selected[:2]) + (f" +{len(selected) - 2}" if len(selected) > 2 else "")
        for spec in schema.specs:
            if spec.is_file and (spec.kind or "").lower() == "3d" and spec.name not in fixed_first \
                    and not any(r.param_name == spec.name for r in lane_state.references):
                fixed_first.setdefault(spec.name, f"Selected mesh: {names}")
    for spec in schema.specs:
        if not spec.is_file or spec.name in hide:
            continue
        box = layout.box() if boxed else layout.column(align=True)
        header = box.row()
        count = len(refs.get(spec.name, [])) + (1 if spec.name in fixed_first else 0)
        label = title_for.get(spec.name) or (spec.label + (" (required)" if spec.required_always else ""))
        kind = spec.kind or "image"
        icon = {'image': 'IMAGE_DATA', 'video': 'FILE_MOVIE', '3d': 'MESH_DATA', 'audio': 'SPEAKER'}.get(kind, 'FILE')
        header.label(text=f"{label}  {count}" + (f"/{spec.max_length}" if spec.max_length else ""), icon=icon)
        # the Edit lane's required mesh hides its add options; everywhere else offer the kind-appropriate sources
        # (a 3D input: Upload a model to override the selection; image/video: stills or clips) even when auto-pinned.
        if not (spec.ptype == "file" and spec.name in fixed_first and lane == "edit3d"):
            add_row = box.row(align=True)
            for source_id, source_label, _desc in props.addable_sources_for(spec.kind):
                op = add_row.operator("scenario.add_reference", text=ADD_SOURCE_LABEL.get(source_id, source_label), icon=SOURCE_ICON.get(source_id, 'ADD'))
                op.lane, op.param_name, op.source = lane, spec.name, source_id
        if spec.name in fixed_first:
            row = box.row(align=True)
            row.enabled = False
            row.label(text=fixed_first[spec.name], icon='PINNED')
        elif (spec.kind or "").lower() == "3d" and not refs.get(spec.name):
            box.label(text="Select a mesh in the viewport to animate it, or Upload one", icon='INFO')
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
    box.label(text="Scene clip", icon='RENDER_ANIMATION')
    scene = context.scene
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    start, end, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                  preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    box.label(text=f"Frames {start} to {end}: {seconds:.1f} s at {fps:g} fps, 1280x720")
    if schema.by_name("duration") is not None:
        box.prop(lane_state, "match_timeline")
        if lane_state.match_timeline:
            _, value, note = generation.timeline_sync_info(context.scene, lane_state, schema)
            if note:
                box.label(text=f"Clip {note} for the model", icon='INFO')
    box.prop(lane_state, "force_solid")


def generate_button_text(lane_state):
    if lane_state.estimate_state == 'READY':
        prefix = "from " if lane_state.estimate_partial else ""
        return f"Generate  ({prefix}{lane_state.estimate_cu:g} CU)"
    if lane_state.estimate_state == 'PENDING':
        return "Generate  (estimating...)"
    return "Generate"


def draw_generate_row(layout, lane_state, lane):
    layout.separator(factor=0.5)  # breathing room above the primary action
    row = layout.row(align=True)
    row.scale_y = 1.5
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
        layout.operator("scenario.blockout", text="Blockout from prompt", icon='MESH_CUBE')  # grey-box the scene from text
        if context.scene.scenario.three_d_mode == 'EDIT':
            draw_edit3d_lane(layout, context)
            return
    draw_model_row(layout, lane_state, lane)
    schema = generation.schema_for(lane_state.model_id)
    if schema is None:
        layout.label(text=lane_state.last_error or "Loading the model description...", icon='ERROR' if lane_state.last_error else 'TIME')
        return
    if schema.prompt_name:
        draw_prompt_row(layout, lane_state, lane)
    draw_references(layout, lane_state, schema)
    params_ui.draw_params(layout, lane_state, schema, locked={"duration"} if (lane == "video" and lane_state.match_timeline) else ())
    if lane == "video":
        draw_clip_options(layout, context, lane_state, schema)
    if lane == "material":
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if meshes:
            layout.label(text=f"Applies to {len(meshes)} selected mesh(es)", icon='MATERIAL')
        else:
            layout.label(text="Select a mesh to apply the material on arrival", icon='INFO')
    if lane == "audio":
        layout.label(text="Results land in the output folder; add them to the sequencer from Generations", icon='INFO')
    draw_generate_row(layout, lane_state, lane)


def draw_edit3d_lane(layout, context):
    """The 3D tab in Edit mode: Scenario's 3D tools on the selected mesh."""
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
    tasks = [t[0] for t in props.EDIT3D_TASK_ITEMS]
    draw_enum_tabs(layout, scene.scenario, "edit3d_task", (tasks[:4], tasks[4:]))  # continuous segmented rows, like the lane tabs
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
        draw_prompt_row(layout, lane_state, "edit3d")
    record = runtime.state.records.get(lane_state.model_id)
    mesh_name = mesh_param(record) if record is not None else None
    draw_references(layout, lane_state, schema, fixed_first={mesh_name: "Selected mesh (exported at generate time)"} if mesh_name else None)
    params_ui.draw_params(layout, lane_state, schema)
    draw_generate_row(layout, lane_state, "3d")  # the operator routes the 3D tab in Edit mode to the edit3d lane


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
    box.label(text="Tools: scene, objects, Python, API help, screenshots, camera path, models, cost, generate, import", icon='INFO')


# -- results ------------------------------------------------------------------

def _short_prompt(rec, limit=40):
    text = (rec.meta.get("prompt") or rec.meta.get("spark_look") or rec.meta.get("look") or "").strip()
    if not text:
        text = rec.meta.get("model_name") or rec.model_id
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _primary_asset(rec):
    for asset_id in rec.asset_ids:
        kind = rec.asset_types.get(asset_id, "")
        if rec.kind == "3d" and "texture" in kind:
            continue
        return asset_id
    return rec.asset_ids[0] if rec.asset_ids else ""


def draw_result(layout, rec):
    """One generation: a header (type icon, prompt start, cost, collapse arrow), then model, asset id and actions.
    Only the output is shown; the inputs and settings live behind Details."""
    collapsed = bool(rec.meta.get("collapsed"))
    box = layout.box()
    header = box.row(align=True)
    toggle = header.operator("scenario.toggle_result", text="", icon='TRIA_RIGHT' if collapsed else 'TRIA_DOWN', emboss=False)
    toggle.local_id = rec.local_id
    header.label(text=_short_prompt(rec), icon=KIND_ICON.get(rec.kind, 'FILE'))
    if not rec.is_success and rec.error:
        # a red error button whose tooltip is the full message, and which opens it in full on click (like the web app)
        header.operator("scenario.error_details", text="", icon='ERROR', emboss=False).local_id = rec.local_id
    elif not rec.is_success:
        header.label(text="", icon='ERROR')
    header.label(text=f"{rec.cu_cost:g} CU" if rec.cu_cost is not None else "")
    if collapsed:
        return
    row = box.row(align=True)
    row.label(text=rec.meta.get("model_name") or rec.model_id, icon='NODE_MATERIAL')
    reload = row.operator("scenario.reload_generation", text="", icon='FILE_REFRESH')
    reload.local_id = rec.local_id
    details = row.operator("scenario.result_details", text="", icon='INFO')
    details.local_id = rec.local_id
    asset_id = _primary_asset(rec)
    if asset_id:
        row = box.row(align=True)
        op = row.operator("scenario.copy_text", text=asset_id, icon='COPYDOWN')
        op.text, op.what = asset_id, "asset id"
        if len(rec.asset_ids) > 1:
            row.label(text=f"+{len(rec.asset_ids) - 1}")
    if rec.error:
        row = box.row(align=True)
        row.alert = not rec.is_success
        row.label(text=("Failed: " if not rec.is_success else "") + rec.error[:60], icon='ERROR')
        row.operator("scenario.error_details", text="", icon='INFO').local_id = rec.local_id  # tooltip = full message; click = full text + copy
    if rec.meta.get("download_errors"):
        box.label(text=f"{len(rec.meta['download_errors'])} file(s) could not be downloaded", icon='ERROR')
    if rec.kind == "image":
        for path in rec.files[:6]:
            icon_id = thumbnail(path)
            row = box.row(align=True)
            if icon_id:
                row.template_icon(icon_value=icon_id, scale=3.0)
            col = row.column(align=True)
            col.operator("scenario.show_image", text="View image", icon='ZOOM_ALL').filepath = path
            col.operator_menu_enum("scenario.use_as_reference", "target", text="Use as reference", icon='IMAGE_REFERENCE').filepath = path
            col.operator("scenario.remove_background", text="Remove background", icon='MOD_MASK').filepath = path
            sub = col.row(align=True)
            sub.operator("scenario.apply_texture", text="Apply as texture").filepath = path
            sub.operator("scenario.add_plane", text="Add as plane").filepath = path
    elif rec.kind == "3d":
        primary = rec.meta.get("primary_mesh") or next((p for p in rec.files if p.lower().endswith(MESH_EXTS)), "")
        if primary:
            row = box.row(align=True)
            add = row.operator("scenario.import_mesh_file", text="Add to scene", icon='IMPORT')
            add.filepath, add.local_id = primary, rec.local_id
            names = "|".join(rec.meta.get("objects") or [])
            sel = row.operator("scenario.select_result_objects", text="Select", icon='RESTRICT_SELECT_OFF')
            sel.names, sel.local_id = names, rec.local_id
            rm = row.operator("scenario.delete_result_objects", text="", icon='TRASH')
            rm.names, rm.local_id = names, rec.local_id
        for alt in rec.meta.get("mesh_alternates") or []:
            row = box.row(align=True)
            row.label(text=os.path.basename(alt)[-40:], icon='FILE_3D')
            add = row.operator("scenario.import_mesh_file", text="Add")
            add.filepath, add.local_id = alt, rec.local_id
    elif rec.kind == "video":
        for path in rec.files[:3]:
            row = box.row(align=True)
            row.operator("scenario.play_video", text="Play", icon='PLAY').filepath = path
            row.operator("scenario.play_video_blender", text="Play in Blender", icon='BLENDER').filepath = path
    elif rec.kind == "audio":
        for path in [p for p in rec.files if p.lower().endswith(AUDIO_EXTS)][:4] or rec.files[:2]:
            row = box.row(align=True)
            row.operator("scenario.play_video", text="Play", icon='PLAY').filepath = path
            row.operator("scenario.add_sound_strip", text="Add to sequencer", icon='SEQUENCE').filepath = path
    elif rec.kind == "material":
        mat_name = rec.meta.get("material_name") or f"Scenario {(rec.meta.get('prompt') or rec.model_id).strip()[:40]}"
        row = box.row(align=True)
        row.label(text="PBR material", icon='MATERIAL')
        if bpy.data.materials.get(mat_name):
            row.operator("scenario.retile_material", text="Tiling", icon='UV').material_name = mat_name
    elif rec.files:
        box.label(text=os.path.basename(rec.files[0]), icon='FILE')


def draw_history(layout, context, shown_ids=()):
    if not runtime.state.history:
        layout.label(text="Press Refresh cloud to list this project's generations", icon='INFO')
        return
    local_by_job = {}
    manager = runtime.state.manager
    if manager is not None:
        local_by_job = {r.job_id: r for r in manager.registry.all() if r.job_id and r.files}
    for entry in runtime.state.history[:24]:
        if entry.job_id in shown_ids:
            continue  # already listed among this session's results
        local = local_by_job.get(entry.job_id)
        if local is not None:
            draw_result(layout, local)  # same entry, same actions as a session result
            continue
        box = layout.box()
        header = box.row()
        header.label(text=(entry.prompt or entry.model_id)[:40], icon=KIND_ICON.get(entry.kind, 'FILE'))
        header.label(text=f"{entry.cu_cost:g} CU" if entry.cu_cost is not None else entry.status)
        if entry.asset_ids:
            op = box.row(align=True).operator("scenario.copy_text", text=entry.asset_ids[0], icon='COPYDOWN')
            op.text, op.what = entry.asset_ids[0], "asset id"
        if entry.local_files and entry.kind == "image":
            icon_id = thumbnail(entry.local_files[0])
            if icon_id:
                box.template_icon(icon_value=icon_id, scale=3.0)
        if entry.is_success:
            op = box.operator("scenario.import_result", text="Download and open", icon='IMPORT')
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
        draw_enum_tabs(layout, scenario, "lane", (("image", "video", "3d"), ("audio", "material"), ("render_image", "render_video")))
        layout.separator(factor=0.5)  # breathing room between the tabs and the lane form
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
        message = runtime.message_visible()
        if message:
            layout.label(text=message[:80])


STATUS_TEXT = {"preparing": "Prompt Spark is writing the look", "submitting": "uploading and submitting", "queued": "queued", "in-progress": "rendering"}


class SCENARIO_PT_jobs(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = ""
    bl_order = 1

    def draw_header(self, context):
        active = sum(1 for r in runtime.state.jobs_view if not r.is_terminal)
        self.layout.label(text="Jobs" if not active else ("1 Job" if active == 1 else f"{active} Jobs"))

    def draw(self, context):
        layout = self.layout
        active = [r for r in runtime.state.jobs_view if not r.is_terminal]
        if not active:
            layout.label(text="No job running", icon='CHECKMARK')
            return
        for rec in active:
            box = layout.box()
            row = box.row(align=True)
            row.label(text=_short_prompt(rec, 44), icon=KIND_ICON.get(rec.kind, 'TIME'))
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
        terminal = [r for r in runtime.state.jobs_view if r.is_terminal]
        if terminal:
            any_open = any(not r.meta.get("collapsed") for r in terminal)
            row.operator("scenario.collapse_results", text="Collapse all" if any_open else "Expand all",
                         icon='FULLSCREEN_EXIT' if any_open else 'FULLSCREEN_ENTER')
        shown, shown_ids = 0, set()
        for rec in runtime.state.jobs_view:
            if not rec.is_terminal:
                continue
            draw_result(layout, rec)
            shown_ids.add(rec.job_id)
            shown += 1
            if shown >= 12:
                break
        if shown == 0:
            layout.label(text="Nothing generated yet in this session")
        layout.separator()
        layout.prop(context.scene.scenario, "show_cloud_history", text="Project history (cloud)", icon='WORLD')
        if context.scene.scenario.show_cloud_history:
            draw_history(layout, context, shown_ids)


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
