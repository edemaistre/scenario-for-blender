# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP tools that read or change the open Blender scene. Every handler runs on the main thread."""
import base64
import tempfile

import bpy

from . import sandbox
from .protocol import ToolSpec


def _vec(v):
    return [round(float(x), 4) for x in v]


def scene_summary(args):
    scene = bpy.context.scene
    objects = []
    for obj in scene.objects:
        objects.append({"name": obj.name, "type": obj.type, "location": _vec(obj.location), "dimensions": _vec(obj.dimensions),
                        "parent": obj.parent.name if obj.parent else None, "collections": [c.name for c in obj.users_collection],
                        "materials": [s.material.name for s in getattr(obj, "material_slots", []) if s.material], "hidden": obj.hide_get()})
    active = bpy.context.view_layer.objects.active
    return {"file": bpy.data.filepath or "(unsaved)", "objects": objects, "active": active.name if active else None,
            "selected": [o.name for o in bpy.context.selected_objects], "cameras": [o.name for o in scene.objects if o.type == 'CAMERA'],
            "scene_camera": scene.camera.name if scene.camera else None, "frame_range": [scene.frame_start, scene.frame_end], "frame_current": scene.frame_current,
            "fps": scene.render.fps / (scene.render.fps_base or 1.0), "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "unit_system": scene.unit_settings.system, "cursor": _vec(scene.cursor.location), "blender": bpy.app.version_string}


def object_detail(args):
    obj = bpy.data.objects.get(args.get("name", ""))
    if obj is None:
        raise ValueError(f"No object named {args.get('name')!r}")
    detail = {"name": obj.name, "type": obj.type, "location": _vec(obj.location), "rotation_euler": _vec(obj.rotation_euler), "scale": _vec(obj.scale),
              "dimensions": _vec(obj.dimensions), "parent": obj.parent.name if obj.parent else None, "modifiers": [m.type for m in getattr(obj, "modifiers", [])],
              "custom_properties": {k: repr(obj[k]) for k in obj.keys() if not k.startswith("_")}}
    if obj.type == 'MESH':
        detail.update({"vertices": len(obj.data.vertices), "faces": len(obj.data.polygons), "uv_layers": [uv.name for uv in obj.data.uv_layers],
                       "materials": [s.material.name if s.material else None for s in obj.material_slots]})
    if obj.type == 'CAMERA':
        detail.update({"lens_mm": obj.data.lens, "sensor_width": obj.data.sensor_width, "clip": [obj.data.clip_start, obj.data.clip_end]})
    return detail


def execute_python(args):
    from .. import prefs as prefs_module

    prefs = prefs_module.get_prefs()
    if prefs is not None and not prefs.mcp_allow_python:
        raise PermissionError("Python execution is disabled in Scenario preferences (MCP > Allow connected agents to run Python)")
    code = args.get("code") or ""
    if not code.strip():
        raise ValueError("code is required")
    return sandbox.run_python(code)


def select_objects(args):
    names = set(args.get("names") or [])
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj.name in names)
    first = next((bpy.data.objects[n] for n in names if n in bpy.data.objects), None)
    if first is not None:
        bpy.context.view_layer.objects.active = first
    return {"selected": sorted(names & set(bpy.data.objects.keys())), "missing": sorted(names - set(bpy.data.objects.keys()))}


def set_frame(args):
    scene = bpy.context.scene
    scene.frame_set(int(args["frame"]))
    return {"frame_current": scene.frame_current}


def _png_content(path):
    with open(path, "rb") as handle:
        return {"_image": base64.b64encode(handle.read()).decode("ascii"), "mimeType": "image/png"}


def screenshot_viewport(args):
    if bpy.app.background:
        raise RuntimeError("Screenshots need the Blender GUI")
    path = tempfile.mktemp(prefix="scenario-shot-", suffix=".png")
    wm = bpy.context.window_manager
    window = wm.windows[0]
    area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        raise RuntimeError("No 3D viewport is open")
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=path)
    return _png_content(path)


def render_still(args):
    from ..blender import capture

    path = tempfile.mktemp(prefix="scenario-render-", suffix=".png")
    capture.capture_still(bpy.context, path, source=args.get("source", 'CAMERA'), width=int(args.get("width", 1280)), height=int(args.get("height", 720)))
    return _png_content(path)


def camera_path(args):
    """Build an animated camera for the Render Video lane: from explicit waypoints, or from a preset around the subject."""
    from ..blender import shot_planner
    from ..core.scene import shot_plan

    context = bpy.context
    scene = context.scene
    props = scene.scenario_shot
    if args.get("preset"):
        resolve = getattr(shot_plan, "resolve_preset", None)
        preset = resolve(args["preset"]) if resolve else args["preset"]
        if preset not in shot_plan.PRESETS or (resolve and args["preset"] not in shot_plan.PRESETS and args["preset"] not in getattr(shot_plan, "PRESET_ALIASES", {})):
            raise ValueError(f"preset must be one of {sorted(shot_plan.PRESETS)}")
        props.preset = preset
    if args.get("duration") is not None:
        props.duration = float(args["duration"])
    if args.get("focal") is not None:
        props.focal = float(args["focal"])
    if args.get("aim_at_subject") is not None:
        props.aim_at_subject = bool(args["aim_at_subject"])
    if args.get("description"):
        plan = shot_plan.plan_from_text(args["description"])
        props.preset, props.duration, props.focal = plan["preset"], plan["duration"], plan["focal"]
    waypoints = args.get("waypoints") or []
    if waypoints:
        shot_planner.clear_markers(scene)
        for wp in waypoints:
            position = wp.get("position")
            if not position or len(position) != 3:
                raise ValueError("each waypoint needs position: [x, y, z]")
            rotation = wp.get("rotation_euler")
            shot_planner.add_marker(context, tuple(float(v) for v in position), rotation=tuple(rotation) if rotation else None,
                                    focal=wp.get("focal"), hold=float(wp.get("hold") or 0.0))
    camera, keyframes, last_frame = shot_planner.build_path(context)
    return {"camera": camera.name, "keyframes": keyframes, "frame_start": scene.frame_start, "frame_end": last_frame,
            "preset": props.preset, "duration": props.duration, "focal": props.focal, "markers": len(shot_planner.marker_objects(scene)),
            "note": "The scene camera now follows this path; Render Video (Camera clip) records it."}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


SPECS = (
    ToolSpec("scene_summary", "Objects, cameras, frame range, fps, selection and cursor of the open Blender scene.", _schema({}), scene_summary, {"readOnlyHint": True}),
    ToolSpec("object_detail", "Transform, mesh statistics, materials and custom properties of one object.", _schema({"name": {"type": "string"}}, ["name"]), object_detail, {"readOnlyHint": True}),
    ToolSpec("execute_python", "Run Python with bpy in this Blender (main thread). Fill the result dict to return data; stdout and stderr are captured. Disabled when the user turned it off in preferences.",
             _schema({"code": {"type": "string", "description": "Python source. bpy and result = {} are preloaded."}}, ["code"]), execute_python, {"destructiveHint": True}),
    ToolSpec("select_objects", "Select the named objects and make the first one active.", _schema({"names": {"type": "array", "items": {"type": "string"}}}, ["names"]), select_objects),
    ToolSpec("set_frame", "Jump the timeline to a frame.", _schema({"frame": {"type": "integer"}}, ["frame"]), set_frame),
    ToolSpec("screenshot_viewport", "PNG screenshot of the 3D viewport area as the user sees it (GUI only).", _schema({}), screenshot_viewport, {"readOnlyHint": True}),
    ToolSpec("camera_path", "Animate a camera around the scene for Render Video: a preset (orbit, push_in, pull_back, crane, pan, flyover) around the subject, a free-text description, or explicit waypoints.",
             _schema({"preset": {"type": "string"}, "duration": {"type": "number", "description": "seconds"}, "focal": {"type": "number", "description": "mm"},
                      "aim_at_subject": {"type": "boolean"}, "description": {"type": "string", "description": "e.g. 'slow orbit, 8 s, 35mm'"},
                      "waypoints": {"type": "array", "items": {"type": "object", "properties": {"position": {"type": "array", "items": {"type": "number"}}, "rotation_euler": {"type": "array", "items": {"type": "number"}},
                                                                                              "focal": {"type": "number"}, "hold": {"type": "number"}}}}}), camera_path),
    ToolSpec("render_still", "Quick OpenGL still of the scene camera (or the viewport) as PNG, default 1280x720 (GUI only).",
             _schema({"source": {"type": "string", "enum": ["CAMERA", "VIEWPORT"]}, "width": {"type": "integer"}, "height": {"type": "integer"}}), render_still, {"readOnlyHint": True}),
)
