# Scenario for Blender P2 Implementation Plan (Render-to-real + Video lane)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the viewport or the scene camera as stills and playblasts, feed them to Scenario models, and ship the two-step render-to-real flow (concept still, then Seedance video) plus a generic Video lane with match-timeline duration and Blender-input references.

**Architecture:** Pure planning in `scenario/core/scene/capture_plan.py` (frame range to seconds, duration choice against a model's allowed values, prompt tagging for Seedance). Blender capture in `scenario/blender/capture.py` (main thread, `render.opengl` still and animation with temporary render settings, restored in `finally`). Captures happen at submit time inside `generation.submit_generation`, never during estimates. Video results are handled by `apply_video.py` (Play with the OS player or Blender's player). The `render` lane gets its own panel with two steps and remembers the concept image on the lane state.

**Tech Stack:** same as P0/P1. `render.opengl` and `gpu` are GUI-only, so headless tests use an injected runner; GUI checks go through `tools/gui_screenshot.py` extended with a capture action.

**Spec:** `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md` (sections 3.1 `capture.py`/`video.py`, 4 Video and Render-to-real)

## Global Constraints

Same as the P0 plan, plus:
- Seedance 2.0 contract (fixture `tests/fixtures/models/model_bytedance-seedance-2-0.json`): `prompt` optional, `referenceVideos` (file_array, max 3), `referenceImages` (file_array, max 9), mutually exclusive with `image` (first frame); `duration` allowed `[-1, 4..15]` where -1 bills the longest reference clip; `resolution` 480p/720p/1080p/4k; `generateAudio`.
- Playblasts: 1280x720 H.264 MP4, overlays and gizmos hidden, stamps off; duration = scene frame range (preview range wins) clamped to the model's limits; always restore the user's render settings.
- Captures are written under `paths.cache_dir / "captures"` and uploaded like files; never inside the .blend folder unless the user changes the output folder.
- Branch `p2-render-to-real-video`, merge `--no-ff` into `main` at the end. Smoke spend for P2: at most one Seedance 2.0 run at 480p / 4 s / no audio, and only if its dry run is at most 150 CU.

---

### Task 19: Capture plan (pure Python)

**Files:**
- Create: `scenario/core/scene/capture_plan.py`
- Test: `tests/unit/test_capture_plan.py`

**Interfaces:**
- Produces: `frame_span(frame_start, frame_end, fps, use_preview=False, preview_start=None, preview_end=None) -> (start, end, seconds)`; `choose_duration(seconds, allowed_values, minimum=None) -> (value, note)` where allowed may contain -1 (auto) and integers, picks the smallest allowed value >= ceil(seconds), clamps to the max with a note, returns -1 when only auto is allowed; `clip_frames_for(seconds_limit, fps, start, end) -> (start, end)` trims the range to the limit; `tag_prompt(prompt, has_video, has_image) -> str` prepends `@video1`/`@image1` mentions when missing; `PLAYBLAST_PREFIX`, `CINEMATIC_SUFFIX` constants; `render_to_real_prompt(user_prompt, force_clay=True) -> str`.

- [ ] **Step 1: Failing tests**

`tests/unit/test_capture_plan.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import capture_plan as cp


def test_frame_span_uses_preview_range_when_asked():
    assert cp.frame_span(1, 250, 24) == (1, 250, 250 / 24)
    assert cp.frame_span(1, 250, 24, use_preview=True, preview_start=10, preview_end=57) == (10, 57, 48 / 24)


def test_choose_duration_rounds_up_and_clamps():
    allowed = (-1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
    assert cp.choose_duration(2.0, allowed) == (4, "padded to the 4 s minimum")
    assert cp.choose_duration(6.2, allowed) == (7, "")
    assert cp.choose_duration(40.0, allowed) == (15, "trimmed to the 15 s maximum")
    assert cp.choose_duration(5.0, (-1,)) == (-1, "")


def test_clip_frames_for_limit():
    assert cp.clip_frames_for(15, 24, 1, 1000) == (1, 360)
    assert cp.clip_frames_for(15, 24, 1, 100) == (1, 100)


def test_tag_prompt_adds_missing_mentions_once():
    assert cp.tag_prompt("a wolf running", True, True).startswith("@video1 @image1 ")
    assert cp.tag_prompt("use @image1 as style", False, True) == "use @image1 as style"
    assert cp.tag_prompt("", True, False) == "@video1"


def test_render_to_real_prompt_wraps_user_text():
    text = cp.render_to_real_prompt("cyborg wolf in a ruined city")
    assert text.startswith("@video1 @image1 ")
    assert "grayscale playblast" in text and "cyborg wolf in a ruined city" in text
    assert text.rstrip().endswith(cp.CINEMATIC_SUFFIX)
```

- [ ] **Step 2: Implement**

`scenario/core/scene/capture_plan.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Frame ranges, clip durations and Seedance prompt tagging. No bpy."""
import math

PLAYBLAST_PREFIX = ("The video @video1 is a grayscale playblast animation exported from Blender: keep its camera move, "
                    "timing, character motion and framing exactly, and render it in the style of @image1.")
CINEMATIC_SUFFIX = "Cinematic lighting, physically plausible materials, coherent shadows, no text or watermark."


def frame_span(frame_start, frame_end, fps, use_preview=False, preview_start=None, preview_end=None):
    start, end = frame_start, frame_end
    if use_preview and preview_start is not None and preview_end is not None:
        start, end = preview_start, preview_end
    frames = max(1, end - start + 1)
    return start, end, frames / float(fps or 24)


def choose_duration(seconds, allowed_values, minimum=None):
    numeric = sorted(int(v) for v in allowed_values if isinstance(v, (int, float)) and int(v) > 0)
    if not numeric:
        return (-1 if -1 in allowed_values else None), ""
    needed = max(1, math.ceil(seconds - 1e-6))
    for value in numeric:
        if value >= needed:
            note = f"padded to the {value} s minimum" if value > needed else ""
            return value, note
    return numeric[-1], f"trimmed to the {numeric[-1]} s maximum"


def clip_frames_for(seconds_limit, fps, start, end):
    max_frames = int(seconds_limit * (fps or 24))
    if end - start + 1 > max_frames:
        end = start + max_frames - 1
    return start, end


def tag_prompt(prompt, has_video, has_image):
    prompt = (prompt or "").strip()
    tags = []
    if has_video and "@video1" not in prompt:
        tags.append("@video1")
    if has_image and "@image1" not in prompt:
        tags.append("@image1")
    return (" ".join(tags) + (" " if prompt and tags else "") + prompt).strip()


def render_to_real_prompt(user_prompt, force_clay=True):
    body = (user_prompt or "").strip()
    parts = [PLAYBLAST_PREFIX]
    if body:
        parts.append(body)
    parts.append(CINEMATIC_SUFFIX)
    return tag_prompt(" ".join(parts), True, True)
```

Run `python3 -m pytest tests/unit/test_capture_plan.py -v` (5 passed), commit `feat(core): capture plan (frame spans, durations, Seedance prompt tagging)`.

---

### Task 20: Blender capture (stills and playblasts) with restored settings

**Files:**
- Create: `scenario/blender/capture.py`
- Test: `tests/blender/test_capture.py`

**Interfaces:**
- Produces: `capture.RenderSettings.snapshot(scene) -> RenderSettings` and `.restore(scene)`; `capture.capture_still(context, path, source='VIEWPORT', camera=None, width=None, height=None, runner=None) -> str`; `capture.capture_playblast(context, path, source='VIEWPORT', camera=None, width=1280, height=720, frame_start=None, frame_end=None, force_solid=False, runner=None) -> dict(path, frame_start, frame_end, seconds, fps)`; `capture.first_frame_still(context, path, ...)`; `capture.capture_dir() -> Path`. `runner(kind, context, scene)` is the injectable call that performs `bpy.ops.render.opengl(...)`; the default runner uses a `temp_override` on the first VIEW_3D area and `view_context = (source == 'VIEWPORT')`.

- [ ] **Step 1: Failing headless test** (`render.opengl` cannot run headless, so the runner is faked and the test checks settings, paths and restoration)

`tests/blender/test_capture.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

import bpy

from helpers import reset_scene, submodule


class CaptureTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.capture = submodule("blender.capture")
        self.tmp = Path(tempfile.mkdtemp(prefix="scenario-cap-"))
        self.calls = []

    def fake_runner(self, kind, context, scene):
        r = scene.render
        self.calls.append({"kind": kind, "res": (r.resolution_x, r.resolution_y, r.resolution_percentage), "fmt": r.image_settings.file_format,
                           "path": r.filepath, "range": (scene.frame_start, scene.frame_end), "stamp": r.use_stamp})
        Path(bpy.path.abspath(r.filepath)).parent.mkdir(parents=True, exist_ok=True)
        if kind == "animation":
            Path(bpy.path.abspath(r.filepath)).write_bytes(b"mp4")
        else:
            Path(bpy.path.abspath(r.filepath)).write_bytes(b"png")

    def test_playblast_sets_720p_h264_and_restores_everything(self):
        scene = bpy.context.scene
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1920, 1080, 50
        scene.render.use_stamp = True
        scene.frame_start, scene.frame_end = 1, 48
        scene.render.filepath = "//renders/"
        out = self.tmp / "clip.mp4"
        info = self.capture.capture_playblast(bpy.context, str(out), source='VIEWPORT', frame_start=1, frame_end=24, runner=self.fake_runner)
        call = self.calls[0]
        self.assertEqual(call["kind"], "animation")
        self.assertEqual(call["res"], (1280, 720, 100))
        self.assertEqual(call["fmt"], 'FFMPEG')
        self.assertFalse(call["stamp"])
        self.assertEqual(call["range"], (1, 24))
        self.assertEqual(info["frame_start"], 1)
        self.assertEqual(info["frame_end"], 24)
        self.assertAlmostEqual(info["seconds"], 24 / scene.render.fps * scene.render.fps_base, places=3)
        self.assertTrue(out.exists())
        self.assertEqual((scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage), (1920, 1080, 50))
        self.assertTrue(scene.render.use_stamp)
        self.assertEqual((scene.frame_start, scene.frame_end), (1, 48))
        self.assertEqual(scene.render.filepath, "//renders/")

    def test_still_uses_png_and_camera_source_requires_camera(self):
        out = self.tmp / "still.png"
        path = self.capture.capture_still(bpy.context, str(out), source='CAMERA', runner=self.fake_runner)
        self.assertEqual(self.calls[0]["kind"], "still")
        self.assertEqual(self.calls[0]["fmt"], 'PNG')
        self.assertTrue(Path(path).exists())
        for obj in list(bpy.data.objects):
            if obj.type == 'CAMERA':
                bpy.data.objects.remove(obj)
        with self.assertRaises(RuntimeError):
            self.capture.capture_still(bpy.context, str(self.tmp / "x.png"), source='CAMERA', runner=self.fake_runner)

    def test_capture_dir_is_under_cache(self):
        self.assertTrue(str(self.capture.capture_dir()).endswith("captures"))
```

- [ ] **Step 2: Implement**

`scenario/blender/capture.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport and camera captures (stills and playblasts). Main thread only; GUI only for the real runner."""
import logging
import time
from dataclasses import dataclass

import bpy

from . import runtime
from ..core.scene import capture_plan

log = logging.getLogger("scenario.capture")


def capture_dir():
    path = runtime.paths().cache_dir / "captures"
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    @classmethod
    def snapshot(cls, scene):
        r = scene.render
        return cls(r.resolution_x, r.resolution_y, r.resolution_percentage, r.image_settings.file_format, r.image_settings.color_mode,
                   r.filepath, r.use_stamp, scene.frame_start, scene.frame_end, scene.use_preview_range,
                   r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.audio_codec, r.film_transparent)

    def restore(self, scene):
        r = scene.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = self.resolution_x, self.resolution_y, self.resolution_percentage
        r.image_settings.file_format = self.file_format
        try:
            r.image_settings.color_mode = self.color_mode
        except TypeError:
            pass
        r.filepath, r.use_stamp = self.filepath, self.use_stamp
        scene.frame_start, scene.frame_end, scene.use_preview_range = self.frame_start, self.frame_end, self.use_preview_range
        r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.audio_codec = self.ffmpeg_format, self.ffmpeg_codec, self.ffmpeg_audio
        r.film_transparent = self.film_transparent


def _view3d(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                return window, area, region
    return None, None, None


def _default_runner(kind, context, scene):
    window, area, region = _view3d(context)
    view_context = getattr(scene, "_scenario_view_context", True)
    if window is None:
        raise RuntimeError("No 3D viewport available for the capture")
    with context.temp_override(window=window, area=area, region=region, scene=scene):
        bpy.ops.render.opengl(animation=(kind == "animation"), view_context=view_context, write_still=(kind == "still"))


class _Overlays:
    """Hide overlays and gizmos (and optionally force solid shading) for the duration of a capture."""

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


def _prepare_source(context, scene, source, camera):
    if source == 'CAMERA':
        cam = camera or scene.camera or next((o for o in scene.objects if o.type == 'CAMERA'), None)
        if cam is None:
            raise RuntimeError("Camera capture needs a camera in the scene")
        scene.camera = cam
    scene._scenario_view_context = source != 'CAMERA'


def capture_still(context, path, source='VIEWPORT', camera=None, width=None, height=None, force_solid=False, runner=None):
    scene = context.scene
    saved = RenderSettings.snapshot(scene)
    runner = runner or _default_runner
    try:
        _prepare_source(context, scene, source, camera)
        r = scene.render
        if width and height:
            r.resolution_x, r.resolution_y = int(width), int(height)
        r.resolution_percentage = 100
        r.image_settings.file_format = 'PNG'
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
        _prepare_source(context, scene, source, camera)
        r = scene.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = int(width), int(height), 100
        r.image_settings.file_format = 'FFMPEG'
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


def new_capture_path(prefix, ext):
    return str(capture_dir() / f"{prefix}_{int(time.time() * 1000)}.{ext}")
```

Note: `render.opengl(animation=True)` writes the file itself using `scene.render.filepath`; with FFMPEG the container is appended only when the path has no extension, so pass a full path ending in `.mp4`. Verify in the GUI step that the exact file exists; if Blender appends a frame range suffix, set `r.filepath` to the path without extension and rename the produced file to `path` after the runner call.

Run `./tools/install_dev.sh && make test-blender` (32 tests OK), commit `feat(blender): viewport and camera captures with restored render settings`.

- [ ] **Step 3: GUI proof of a real capture**

Extend `tools/gui_screenshot.py` with an optional action `capture` (5th argument): when present, `_prepare` calls `capture.capture_playblast(bpy.context, str(out_dir/"gui_playblast.mp4"), frame_start=1, frame_end=12)` and `capture.capture_still(bpy.context, str(out_dir/"gui_still.png"))`, printing file sizes. Run: `blender tools/blank.blend --python tools/gui_screenshot.py -- ~/Developer/scratch/playwright-screenshots/scenario-blender/p2-capture.png video 14 "" capture` and check that both files exist with non-zero size (fix the extension handling if the MP4 landed under a different name).

---

### Task 21: Reference sources for captures and the Video lane

**Files:**
- Modify: `scenario/blender/props.py` (REFERENCE_SOURCES adds `VIEWPORT_CLIP`, `CAMERA_CLIP`; lane state gets `match_timeline: BoolProperty(default=True)`, `capture_camera: PointerProperty(type=bpy.types.Object, poll=camera only)`, `force_solid: BoolProperty`)
- Modify: `scenario/blender/generation.py` (`build_request` records pending captures; new `perform_captures(context, request)` runs them on the main thread at submit; `submit_generation` calls it; `apply_match_timeline(scene, lane_state, schema)` sets the `duration` param from the frame range using `capture_plan.choose_duration`; Seedance prompt tagging via `capture_plan.tag_prompt` when references exist)
- Modify: `scenario/blender/panels.py` (Video lane enabled in `GENERATE_LANES`; video-kind file specs offer clip sources; Match timeline toggle and a "Clip: frames a to b, N.N s at 720p" hint; camera picker when a camera source is chosen)
- Modify: `scenario/blender/operators.py` (`scenario.add_reference` accepts the new sources)
- Create: `scenario/blender/apply_video.py` (`on_video_result(rec)`: message + remember path; operators `scenario.play_video(filepath)` using `bpy.ops.wm.path_open`, `scenario.play_video_blender(filepath)` spawning `[bpy.app.binary_path, "-a", filepath]`)
- Modify: `scenario/blender/handlers.py` (`RESULT_HANDLERS["video"]`), `scenario/blender/panels.py` Results rows for videos (Play, Play in Blender, Open folder)
- Test: `tests/blender/test_video_lane.py`

**Interfaces:**
- `generation.Request` gains `captures: list[dict]` where each dict is `{"param": name, "source": 'VIEWPORT'|'CAMERA'|'VIEWPORT_CLIP'|'CAMERA_CLIP', "camera": name or None}`; `generation.perform_captures(context, request, runner=None)` turns them into files in `request.files` (stills for image params, playblasts for video params, honouring `match_timeline` frame clamping from the chosen `duration`).
- `generation.apply_match_timeline(scene, lane_state, schema)` returns `(value, note, seconds)` or `None` when the schema has no `duration` spec.

- [ ] **Step 1: Failing headless test**

`tests/blender/test_video_lane.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest
from pathlib import Path

import bpy

from helpers import FIXTURES, reset_scene, submodule


class VideoLaneTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        data = json.loads((FIXTURES / "models" / "model_bytedance-seedance-2-0.json").read_text())["model"]
        rec = catalog.ModelRecord.from_api(data)
        handlers.dispatch(("catalog", {"privacy": "public", "records": [rec], "detailed": [rec]}))
        self.scene = bpy.context.scene
        self.scene.scenario.lane = "video"
        self.lane = self.scene.scenario.lane_state("video")

    def test_match_timeline_sets_duration_from_frame_range(self):
        self.scene.frame_start, self.scene.frame_end = 1, 150  # 6.25 s at 24 fps
        self.scene.render.fps, self.scene.render.fps_base = 24, 1.0
        schema = self.generation.schema_for(self.lane.model_id)
        value, note, seconds = self.generation.apply_match_timeline(self.scene, self.lane, schema)
        self.assertEqual(value, 7)
        self.assertAlmostEqual(seconds, 6.25, places=3)
        self.assertEqual(self.lane.params["duration"].enum_value, "7")
        self.assertTrue(self.lane.params["duration"].enabled)

    def test_clip_reference_becomes_a_pending_capture_then_a_file(self):
        ref = self.lane.references.add()
        ref.param_name, ref.source = "referenceVideos", 'VIEWPORT_CLIP'
        self.lane.prompt = "a wolf running"
        request = self.generation.build_request(self.scene, "video")
        self.assertEqual(request.captures, [{"param": "referenceVideos", "source": 'VIEWPORT_CLIP', "camera": None}])
        self.assertEqual(request.errors, [])
        made = []

        def runner(kind, context, scene):
            made.append(kind)
            Path(bpy.path.abspath(scene.render.filepath)).parent.mkdir(parents=True, exist_ok=True)
            Path(bpy.path.abspath(scene.render.filepath)).write_bytes(b"mp4")

        self.generation.perform_captures(bpy.context, request, runner=runner)
        self.assertEqual(made, ["animation"])
        self.assertEqual(len(request.files["referenceVideos"]), 1)
        self.assertTrue(request.files["referenceVideos"][0].endswith(".mp4"))
        self.assertTrue(request.body["prompt"].startswith("@video1"))

    def test_estimate_skips_captures_and_marks_partial(self):
        ref = self.lane.references.add()
        ref.param_name, ref.source = "referenceVideos", 'CAMERA_CLIP'
        request = self.generation.build_request(self.scene, "video", for_estimate=True)
        self.assertTrue(request.partial)
        self.assertNotIn("referenceVideos", request.body)
```

- [ ] **Step 2: Implement** (key code; keep everything else as in P0/P1)

In `props.py`:
```python
REFERENCE_SOURCES = [
    ('FILE', "File", "An image or video file on disk"),
    ('VIEWPORT', "Viewport still", "Capture the active 3D viewport as an image at generate time"),
    ('CAMERA', "Camera still", "Render the scene camera view as an image at generate time"),
    ('VIEWPORT_CLIP', "Viewport clip", "Playblast the active viewport over the timeline at generate time"),
    ('CAMERA_CLIP', "Camera clip", "Playblast the scene camera over the timeline at generate time"),
    ('RENDER', "Render Result", "The latest render result"),
    ('ASSET', "Scenario asset", "An asset already in your Scenario project"),
]
CAPTURE_SOURCES = ('VIEWPORT', 'CAMERA', 'VIEWPORT_CLIP', 'CAMERA_CLIP')
CLIP_SOURCES = ('VIEWPORT_CLIP', 'CAMERA_CLIP')
```
and on `ScenarioLaneState`:
```python
    match_timeline: BoolProperty(name="Match timeline", default=True, description="Set the clip duration from the scene frame range", update=_on_prompt_update)
    force_solid: BoolProperty(name="Grey clay capture", default=False, description="Capture with solid single-colour shading so the model reads motion, not materials")
    concept_path: StringProperty()  # render-to-real: last concept image
    concept_job: StringProperty()
```
(`capture_camera` as `PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')` on the lane state.)

In `generation.py`:
```python
def _video_reference_specs(schema):
    return [s for s in schema.specs if s.is_file and s.kind == "video"]


def apply_match_timeline(scene, lane_state, schema):
    spec = schema.by_name("duration")
    if spec is None or not spec.allowed_values or not lane_state.match_timeline:
        return None
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    _, _, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                            preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    value, note = capture_plan.choose_duration(seconds, spec.allowed_values)
    index = lane_state.params.find("duration")
    if index >= 0 and value is not None:
        item = lane_state.params[index]
        item.enum_value = str(value)
        item.enabled = True
    return value, note, seconds
```
In `build_request`, for each file spec and each reference: `if ref.source in props.CAPTURE_SOURCES: captures.append({"param": spec.name, "source": ref.source, "camera": ref.label or None})` (the camera name is stored in `ref.label` when a camera picker is used; None means the scene camera). Estimates: `partial = partial or bool(captures)`. Before building the body for a lane whose schema has `duration`, call `apply_match_timeline` when `lane_state.match_timeline`. After building the body, if the model id contains `seedance` and (video refs or image refs are present or pending), set `body[schema.prompt_name] = capture_plan.tag_prompt(body.get(prompt) , has_video, has_image)`.

```python
def perform_captures(context, request, runner=None):
    from . import capture

    scene = context.scene
    lane_state = scene.scenario.lane_state(request.lane)
    schema = schema_for(request.model_id)
    limit = None
    duration_spec = schema.by_name("duration") if schema else None
    chosen = request.body.get("duration")
    if isinstance(chosen, int) and chosen > 0:
        limit = chosen
    elif duration_spec and duration_spec.allowed_values:
        numeric = [int(v) for v in duration_spec.allowed_values if isinstance(v, (int, float)) and int(v) > 0]
        limit = max(numeric) if numeric else None
    for cap in request.captures:
        source = cap["source"]
        camera = bpy.data.objects.get(cap["camera"]) if cap.get("camera") else None
        base = 'CAMERA' if source.startswith('CAMERA') else 'VIEWPORT'
        if source in props.CLIP_SOURCES:
            fps = scene.render.fps / (scene.render.fps_base or 1.0)
            start, end, _ = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                    preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
            if limit:
                start, end = capture_plan.clip_frames_for(limit, fps, start, end)
            path = capture.new_capture_path("playblast", "mp4")
            info = capture.capture_playblast(context, path, source=base, camera=camera, frame_start=start, frame_end=end, force_solid=lane_state.force_solid, runner=runner)
            request.files.setdefault(cap["param"], []).append(info["path"])
        else:
            path = capture.new_capture_path("still", "png")
            request.files.setdefault(cap["param"], []).append(capture.capture_still(context, path, source=base, camera=camera, force_solid=lane_state.force_solid, runner=runner))
    request.captures = []
    return request
```
`submit_generation` calls `perform_captures(context, request)` right after `build_request` and before `manager.submit`.

`apply_video.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Video results: remember the file, offer playback."""
import subprocess

import bpy

from . import runtime


def on_video_result(rec):
    if rec.files:
        runtime.set_message(f"Video ready: {rec.files[0]}")
    return list(rec.files)


def play_with_os(path):
    bpy.ops.wm.path_open(filepath=path)


def play_with_blender(path):
    subprocess.Popen([bpy.app.binary_path, "-a", path])
```
Operators `SCENARIO_OT_play_video` (`filepath`) and `SCENARIO_OT_play_video_blender` call these. Panel Results rows: for `rec.kind == "video"` show `Play` and `Play in Blender`. Video lane panel: references with kind video draw the clip sources menu (`operator_menu_enum` already lists every source; that is acceptable for P2), plus `layout.prop(lane_state, "match_timeline")`, `layout.prop(lane_state, "force_solid")`, and the hint `Clip: frames {start} to {end}, {seconds:.1f} s at 720p` computed from `capture_plan.frame_span`.

Run `./tools/install_dev.sh && make test-blender` (35 OK), commit `feat(blender): Video lane with capture references, match-timeline duration and playback`.

---

### Task 22: Render-to-real panel (concept still, then Seedance video)

**Files:**
- Create: `scenario/blender/render_to_real.py` (`draw_render_lane(layout, context)`, `submit_concept(context)`, `submit_video(context)`, `on_result(rec)` hook that stores `concept_path` when `rec.meta["render_step"] == "concept"`)
- Modify: `scenario/blender/operators.py` (`scenario.render_concept`, `scenario.render_video`, `scenario.render_use_concept(filepath)`), `scenario/blender/panels.py` (route `render` lane), `scenario/blender/handlers.py` (call `render_to_real.on_result` on `job_done`)
- Test: `tests/blender/test_render_to_real.py`

**Interfaces:**
- `render_to_real.CONCEPT_MODELS = ("model_google-gemini-3-1-flash", "model_openai-gpt-image-2")`, `render_to_real.VIDEO_MODEL = "model_bytedance-seedance-2-0"`.
- `render_to_real.concept_request(context) -> generation.Request` (image kind, model = first available concept model, references: viewport or camera still + optional style files from the `render` lane references, prompt = lane prompt); `render_to_real.video_request(context) -> generation.Request` (Seedance 2.0, `referenceVideos` = playblast capture, `referenceImages` = `[concept_path]` when set, prompt = `capture_plan.render_to_real_prompt(lane.prompt)`, `duration` from match timeline, `resolution` 720p default, `generateAudio` from the lane param).
- The `render` lane state stores: `prompt` (style prompt), `concept_path`, `concept_job`, `force_solid` (default True here), `capture_source` (`VIEWPORT`/`CAMERA`), `references` for style images (param `styleImages`, virtual: mapped to the concept model's `referenceImages`).

- [ ] **Step 1: Failing headless test**

`tests/blender/test_render_to_real.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class RenderToRealTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.rtr = submodule("blender.render_to_real")
        self.runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        records = [catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{n}.json").read_text())["model"])
                   for n in ("model_google-gemini-3-1-flash", "model_bytedance-seedance-2-0")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        self.scene = bpy.context.scene
        self.lane = self.scene.scenario.lane_state("render")
        self.lane.prompt = "cyborg wolf in a ruined city"

    def test_concept_request_uses_a_viewport_still_and_the_style_prompt(self):
        request = self.rtr.concept_request(bpy.context)
        self.assertEqual(request.model_id, "model_google-gemini-3-1-flash")
        self.assertEqual(request.kind, "image")
        self.assertEqual(request.captures[0]["param"], "referenceImages")
        self.assertIn("cyborg wolf", request.body["prompt"])
        self.assertEqual(request.errors, [])

    def test_video_request_wraps_prompt_and_uses_concept_and_playblast(self):
        self.lane.concept_path = str(FIXTURES / "patina-copper-512" / "albedo.png")
        self.scene.frame_start, self.scene.frame_end = 1, 96
        request = self.rtr.video_request(bpy.context)
        self.assertEqual(request.model_id, "model_bytedance-seedance-2-0")
        self.assertEqual(request.kind, "video")
        self.assertEqual(request.captures[0]["param"], "referenceVideos")
        self.assertEqual(request.files["referenceImages"], [self.lane.concept_path])
        self.assertTrue(request.body["prompt"].startswith("@video1 @image1"))
        self.assertIn("grayscale playblast", request.body["prompt"])
        self.assertEqual(request.body["duration"], 4)
        self.assertEqual(request.errors, [])

    def test_concept_result_is_remembered_on_the_lane(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="render", kind="image", model_id="model_google-gemini-3-1-flash", body={}, meta={"render_step": "concept"})
        rec.files = [str(FIXTURES / "patina-copper-512" / "albedo.png")]
        rec.status = "success"
        self.rtr.on_result(rec)
        self.assertEqual(self.lane.concept_path, rec.files[0])
```

- [ ] **Step 2: Implement** `scenario/blender/render_to_real.py`

```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render-to-real: a styled concept still from the viewport, then a Seedance video from the playblast."""
import bpy

from . import generation, props, runtime
from ..core.api.errors import ScenarioError
from ..core.schema.params import build_body, parse_schema
from ..core.scene import capture_plan

CONCEPT_MODELS = ("model_google-gemini-3-1-flash", "model_openai-gpt-image-2")
VIDEO_MODEL = "model_bytedance-seedance-2-0"
CONCEPT_PROMPT_SUFFIX = "Keep the composition, camera angle and silhouettes of the reference render exactly; only change the look."


def _record(model_ids):
    for model_id in model_ids:
        record = runtime.state.records.get(model_id)
        if record is not None and record.parameters:
            return record
    for model_id in model_ids:
        try:
            return generation.ensure_record(model_id)
        except ScenarioError:
            continue
    return None


def _capture_source(lane_state):
    return 'CAMERA' if getattr(lane_state, "capture_source", 'VIEWPORT') == 'CAMERA' else 'VIEWPORT'


def concept_request(context):
    scene = context.scene
    lane = scene.scenario.lane_state("render")
    record = _record(CONCEPT_MODELS)
    if record is None:
        return generation.Request("render", "image", "", {}, errors=["Concept model not available"])
    schema = parse_schema(record)
    refs = schema.by_name("referenceImages") or next((s for s in schema.specs if s.is_file and s.kind == "image"), None)
    if refs is None:
        return generation.Request("render", "image", record.id, {}, errors=["Concept model takes no reference image"])
    prompt = f"{lane.prompt.strip()}. {CONCEPT_PROMPT_SUFFIX}" if lane.prompt.strip() else CONCEPT_PROMPT_SUFFIX
    body = build_body(schema.specs, {schema.prompt_name: prompt, "resolution": "1K"}, files={})
    files = {refs.name: [bpy.path.abspath(r.filepath) for r in lane.references if r.source == 'FILE' and r.filepath]}
    if not files[refs.name]:
        files.pop(refs.name)
    request = generation.Request("render", "image", record.id, body, files, {refs.name} if refs.ptype == "file_array" else set(), [])
    request.captures = [{"param": refs.name, "source": _capture_source(lane), "camera": None}]
    return request


def video_request(context):
    scene = context.scene
    lane = scene.scenario.lane_state("render")
    record = _record((VIDEO_MODEL,))
    if record is None:
        return generation.Request("render", "video", VIDEO_MODEL, {}, errors=["Seedance 2.0 not available"])
    schema = parse_schema(record)
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    _, _, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                            preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    duration_spec = schema.by_name("duration")
    duration, note = capture_plan.choose_duration(seconds, duration_spec.allowed_values if duration_spec else (-1,))
    values = {schema.prompt_name: capture_plan.render_to_real_prompt(lane.prompt), "duration": duration, "resolution": "720p",
              "generateAudio": bool(getattr(lane, "generate_audio", False))}
    files = {}
    if lane.concept_path:
        files["referenceImages"] = [lane.concept_path]
    body = build_body(schema.specs, values, files={})
    request = generation.Request("render", "video", record.id, body, files, {"referenceVideos", "referenceImages"}, [])
    request.captures = [{"param": "referenceVideos", "source": 'CAMERA_CLIP' if _capture_source(lane) == 'CAMERA' else 'VIEWPORT_CLIP', "camera": None}]
    if note:
        runtime.set_message(f"Clip {note}")
    return request


def _submit(context, request, step):
    if request.errors:
        raise ScenarioError(0, "; ".join(request.errors))
    generation.perform_captures(context, request)
    manager = runtime.ensure_manager()
    lane = context.scene.scenario.lane_state("render")
    meta = {"prompt": lane.prompt, "model_name": runtime.state.records[request.model_id].name if request.model_id in runtime.state.records else request.model_id, "render_step": step}
    rec = manager.submit("render", request.kind, request.model_id, request.body, files=request.files, array_params=request.array_params, meta=meta)
    runtime.state.jobs_view.insert(0, rec)
    if step == "concept":
        lane.concept_job = rec.local_id
    return rec


def submit_concept(context):
    return _submit(context, concept_request(context), "concept")


def submit_video(context):
    return _submit(context, video_request(context), "video")


def on_result(rec):
    if rec.lane != "render" or rec.meta.get("render_step") != "concept" or not rec.files:
        return
    for scene in bpy.data.scenes:
        lane = scene.scenario.lane_state("render")
        if lane.concept_job in ("", rec.local_id):
            lane.concept_path = rec.files[0]
            runtime.set_message("Concept ready, now Playblast and Generate")


def draw_render_lane(layout, context):
    lane = context.scene.scenario.lane_state("render")
    box = layout.box()
    box.label(text="1. Concept look", icon='IMAGE_DATA')
    box.prop(lane, "capture_source", text="Source")
    row = box.row(align=True)
    row.prop(lane, "prompt", text="")
    row.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL').lane = "render"
    refs = [r for r in lane.references if r.source == 'FILE']
    header = box.row()
    header.label(text=f"Style references  {len(refs)}", icon='IMAGE_REFERENCE')
    add = header.operator("scenario.add_reference", text="Add", icon='ADD')
    add.lane, add.param_name, add.source = "render", "styleImages", 'FILE'
    for index, ref in enumerate(lane.references):
        r = box.row(align=True)
        r.label(text=ref.label or ref.filepath, icon='DOT')
        rm = r.operator("scenario.remove_reference", text="", icon='X')
        rm.lane, rm.index = "render", index
    box.operator("scenario.render_concept", text="Render concept", icon='RENDER_STILL')
    if lane.concept_path:
        box.label(text="Concept: " + lane.concept_path.rsplit("/", 1)[-1][:40], icon='CHECKMARK')
        box.operator("scenario.show_image", text="Show concept").filepath = lane.concept_path
    box = layout.box()
    box.label(text="2. Playblast to video (Seedance 2.0)", icon='RENDER_ANIMATION')
    scene = context.scene
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    start, end, seconds = capture_plan.frame_span(scene.frame_start, scene.frame_end, fps, use_preview=scene.use_preview_range,
                                                  preview_start=scene.frame_preview_start, preview_end=scene.frame_preview_end)
    box.label(text=f"Frames {start} to {end}: {seconds:.1f} s at 720p (clamped 4 to 15 s)")
    box.prop(lane, "force_solid")
    box.prop(lane, "generate_audio")
    row = box.row()
    row.scale_y = 1.4
    row.enabled = bool(lane.concept_path)
    row.operator("scenario.render_video", text="Playblast and Generate", icon='PLAY')
    if not lane.concept_path:
        box.label(text="Render a concept first (or use the Video lane directly)", icon='INFO')
```
Add to `ScenarioLaneState`: `capture_source: EnumProperty(items=[('VIEWPORT', "Viewport", ""), ('CAMERA', "Scene camera", "")], default='CAMERA')`, `generate_audio: BoolProperty(default=False)`. Operators `scenario.render_concept` and `scenario.render_video` call `render_to_real.submit_concept/submit_video` with the same error handling as `scenario.generate`. `handlers._on_job` calls `render_to_real.on_result(rec)` on `job_done` before the kind handler. Panel routes `lane == "render"` to `draw_render_lane`; `panels.GENERATE_LANES` becomes `("image", "video", "3d", "material")`.

Run tests (38 OK), commit `feat(blender): render-to-real panel (concept still, then Seedance playblast video)`.

---

### Task 23: P2 GUI proof, smoke, docs, merge

- [ ] GUI: `tools/gui_screenshot.py` lanes `video` and `render` with a prompt; open both PNGs and check the Video lane shows Match timeline, the clip hint and the quote, and the Render-to-real lane shows the two steps.
- [ ] Capture proof (Task 20 step 3) recorded in README.
- [ ] Smoke (opt-in): `tests/smoke/smoke_video.py` runs inside Blender GUI is not needed; use the core: upload `tests/fixtures/smoke/playblast_12f.mp4` (produced by the GUI capture step, copied into fixtures, under 1 MB) as `referenceVideos`, prompt `capture_plan.render_to_real_prompt("a copper teapot spinning")`, `duration 4`, `resolution 480p`, `generateAudio false`; dry run first and abort if above 150 CU; print files and CU.
- [ ] CHANGELOG `0.3.0 (P2)`, README (lanes, credits tally), CLAUDE.md state; `make test && make test-blender`; merge `--no-ff` into main.
