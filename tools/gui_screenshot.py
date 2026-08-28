# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Blender with the Scenario panel visible, screenshot it, quit.

Usage: blender --python tools/gui_screenshot.py -- /abs/out.png [lane] [delay_seconds]
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/scenario-panel.png"
LANE = argv[1] if len(argv) > 1 else "image"
DELAY = float(argv[2]) if len(argv) > 2 else 6.0


def _prepare():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    bpy.context.scene.scenario.lane = LANE
    ui_region = next(r for r in area.regions if r.type == 'UI')
    try:
        ui_region.active_panel_category = "Scenario"
    except (AttributeError, TypeError):
        pass
    return None


def _shot():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    ui_region = next(r for r in area.regions if r.type == 'UI')
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=ui_region):
        bpy.ops.screen.screenshot(filepath=OUT)
    print("screenshot saved", OUT)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(_prepare, first_interval=1.0)
bpy.app.timers.register(_shot, first_interval=DELAY)
