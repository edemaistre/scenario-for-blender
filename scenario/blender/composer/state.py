# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Interaction state of the floating composer, mirrored into the Scene lane state."""
from ...core.ui.composer_layout import TextField


class ComposerState:
    def __init__(self):
        self.expanded = False
        self.focused = False
        self.hover = None
        self.mouse = (0, 0)
        self.field = TextField("")
        self.synced_lane = ""
        self.synced_text = None
        self.layout = None

    def lane_for(self, scene):
        lane = scene.scenario.lane
        return lane if lane in ("image", "video", "3d", "material", "render") else "image"

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
