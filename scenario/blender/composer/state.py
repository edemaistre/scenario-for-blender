# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Interaction state of the floating composer, mirrored into the Scene lane state."""
from ...core.ui.composer_layout import LANE_ORDER, TextField

COMPOSER_LANES = tuple(LANE_ORDER)


class ComposerState:
    def __init__(self):
        self.expanded = False
        self.focused = False
        self.dragging = False      # left button held inside the prompt: mouse moves extend the selection
        self.hover = None
        self.mouse = (0, 0)
        self.field = TextField("")
        self.synced_lane = ""
        self.synced_text = None
        self.layout = None
        # placement: offset from the default bottom-centre spot (region pixels) and an optional card width
        self.offset = (0.0, 0.0)
        self.width = None
        self.drag_mode = None      # None | "pending" | "move" | "resize"
        self.drag_start = None     # dict(mouse, offset, width, kind) captured at the press
        self.moved = False

    def lane_for(self, scene):
        """The composer drives the six generation lanes; other tabs (Generations, MCP, 3D tools) fall back to Image."""
        lane = scene.scenario.lane
        if lane in COMPOSER_LANES and scene.scenario.lane_state(lane) is not None:
            return lane
        return "image"

    def sync_from_lane(self, scene):
        lane = self.lane_for(scene)
        lane_state = scene.scenario.lane_state(lane)
        if lane != self.synced_lane or lane_state.prompt != self.synced_text:
            self.field.set_text(lane_state.prompt)
            self.field.end()
            self.synced_lane, self.synced_text = lane, lane_state.prompt
        return lane_state

    def commit_to_lane(self, scene):
        lane = self.lane_for(scene)
        lane_state = scene.scenario.lane_state(lane)
        if lane_state.prompt != self.field.text:
            lane_state.prompt = self.field.text
        self.synced_lane, self.synced_text = lane, self.field.text
        return lane_state

    # -- placement ------------------------------------------------------------
    def begin_drag(self, mouse, kind):
        """Remember where a press happened so a move beyond the threshold turns into a drag (or a resize)."""
        self.drag_mode = "resize" if kind == "resize" else "pending"
        self.drag_start = {"mouse": tuple(mouse), "offset": tuple(self.offset), "width": self.width, "kind": kind}
        self.moved = False

    def cancel_drag(self):
        """Escape: put the composer back where it was when the press happened."""
        if self.drag_start is not None:
            self.offset = tuple(self.drag_start["offset"])
            self.width = self.drag_start["width"]
        self.drag_mode = None
        self.drag_start = None
        self.moved = False

    def end_drag(self):
        kind = self.drag_start["kind"] if self.drag_start else None
        mode, moved = self.drag_mode, self.moved
        self.drag_mode = None
        self.drag_start = None
        self.moved = False
        return kind, mode, moved

    def reset_layout(self):
        self.offset = (0.0, 0.0)
        self.width = None
