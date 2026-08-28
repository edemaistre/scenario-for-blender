# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""gpu/blf drawing of the floating composer. Runs inside a POST_PIXEL draw handler on the main thread; no IO."""
import math

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .. import runtime
from ...core.ui import composer_layout as cl

_batches = {}
_shader = None
FONT = 0
ACCENT = (0.36, 0.55, 1.0, 1.0)
ACCENT_DIM = (0.36, 0.55, 1.0, 0.35)
CARD = (0.11, 0.11, 0.12, 0.92)
FIELD = (0.06, 0.06, 0.07, 1.0)
TEXT = (0.92, 0.92, 0.92, 1.0)
MUTED = (0.6, 0.6, 0.62, 1.0)
TAB = (0.2, 0.2, 0.22, 1.0)
TAB_HOVER = (0.28, 0.28, 0.3, 1.0)
SELECTION = (0.36, 0.55, 1.0, 0.45)
PROMPT_INSET = 12  # horizontal text inset inside the prompt field, in unscaled pixels


def _shader_get():
    global _shader
    if _shader is None:
        _shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    return _shader


def _rounded_verts(w, h, r, segments=6):
    r = max(0.0, min(r, w / 2, h / 2))
    verts = []
    corners = ((w - r, h - r, 0.0), (r, h - r, math.pi / 2), (r, r, math.pi), (w - r, r, 3 * math.pi / 2))
    for cx, cy, start in corners:
        for i in range(segments + 1):
            a = start + (math.pi / 2) * i / segments
            verts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return verts


def _batch(w, h, r):
    key = (int(w), int(h), int(r))
    batch = _batches.get(key)
    if batch is None:
        verts = _rounded_verts(key[0], key[1], key[2])
        batch = batch_for_shader(_shader_get(), 'TRI_FAN', {"pos": verts})
        if len(_batches) > 64:
            _batches.clear()
        _batches[key] = batch
    return batch


def rect(x, y, w, h, color, radius=8.0):
    if w <= 0 or h <= 0:
        return
    shader = _shader_get()
    with gpu.matrix.push_pop():
        gpu.matrix.translate((x, y, 0))
        shader.uniform_float("color", color)
        _batch(w, h, radius).draw(shader)


def text(x, y, size, string, color=TEXT, max_width=None):
    blf.size(FONT, size)
    if max_width is not None:
        while string and blf.dimensions(FONT, string)[0] > max_width:
            string = string[:-2] + "…" if len(string) > 2 else ""
    blf.color(FONT, *color)
    blf.position(FONT, x, y, 0)
    blf.draw(FONT, string)
    return blf.dimensions(FONT, string)[0]


def ui_scale(context):
    prefs = context.preferences
    return prefs.system.pixel_size * prefs.view.ui_scale


def prompt_metrics(prompt_rect, field, scale):
    """Font size, visible slice and text origin of the prompt field: shared by drawing and mouse hit testing."""
    font_px = int(12 * scale)
    blf.size(FONT, font_px)
    char_w = max(1.0, blf.dimensions(FONT, "M")[0] * 0.8)
    width_chars = int((prompt_rect.w - 2 * PROMPT_INSET * scale) / char_w)
    start, end = field.visible_slice(width_chars)
    return font_px, start, end, prompt_rect.x + PROMPT_INSET * scale


def caret_index_at(px, prompt_rect, field, scale):
    """Character index under the horizontal pixel `px`, measured on the visible slice (nearest glyph boundary)."""
    font_px, start, end, x0 = prompt_metrics(prompt_rect, field, scale)
    blf.size(FONT, font_px)
    rel = px - x0
    if rel <= 0:
        return start
    previous = 0.0
    for i in range(start + 1, end + 1):
        width = blf.dimensions(FONT, field.text[start:i])[0]
        if width >= rel:
            return i if (width - rel) <= (rel - previous) else i - 1
        previous = width
    return end


def _chip(r, label, scale, font_px, hovered, fill=TAB, color=TEXT, centered=False):
    rect(r.x, r.y, r.w, r.h, TAB_HOVER if hovered else fill, 6 * scale)
    blf.size(FONT, font_px)
    tw = blf.dimensions(FONT, label)[0]
    x = r.x + (max(4 * scale, (r.w - tw) / 2) if centered else 10 * scale)
    text(x, r.y + (r.h - font_px) / 2 + 2 * scale, font_px, label, color, max_width=r.w - 12 * scale)


def _minus_button(cr, scale, hovered):
    rect(cr.x, cr.y, cr.w, cr.h, TAB_HOVER if hovered else TAB, 4 * scale)
    bar_h = max(1.5, 2 * scale)
    rect(cr.x + cr.w * 0.25, cr.y + (cr.h - bar_h) / 2, cr.w * 0.5, bar_h, TEXT, 0)


def _grip(gr, scale, hovered):
    """Three short diagonal bars in the bottom-right corner: the resize handle of the expanded card."""
    shader = _shader_get()
    color = TEXT if hovered else MUTED
    lines = []
    for i in range(3):
        d = (4 + 4 * i) * scale
        lines.append((gr.right - d, gr.y + 2 * scale))
        lines.append((gr.right - 2 * scale, gr.y + d))
    batch = batch_for_shader(shader, 'LINES', {"pos": lines})
    gpu.state.line_width_set(max(1.0, 1.5 * scale))
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.line_width_set(1.0)


def status_note(lane_state):
    """The line shown next to the model chip: a quote problem, the lane's error, else the add-on's temporary message."""
    if lane_state.estimate_state in ('ERROR', 'UNAVAILABLE') and lane_state.estimate_error:
        return lane_state.estimate_error
    if lane_state.last_error:
        return lane_state.last_error
    visible = getattr(runtime, "message_visible", None)
    if callable(visible):
        return visible() or ""
    return runtime.state.last_message or ""


def _prompt_field(pr, field, focused, lane, scale):
    rect(pr.x, pr.y, pr.w, pr.h, FIELD, 6 * scale)
    font_px, start, end, x0 = prompt_metrics(pr, field, scale)
    text_y = pr.y + (pr.h - font_px) / 2 + 2 * scale
    if not field.text:
        text(x0, text_y, font_px, cl.placeholder_for(lane), MUTED, max_width=pr.w - 2 * PROMPT_INSET * scale)
        if focused:
            rect(x0, pr.y + 8 * scale, max(1.0, 1.5 * scale), pr.h - 16 * scale, TEXT, 0)
        return
    blf.size(FONT, font_px)
    sel = field.selection
    if sel and focused:
        a, b = max(sel[0], start), min(sel[1], end)
        if b > a:
            sx0 = x0 + blf.dimensions(FONT, field.text[start:a])[0]
            sx1 = x0 + blf.dimensions(FONT, field.text[start:b])[0]
            rect(sx0, pr.y + 6 * scale, sx1 - sx0, pr.h - 12 * scale, SELECTION, 3 * scale)
    text(x0, text_y, font_px, field.text[start:end], TEXT)
    if focused:
        caret_x = x0 + blf.dimensions(FONT, field.text[start:max(start, min(field.caret, end))])[0]
        rect(caret_x, pr.y + 8 * scale, max(1.0, 1.5 * scale), pr.h - 16 * scale, TEXT, 0)


def draw_composer():
    context = bpy.context
    region = context.region
    scene = context.scene
    if region is None or scene is None or not hasattr(scene, "scenario"):
        return
    if context.space_data is None or context.space_data.type != 'VIEW_3D' or context.space_data.region_3d is None:
        return
    state = runtime.state.composer
    if state is None:
        return
    scale = ui_scale(context)
    layout = cl.pill_placement(region.width, region.height, state.expanded, scale,
                               offset=state.offset, width=state.width if state.expanded else None)
    state.layout = layout
    lane_state = state.sync_from_lane(scene) if not state.focused else scene.scenario.lane_state(state.lane_for(scene))
    lane = state.lane_for(scene)
    font_px = int(12 * scale)
    gpu.state.blend_set('ALPHA')
    try:
        if not state.expanded:
            # the collapsed composer shares the card's language: same fill, same corner radius, same field and button styles
            r = layout.pill_rect
            rect(r.x, r.y, r.w, r.h, CARD, 12 * scale)
            gen_w = 96 * scale
            inset = 6 * scale
            field_rect = cl.Rect(r.x + inset, r.y + inset, r.w - gen_w - 3 * inset, r.h - 2 * inset)
            rect(field_rect.x, field_rect.y, field_rect.w, field_rect.h, FIELD, 6 * scale)
            label = lane_state.prompt or cl.placeholder_for(lane)
            text(field_rect.x + 10 * scale, r.y + (r.h - font_px) / 2 + 2 * scale, font_px, label, TEXT if lane_state.prompt else MUTED, max_width=field_rect.w - 20 * scale)
            gx = r.right - inset - gen_w
            rect(gx, r.y + inset, gen_w, r.h - 2 * inset, ACCENT if lane_state.prompt else ACCENT_DIM, 6 * scale)
            blf.size(FONT, font_px)
            tw = blf.dimensions(FONT, "Generate")[0]
            text(gx + max(4 * scale, (gen_w - tw) / 2), r.y + (r.h - font_px) / 2 + 2 * scale, font_px, "Generate", TEXT, max_width=gen_w - 8 * scale)
            return
        card = layout.card_rect
        rect(card.x, card.y, card.w, card.h, CARD, 12 * scale)
        for tab_lane, tr in layout.tab_rects.items():
            active = tab_lane == lane
            _chip(tr, cl.LANE_LABELS[tab_lane], scale, font_px, hovered=(state.hover == ("tab", tab_lane)) and not active,
                  fill=ACCENT if active else TAB, centered=True)
        _minus_button(layout.collapse_rect, scale, hovered=(state.hover == ("collapse",)))
        _prompt_field(layout.prompt_rect, state.field, state.focused, lane, scale)
        mr = layout.model_rect
        record = runtime.state.records.get(lane_state.model_id)
        model_name = record.name if record else ("Loading models..." if not runtime.state.catalog_loaded else "Pick a model")
        _chip(mr, model_name, scale, font_px, hovered=(state.hover == ("model",)))
        note_x = mr.right + 10 * scale
        if layout.settings_rect is not None:
            _chip(layout.settings_rect, "Settings", scale, font_px, hovered=(state.hover == ("settings",)), color=MUTED, centered=True)
            note_x = layout.settings_rect.right + 10 * scale
        gr = layout.generate_rect
        from .. import panels

        rect(gr.x, gr.y, gr.w, gr.h, ACCENT if lane_state.prompt else ACCENT_DIM, 6 * scale)
        label = panels.generate_button_text(lane_state)
        blf.size(FONT, font_px)
        tw = blf.dimensions(FONT, label)[0]
        text(gr.x + max(8 * scale, (gr.w - tw) / 2), gr.y + (gr.h - font_px) / 2 + 2 * scale, font_px, label, TEXT, max_width=gr.w - 12 * scale)
        if layout.resize_rect is not None:
            _grip(layout.resize_rect, scale, hovered=(state.hover == ("resize",)) or state.drag_mode == "resize")
        note = status_note(lane_state)
        if note and gr.x - note_x > 40 * scale:
            text(note_x, mr.y + (mr.h - font_px) / 2 + 2 * scale, int(11 * scale), note, MUTED, max_width=gr.x - note_x - 10 * scale)
    finally:
        gpu.state.blend_set('NONE')
