# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Blender with the Scenario panel visible, screenshot it, quit.

Usage: blender [file.blend] --python tools/gui_screenshot.py -- /abs/out.png [lane] [delay_seconds] [prompt]
Opening a .blend file (any, tools/blank.blend is provided) avoids the splash screen.
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/scenario-panel.png"
LANE = argv[1] if len(argv) > 1 else "image"
DELAY = float(argv[2]) if len(argv) > 2 else 6.0
PROMPT = argv[3] if len(argv) > 3 else ""
ACTION = argv[4] if len(argv) > 4 else ""


def _view3d():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    return window, area


def _prepare():
    try:
        window, area = _view3d()
        space = area.spaces.active
        space.show_region_ui = True
        bpy.context.scene.scenario.lane = LANE
        if PROMPT and bpy.context.scene.scenario.lane_state(LANE) is not None:
            bpy.context.scene.scenario.lane_state(LANE).prompt = PROMPT
        if LANE == "history":
            bpy.ops.scenario.history_refresh()
        if ACTION == "capture":
            import importlib
            import pathlib
            name = next(n for n in bpy.context.preferences.addons.keys() if n.endswith(".scenario"))
            capture = importlib.import_module(name + ".blender.capture")
            out_dir = pathlib.Path(OUT).parent
            clip = capture.capture_playblast(bpy.context, str(out_dir / "gui_playblast.mp4"), source='CAMERA', frame_start=1, frame_end=72)
            still = capture.capture_still(bpy.context, str(out_dir / "gui_still.png"), source='VIEWPORT')
            for p in (pathlib.Path(clip["path"]), pathlib.Path(still)):
                print("capture file:", p, p.exists(), p.stat().st_size if p.exists() else 0)
            print("capture dir listing:", sorted(x.name for x in out_dir.iterdir() if x.name.startswith("gui_")))
        ui_region = next(r for r in area.regions if r.type == 'UI')
        try:
            ui_region.active_panel_category = "Scenario"
        except (AttributeError, TypeError) as err:
            print("active_panel_category not settable:", err)
        area.tag_redraw()
        print("prepared: sidebar", space.show_region_ui, "ui region width", ui_region.width)
    except Exception as err:  # keep going, the screenshot tells the rest
        print("prepare failed:", err)
    return None


def _select_tab():
    try:
        window, area = _view3d()
        ui_region = next(r for r in area.regions if r.type == 'UI')
        ui_region.active_panel_category = "Scenario"
        area.tag_redraw()
        print("tab selected:", ui_region.active_panel_category)
    except Exception as err:
        print("tab select failed:", err)
    return None


def _shot():
    window, area = _view3d()
    ui_region = next(r for r in area.regions if r.type == 'UI')
    print("ui region width at shot:", ui_region.width, "tab:", getattr(ui_region, "active_panel_category", "?"))
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=ui_region):
        try:
            ui_region.active_panel_category = "Scenario"
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
        except Exception as err:
            print("forced redraw failed:", err)
        bpy.ops.screen.screenshot(filepath=OUT)
    print("screenshot saved", OUT)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(_prepare, first_interval=1.5)
bpy.app.timers.register(_select_tab, first_interval=max(2.5, DELAY - 2.0))
bpy.app.timers.register(_shot, first_interval=DELAY)
