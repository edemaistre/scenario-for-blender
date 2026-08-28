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
    layout = cl.pill_placement(region.width, region.height, state.expanded, scale)
    state.layout = layout
    lane_state = state.sync_from_lane(scene) if not state.focused else scene.scenario.lane_state(state.lane_for(scene))
    lane = state.lane_for(scene)
    font_px = int(12 * scale)
    gpu.state.blend_set('ALPHA')
    try:
        if not state.expanded:
            r = layout.pill_rect
            rect(r.x, r.y, r.w, r.h, CARD, r.h / 2)
            label = lane_state.prompt or cl.placeholder_for(lane)
            text(r.x + 16 * scale, r.y + (r.h - font_px) / 2 + 2 * scale, font_px, label, TEXT if lane_state.prompt else MUTED, max_width=r.w - 120 * scale)
            gen_w = 84 * scale
            rect(r.right - gen_w - 6 * scale, r.y + 6 * scale, gen_w, r.h - 12 * scale, ACCENT if lane_state.prompt else ACCENT_DIM, (r.h - 12 * scale) / 2)
            text(r.right - gen_w + 6 * scale, r.y + (r.h - font_px) / 2 + 2 * scale, font_px, "Generate", TEXT, max_width=gen_w - 12 * scale)
            return
        card = layout.card_rect
        rect(card.x, card.y, card.w, card.h, CARD, 12 * scale)
        for tab_lane, tr in layout.tab_rects.items():
            active = tab_lane == lane
            hovered = state.hover == ("tab", tab_lane)
            rect(tr.x, tr.y, tr.w, tr.h, ACCENT if active else (TAB if not hovered else (0.28, 0.28, 0.3, 1.0)), 6 * scale)
            label = cl.LANE_LABELS[tab_lane]
            blf.size(FONT, font_px)
            tw = blf.dimensions(FONT, label)[0]
            text(tr.x + max(4 * scale, (tr.w - tw) / 2), tr.y + (tr.h - font_px) / 2 + 2 * scale, font_px, label, TEXT, max_width=tr.w - 6 * scale)
        cr = layout.collapse_rect
        text(cr.x + 4 * scale, cr.y + 2 * scale, font_px, "v", MUTED)
        pr = layout.prompt_rect
        rect(pr.x, pr.y, pr.w, pr.h, FIELD, 6 * scale)
        blf.size(FONT, font_px)
        char_w = max(1.0, blf.dimensions(FONT, "M")[0] * 0.8)
        width_chars = int((pr.w - 24 * scale) / char_w)
        field = state.field
        if field.text:
            start, end = field.visible_slice(width_chars)
            shown = field.text[start:end]
            text(pr.x + 12 * scale, pr.y + (pr.h - font_px) / 2 + 2 * scale, font_px, shown, TEXT)
            if state.focused:
                caret_x = pr.x + 12 * scale + blf.dimensions(FONT, field.text[start:field.caret])[0]
                rect(caret_x, pr.y + 8 * scale, max(1.0, 1.5 * scale), pr.h - 16 * scale, TEXT, 0)
        else:
            text(pr.x + 12 * scale, pr.y + (pr.h - font_px) / 2 + 2 * scale, font_px, cl.placeholder_for(lane), MUTED, max_width=pr.w - 24 * scale)
            if state.focused:
                rect(pr.x + 12 * scale, pr.y + 8 * scale, max(1.0, 1.5 * scale), pr.h - 16 * scale, TEXT, 0)
        mr = layout.model_rect
        rect(mr.x, mr.y, mr.w, mr.h, TAB, 6 * scale)
        record = runtime.state.records.get(lane_state.model_id)
        model_name = record.name if record else ("Loading models..." if not runtime.state.catalog_loaded else "Pick a model")
        text(mr.x + 10 * scale, mr.y + (mr.h - font_px) / 2 + 2 * scale, font_px, model_name, TEXT, max_width=mr.w - 20 * scale)
        gr = layout.generate_rect
        from .. import panels

        rect(gr.x, gr.y, gr.w, gr.h, ACCENT if lane_state.prompt else ACCENT_DIM, 6 * scale)
        label = panels.generate_button_text(lane_state)
        blf.size(FONT, font_px)
        tw = blf.dimensions(FONT, label)[0]
        text(gr.x + max(8 * scale, (gr.w - tw) / 2), gr.y + (gr.h - font_px) / 2 + 2 * scale, font_px, label, TEXT, max_width=gr.w - 12 * scale)
        note = lane_state.estimate_error if lane_state.estimate_state in ('ERROR', 'UNAVAILABLE') else (lane_state.last_error or runtime.state.last_message)
        if note:
            text(mr.right + 10 * scale, mr.y + (mr.h - font_px) / 2 + 2 * scale, int(11 * scale), note, MUTED, max_width=gr.x - mr.right - 20 * scale)
    finally:
        gpu.state.blend_set('NONE')
