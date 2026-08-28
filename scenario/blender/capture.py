# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport and camera captures (stills and playblasts). Main thread only; the real runner needs the GUI."""
import logging
import time
from dataclasses import dataclass

import bpy

from . import runtime
from ..core.scene import capture_plan

log = logging.getLogger("scenario.capture")
_view_context = {"value": True}


def capture_dir():
    path = runtime.paths().cache_dir / "captures"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_capture_path(prefix, ext):
    return str(capture_dir() / f"{prefix}_{int(time.time() * 1000)}.{ext}")


@dataclass
class RenderSettings:
    resolution_x: int
    resolution_y: int
    resolution_percentage: int
    file_format: str
    color_mode: str
    filepath: str
    use_stamp: bool
    frame_start: int
    frame_end: int
    use_preview_range: bool
    ffmpeg_format: str
    ffmpeg_codec: str
    ffmpeg_audio: str
    film_transparent: bool
    camera_name: str
    media_type: str = ""

    @classmethod
    def snapshot(cls, scene):
        r = scene.render
        return cls(r.resolution_x, r.resolution_y, r.resolution_percentage, r.image_settings.file_format, r.image_settings.color_mode,
                   r.filepath, r.use_stamp, scene.frame_start, scene.frame_end, scene.use_preview_range,
                   r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.audio_codec, r.film_transparent, scene.camera.name if scene.camera else "",
                   getattr(r.image_settings, "media_type", ""))

    def restore(self, scene):
        r = scene.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = self.resolution_x, self.resolution_y, self.resolution_percentage
        if self.media_type and hasattr(r.image_settings, "media_type"):
            r.image_settings.media_type = self.media_type
        if self.media_type != 'VIDEO':
            r.image_settings.file_format = self.file_format
        try:
            r.image_settings.color_mode = self.color_mode
        except TypeError:
            pass
        r.filepath, r.use_stamp = self.filepath, self.use_stamp
        scene.frame_start, scene.frame_end, scene.use_preview_range = self.frame_start, self.frame_end, self.use_preview_range
        r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.audio_codec = self.ffmpeg_format, self.ffmpeg_codec, self.ffmpeg_audio
        r.film_transparent = self.film_transparent
        if self.camera_name and bpy.data.objects.get(self.camera_name) is not None:
            scene.camera = bpy.data.objects[self.camera_name]


def set_video_output(render):
    """Blender 4.x uses file_format FFMPEG; 4.5+/5.x use image_settings.media_type VIDEO."""
    settings = render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = 'VIDEO'
    else:
        settings.file_format = 'FFMPEG'


def set_image_output(render, file_format):
    settings = render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = 'IMAGE'
    settings.file_format = file_format


def is_video_output(render):
    settings = render.image_settings
    if hasattr(settings, "media_type"):
        return settings.media_type == 'VIDEO'
    return settings.file_format == 'FFMPEG'


def _view3d(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                return window, area, region
    return None, None, None


def _default_runner(kind, context, scene):
    window, area, region = _view3d(context)
    if window is None:
        raise RuntimeError("No 3D viewport available for the capture")
    with context.temp_override(window=window, area=area, region=region, scene=scene):
        bpy.ops.render.opengl(animation=(kind == "animation"), view_context=_view_context["value"], write_still=(kind == "still"))


class _Overlays:
    """Hide overlays and gizmos (and optionally force solid shading) while a capture runs."""

    def __init__(self, context, force_solid):
        self.spaces = []
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    self.spaces.append(area.spaces.active)
        self.force_solid = force_solid
        self.saved = []

    def __enter__(self):
        for space in self.spaces:
            self.saved.append((space.overlay.show_overlays, space.show_gizmo, space.shading.type, space.shading.color_type))
            space.overlay.show_overlays = False
            space.show_gizmo = False
            if self.force_solid:
                space.shading.type = 'SOLID'
                space.shading.color_type = 'SINGLE'
        return self

    def __exit__(self, *exc):
        for space, (overlays, gizmo, shading, color) in zip(self.spaces, self.saved):
            space.overlay.show_overlays = overlays
            space.show_gizmo = gizmo
            space.shading.type = shading
            space.shading.color_type = color
        return False


def _prepare_source(scene, source, camera):
    if source == 'CAMERA':
        cam = camera or scene.camera or next((o for o in scene.objects if o.type == 'CAMERA'), None)
        if cam is None:
            raise RuntimeError("Camera capture needs a camera in the scene")
        scene.camera = cam
    _view_context["value"] = source != 'CAMERA'


def capture_still(context, path, source='VIEWPORT', camera=None, width=None, height=None, force_solid=False, runner=None):
    scene = context.scene
    saved = RenderSettings.snapshot(scene)
    runner = runner or _default_runner
    try:
        _prepare_source(scene, source, camera)
        r = scene.render
        if width and height:
            r.resolution_x, r.resolution_y = int(width), int(height)
        r.resolution_percentage = 100
        set_image_output(r, 'PNG')
        r.image_settings.color_mode = 'RGB'
        r.use_stamp = False
        r.filepath = str(path)
        with _Overlays(context, force_solid):
            runner("still", context, scene)
        return str(path)
    finally:
        saved.restore(scene)


def capture_playblast(context, path, source='VIEWPORT', camera=None, width=1280, height=720, frame_start=None, frame_end=None, force_solid=False, runner=None):
    scene = context.scene
    saved = RenderSettings.snapshot(scene)
    runner = runner or _default_runner
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    start, end, seconds = capture_plan.frame_span(
        frame_start if frame_start is not None else scene.frame_start, frame_end if frame_end is not None else scene.frame_end, fps,
        use_preview=(frame_start is None and scene.use_preview_range), preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    try:
        _prepare_source(scene, source, camera)
        r = scene.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = int(width), int(height), 100
        set_video_output(r)
        r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.audio_codec = 'MPEG4', 'H264', 'NONE'
        r.use_stamp = False
        scene.use_preview_range = False
        scene.frame_start, scene.frame_end = start, end
        r.filepath = str(path)
        with _Overlays(context, force_solid):
            runner("animation", context, scene)
        return {"path": str(path), "frame_start": start, "frame_end": end, "seconds": seconds, "fps": fps}
    finally:
        saved.restore(scene)


def first_frame_still(context, path, source='VIEWPORT', camera=None, force_solid=False, runner=None):
    scene = context.scene
    current = scene.frame_current
    start = scene.frame_preview_start if scene.use_preview_range else scene.frame_start
    try:
        scene.frame_set(start)
        return capture_still(context, path, source=source, camera=camera, width=1280, height=720, force_solid=force_solid, runner=runner)
    finally:
        scene.frame_set(current)
