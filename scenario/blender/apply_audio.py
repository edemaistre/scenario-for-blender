# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audio results: files in the output folder, playable, and droppable on the sequencer as sound strips."""
import logging
import os
import subprocess
import sys

import bpy

from . import runtime

log = logging.getLogger("scenario.audio")
AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".flac")


def on_audio_result(rec):
    files = [p for p in rec.files if p.lower().endswith(AUDIO_EXTS)] or list(rec.files)
    if not files:
        runtime.set_message("The job returned no audio file")
        return []
    runtime.set_message(f"{len(files)} audio file(s) ready: Play, or add them to the sequencer")
    return files


def play_with_os(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # noqa: S606 (Windows only)
    else:
        subprocess.Popen(["xdg-open", path])


def _free_channel(sequences, frame_start, frame_end):
    """First sequencer channel with no strip overlapping [frame_start, frame_end]."""
    for channel in range(1, 128):
        busy = any(s.channel == channel and not (s.frame_final_end <= frame_start or s.frame_final_start >= frame_end) for s in sequences)
        if not busy:
            return channel
    return 1


def add_to_sequencer(context, path, frame=None):
    """Add the file as a sound strip at `frame` (default the current frame) on a free channel; returns the strip."""
    scene = context.scene
    editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = getattr(editor, "strips_all", None) or getattr(editor, "sequences_all", [])
    frame = scene.frame_current if frame is None else int(frame)
    channel = _free_channel(list(strips), frame, frame + 1)
    collection = getattr(editor, "strips", None) or editor.sequences
    strip = collection.new_sound(name=os.path.basename(path)[:60], filepath=path, channel=channel, frame_start=frame)
    log.info("sound strip %s at frame %d on channel %d", strip.name, frame, channel)
    return strip
