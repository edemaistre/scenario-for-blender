# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry and text editing for the floating composer. No bpy, no gpu: pure numbers and strings."""
from dataclasses import dataclass, field

MARGIN = 24
PILL_WIDTH, PILL_HEIGHT = 320, 44
CARD_WIDTH, CARD_HEIGHT = 820, 150
TAB_HEIGHT, ROW_GAP, PAD = 24, 8, 12
GENERATE_WIDTH, MODEL_WIDTH, COLLAPSE_SIZE, SETTINGS_WIDTH = 190, 200, 20, 84
RESIZE_SIZE, MIN_CARD_WIDTH, MIN_PILL_WIDTH, MIN_VISIBLE, DRAG_THRESHOLD = 16, 420, 200, 40, 4
LANE_ORDER = ("image", "video", "3d", "material", "render_image", "render_video")
LANE_LABELS = {"image": "Image", "video": "Video", "3d": "3D", "material": "Materials", "render_image": "Render Image", "render_video": "Render Video"}
PLACEHOLDERS = {"image": "Describe the image to generate", "video": "Describe the video, or capture the timeline", "3d": "Describe the object",
                "material": "Describe the material (weathered copper, mossy stone...)",
                "render_image": "Describe the look to render the viewport with (empty: Prompt Spark writes it)",
                "render_video": "Describe the look of the video (empty: Prompt Spark writes it)"}


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
    """Single-line editor: text, caret index and a selection anchor.

    The selection is the span between `anchor` and `caret` (None when they coincide or no anchor is set), so
    extending with Shift+arrows, Shift+Home/End, shift-click or a drag only ever moves the caret."""

    def __init__(self, text="", caret=None):
        self.text = text
        self.caret = len(text) if caret is None else max(0, min(caret, len(text)))
        self.anchor = None

    # -- selection ----------------------------------------------------------
    @property
    def selection(self):
        if self.anchor is None or self.anchor == self.caret:
            return None
        a, b = sorted((self.anchor, self.caret))
        return (a, b)

    @selection.setter
    def selection(self, value):
        if value is None:
            self.anchor = None
            return
        a, b = value
        self.anchor, self.caret = self._clamp(a), self._clamp(b)

    def _clamp(self, index):
        return max(0, min(len(self.text), int(index)))

    def _clear_selection(self):
        self.anchor = None

    def _start_extend(self):
        if self.anchor is None:
            self.anchor = self.caret

    def selected_text(self):
        sel = self.selection
        return self.text[sel[0]:sel[1]] if sel else ""

    def select_all(self):
        self.anchor = 0
        self.caret = len(self.text)

    def select_word_at(self, index):
        """Select the word (or the whitespace run) under `index`, as a double-click does."""
        if not self.text:
            return
        i = max(0, min(len(self.text) - 1, int(index)))
        space = self.text[i].isspace()
        a = i
        while a > 0 and self.text[a - 1].isspace() == space:
            a -= 1
        b = i + 1
        while b < len(self.text) and self.text[b].isspace() == space:
            b += 1
        self.anchor, self.caret = a, b

    def caret_at(self, index, extend=False):
        """Place the caret from a click (or a drag when `extend` is true, which keeps the press position as anchor)."""
        if extend:
            self._start_extend()
        else:
            self._clear_selection()
        self.caret = self._clamp(index)

    # -- clipboard -----------------------------------------------------------
    def copy(self):
        return self.selected_text() or self.text

    def cut(self):
        if self.selection:
            out = self.selected_text()
            self.replace_selection("")
            return out
        out = self.text
        self.set_text("")
        return out

    # -- editing -------------------------------------------------------------
    def insert(self, s):
        if self.selection:
            self.replace_selection(s)
            return
        self._clear_selection()
        self.text = self.text[:self.caret] + s + self.text[self.caret:]
        self.caret += len(s)

    def backspace(self):
        if self.selection:
            self.replace_selection("")
            return
        self._clear_selection()
        if self.caret > 0:
            self.text = self.text[:self.caret - 1] + self.text[self.caret:]
            self.caret -= 1

    def delete(self):
        if self.selection:
            self.replace_selection("")
            return
        self._clear_selection()
        if self.caret < len(self.text):
            self.text = self.text[:self.caret] + self.text[self.caret + 1:]

    def replace_selection(self, s):
        if not self.selection:
            self.insert(s)
            return
        a, b = self.selection
        self.text = self.text[:a] + s + self.text[b:]
        self.caret = a + len(s)
        self.anchor = None

    def set_text(self, text):
        self.text = text or ""
        self.caret = min(self.caret, len(self.text))
        self.anchor = None

    # -- caret movement --------------------------------------------------------
    def move(self, delta, extend=False):
        if extend:
            self._start_extend()
            self.caret = self._clamp(self.caret + delta)
            return
        sel = self.selection
        self._clear_selection()
        if sel:
            self.caret = sel[0] if delta < 0 else sel[1]  # collapse onto the edge, like a native text field
            return
        self.caret = self._clamp(self.caret + delta)

    def home(self, extend=False):
        if extend:
            self._start_extend()
        else:
            self._clear_selection()
        self.caret = 0

    def end(self, extend=False):
        if extend:
            self._start_extend()
        else:
            self._clear_selection()
        self.caret = len(self.text)

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
    settings_rect: Rect = None
    resize_rect: Rect = None

    def hit(self, px, py):
        """What the pointer is on. `expand` (collapsed pill), `resize` (corner grip), `drag` (empty card area) or a control."""
        if not self.expanded:
            return ("expand",) if self.pill_rect.contains(px, py) else None
        if self.card_rect is None or not self.card_rect.contains(px, py):
            return None
        if self.resize_rect is not None and self.resize_rect.contains(px, py):
            return ("resize",)
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
        if self.settings_rect is not None and self.settings_rect.contains(px, py):
            return ("settings",)
        return ("drag",)


def _clamp(value, lo, hi):
    if hi < lo:
        hi = lo
    return max(lo, min(hi, value))


def clamp_width(width, region_w, scale=1.0, expanded=True):
    """A card or pill width that fits the region: never narrower than the minimum, never wider than the region minus margins."""
    s = float(scale or 1.0)
    margin = MARGIN * s
    minimum = (MIN_CARD_WIDTH if expanded else MIN_PILL_WIDTH) * s
    maximum = max(minimum, region_w - 2 * margin)
    return _clamp(float(width), minimum, maximum)


def clamp_offset(offset, size, region_w, region_h, scale=1.0):
    """Keep at least MIN_VISIBLE px of a `size`-wide/high box inside the region, given its default bottom-centre position."""
    s = float(scale or 1.0)
    w, h = size
    margin = MARGIN * s
    keep = MIN_VISIBLE * s
    base_x, base_y = (region_w - w) / 2, margin
    ox, oy = offset
    x = _clamp(base_x + ox, keep - w, region_w - keep)
    y = _clamp(base_y + oy, keep - h, region_h - keep)
    return (x - base_x, y - base_y)


def pill_placement(region_w, region_h, expanded, scale=1.0, offset=(0.0, 0.0), width=None):
    """Geometry of the composer. `offset` moves it from its default bottom-centre spot (region pixels), `width`
    overrides the card (expanded) or pill (collapsed) width; both are clamped so the composer stays reachable."""
    s = float(scale or 1.0)
    margin = MARGIN * s
    offset = tuple(offset or (0.0, 0.0))
    if not expanded:
        w = clamp_width(width if width else PILL_WIDTH * s, region_w, s, expanded=False)
        w = min(w, max(MIN_PILL_WIDTH * s, region_w - 2 * margin))
        h = PILL_HEIGHT * s
        ox, oy = clamp_offset(offset, (w, h), region_w, region_h, s)
        return Layout(False, s, Rect((region_w - w) / 2 + ox, margin + oy, w, h))
    w = clamp_width(width if width else CARD_WIDTH * s, region_w, s, expanded=True)
    w = min(w, max(MIN_CARD_WIDTH * s, region_w - 2 * margin))
    h = min(CARD_HEIGHT * s, region_h - 2 * margin)
    ox, oy = clamp_offset(offset, (w, h), region_w, region_h, s)
    x, y = (region_w - w) / 2 + ox, margin + oy
    card = Rect(x, y, w, h)
    pad, gap = PAD * s, ROW_GAP * s
    tab_h = TAB_HEIGHT * s
    tabs_y = card.top - pad - tab_h
    size = COLLAPSE_SIZE * s
    # the minus button sits in the top-right corner, the same distance from the top and the right edge
    collapse = Rect(card.right - pad - size, card.top - pad - size, size, size)
    tab_rects, tx = {}, x + pad
    tab_w = (collapse.x - gap - (x + pad) - gap * (len(LANE_ORDER) - 1)) / len(LANE_ORDER)
    for lane in LANE_ORDER:
        tab_rects[lane] = Rect(tx, tabs_y, tab_w, tab_h)
        tx += tab_w + gap
    row_h = 34 * s
    prompt_y = tabs_y - gap - row_h
    prompt = Rect(x + pad, prompt_y, w - 2 * pad, row_h)
    bottom_y = prompt_y - gap - row_h
    if bottom_y < y + pad:
        bottom_y = y + pad
    model = Rect(x + pad, bottom_y, min(MODEL_WIDTH * s, w / 2 - pad), row_h)
    generate = Rect(card.right - pad - min(GENERATE_WIDTH * s, w / 2 - pad), bottom_y, min(GENERATE_WIDTH * s, w / 2 - pad), row_h)
    settings = None
    room = generate.x - gap - (model.right + gap)
    if room >= 40 * s:
        settings = Rect(model.right + gap, bottom_y, min(SETTINGS_WIDTH * s, room), row_h)
    grip = RESIZE_SIZE * s
    resize = Rect(card.right - grip, card.y, grip, grip)  # bottom-right corner
    return Layout(True, s, Rect(x, y, w, h), card, tab_rects, prompt, model, generate, collapse, settings, resize)
