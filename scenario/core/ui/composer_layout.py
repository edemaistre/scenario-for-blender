# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry and text editing for the floating composer. No bpy, no gpu: pure numbers and strings."""
from dataclasses import dataclass, field

MARGIN = 24
PILL_WIDTH, PILL_HEIGHT = 320, 44
CARD_WIDTH, CARD_HEIGHT = 720, 150
TAB_HEIGHT, ROW_GAP, PAD = 24, 8, 12
GENERATE_WIDTH, MODEL_WIDTH, COLLAPSE_SIZE = 190, 200, 20
LANE_ORDER = ("image", "video", "3d", "material", "render")
LANE_LABELS = {"image": "Image", "video": "Video", "3d": "3D", "material": "Materials", "render": "Render-to-real"}
PLACEHOLDERS = {"image": "Describe the image to generate", "video": "Describe the video, or capture the timeline", "3d": "Describe the object",
                "material": "Describe the material (weathered copper, mossy stone...)", "render": "Describe the look of the concept"}


def placeholder_for(lane):
    return PLACEHOLDERS.get(lane, "Type a prompt")


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    @property
    def right(self):
        return self.x + self.w

    @property
    def top(self):
        return self.y + self.h


class TextField:
    """Single-line editor: text, caret index, optional selection (a, b) with a < b."""

    def __init__(self, text="", caret=None):
        self.text = text
        self.caret = len(text) if caret is None else max(0, min(caret, len(text)))
        self.selection = None

    def _clear_selection(self):
        self.selection = None

    def insert(self, s):
        if self.selection:
            self.replace_selection(s)
            return
        self.text = self.text[:self.caret] + s + self.text[self.caret:]
        self.caret += len(s)

    def backspace(self):
        if self.selection:
            self.replace_selection("")
            return
        if self.caret > 0:
            self.text = self.text[:self.caret - 1] + self.text[self.caret:]
            self.caret -= 1

    def delete(self):
        if self.selection:
            self.replace_selection("")
            return
        if self.caret < len(self.text):
            self.text = self.text[:self.caret] + self.text[self.caret + 1:]

    def move(self, delta):
        self._clear_selection()
        self.caret = max(0, min(len(self.text), self.caret + delta))

    def home(self):
        self._clear_selection()
        self.caret = 0

    def end(self):
        self._clear_selection()
        self.caret = len(self.text)

    def select_all(self):
        self.selection = (0, len(self.text)) if self.text else None
        self.caret = len(self.text)

    def replace_selection(self, s):
        if not self.selection:
            self.insert(s)
            return
        a, b = self.selection
        self.text = self.text[:a] + s + self.text[b:]
        self.caret = a + len(s)
        self.selection = None

    def set_text(self, text):
        self.text = text or ""
        self.caret = min(self.caret, len(self.text))
        self.selection = None

    def visible_slice(self, width_chars):
        width_chars = max(1, int(width_chars))
        if len(self.text) <= width_chars:
            return 0, len(self.text)
        start = max(0, min(self.caret - width_chars + 1, len(self.text) - width_chars))
        if self.caret < start:
            start = self.caret
        return start, min(len(self.text), start + width_chars)


@dataclass
class Layout:
    expanded: bool
    scale: float
    pill_rect: Rect
    card_rect: Rect = None
    tab_rects: dict = field(default_factory=dict)
    prompt_rect: Rect = None
    model_rect: Rect = None
    generate_rect: Rect = None
    collapse_rect: Rect = None

    def hit(self, px, py):
        if not self.expanded:
            return ("expand",) if self.pill_rect.contains(px, py) else None
        if self.card_rect is None or not self.card_rect.contains(px, py):
            return None
        if self.collapse_rect.contains(px, py):
            return ("collapse",)
        for lane, rect in self.tab_rects.items():
            if rect.contains(px, py):
                return ("tab", lane)
        if self.prompt_rect.contains(px, py):
            return ("prompt",)
        if self.generate_rect.contains(px, py):
            return ("generate",)
        if self.model_rect.contains(px, py):
            return ("model",)
        return ("card",)


def pill_placement(region_w, region_h, expanded, scale=1.0):
    s = float(scale or 1.0)
    margin = MARGIN * s
    if not expanded:
        w, h = PILL_WIDTH * s, PILL_HEIGHT * s
        w = min(w, region_w - 2 * margin)
        return Layout(False, s, Rect((region_w - w) / 2, margin, w, h))
    w = min(CARD_WIDTH * s, region_w - 2 * margin)
    h = min(CARD_HEIGHT * s, region_h - 2 * margin)
    x, y = (region_w - w) / 2, margin
    card = Rect(x, y, w, h)
    pad, gap = PAD * s, ROW_GAP * s
    tab_h = TAB_HEIGHT * s
    tabs_y = card.top - pad - tab_h
    tab_rects, tx = {}, x + pad
    tab_w = (w - 2 * pad - COLLAPSE_SIZE * s - gap - gap * (len(LANE_ORDER) - 1)) / len(LANE_ORDER)
    for lane in LANE_ORDER:
        tab_rects[lane] = Rect(tx, tabs_y, tab_w, tab_h)
        tx += tab_w + gap
    collapse = Rect(card.right - pad - COLLAPSE_SIZE * s, tabs_y + (tab_h - COLLAPSE_SIZE * s) / 2, COLLAPSE_SIZE * s, COLLAPSE_SIZE * s)
    row_h = 34 * s
    prompt_y = tabs_y - gap - row_h
    prompt = Rect(x + pad, prompt_y, w - 2 * pad, row_h)
    bottom_y = prompt_y - gap - row_h
    if bottom_y < y + pad:
        bottom_y = y + pad
    model = Rect(x + pad, bottom_y, min(MODEL_WIDTH * s, w / 2 - pad), row_h)
    generate = Rect(card.right - pad - min(GENERATE_WIDTH * s, w / 2 - pad), bottom_y, min(GENERATE_WIDTH * s, w / 2 - pad), row_h)
    return Layout(True, s, Rect(x, y, w, h), card, tab_rects, prompt, model, generate, collapse)
