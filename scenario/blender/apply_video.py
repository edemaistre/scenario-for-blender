# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Video results: remember the file, offer playback."""
import subprocess

import bpy

from . import runtime


def on_video_result(rec):
    if rec.files:
        runtime.set_message(f"Video ready: {rec.files[0].rsplit('/', 1)[-1]}")
    return list(rec.files)


def play_with_os(path):
    bpy.ops.wm.path_open(filepath=path)


def play_with_blender(path):
    subprocess.Popen([bpy.app.binary_path, "-a", path])
