# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.ui import composer_layout as cl


def test_text_field_editing_and_caret():
    f = cl.TextField("hello")
    assert f.caret == 5
    f.insert(" world")
    assert f.text == "hello world" and f.caret == 11
    f.move(-5)
    f.backspace()
    assert f.text == "helloworld" and f.caret == 5
    f.delete()
    assert f.text == "helloorld"
    f.home()
    assert f.caret == 0
    f.end()
    assert f.caret == len(f.text)
    f.select_all()
    assert f.selection == (0, len(f.text))
    f.replace_selection("x")
    assert f.text == "x" and f.caret == 1 and f.selection is None


def test_visible_slice_keeps_caret_visible():
    f = cl.TextField("a" * 50)
    assert f.visible_slice(20) == (30, 50)
    f.home()
    assert f.visible_slice(20) == (0, 20)
    f.move(25)
    start, end = f.visible_slice(20)
    assert start <= 25 <= end and end - start == 20


def test_pill_placement_and_hit_testing():
    collapsed = cl.pill_placement(1600, 900, expanded=False, scale=1.0)
    assert collapsed.pill_rect.w == cl.PILL_WIDTH and collapsed.pill_rect.y == cl.MARGIN
    assert abs((collapsed.pill_rect.x + collapsed.pill_rect.w / 2) - 800) < 1
    assert collapsed.hit(800, cl.MARGIN + 10) == ("expand",)
    assert collapsed.hit(10, 10) is None
    expanded = cl.pill_placement(1600, 900, expanded=True, scale=1.0)
    card = expanded.card_rect
    assert card.w == cl.CARD_WIDTH and card.x >= 0 and card.y >= 0
    tab = expanded.tab_rects["material"]
    assert expanded.hit(tab.x + 2, tab.y + 2) == ("tab", "material")
    p = expanded.prompt_rect
    assert expanded.hit(p.x + 5, p.y + 5) == ("prompt",)
    g = expanded.generate_rect
    assert expanded.hit(g.x + 1, g.y + 1) == ("generate",)
    m = expanded.model_rect
    assert expanded.hit(m.x + 1, m.y + 1) == ("model",)
    c = expanded.collapse_rect
    assert expanded.hit(c.x + 1, c.y + 1) == ("collapse",)
    for rect in (card, tab, p, g, m, c):
        assert rect.x >= 0 and rect.y >= 0 and rect.x + rect.w <= 1600 and rect.y + rect.h <= 900


def test_scale_multiplies_every_size_and_fits_small_regions():
    hi = cl.pill_placement(1600, 900, expanded=True, scale=2.0)
    assert hi.card_rect.w == cl.CARD_WIDTH * 2
    narrow = cl.pill_placement(500, 400, expanded=True, scale=1.0)
    assert narrow.card_rect.w <= 500 - 2 * cl.MARGIN
    assert narrow.card_rect.x >= 0


def test_prompt_placeholder_and_lane_labels():
    assert cl.LANE_LABELS["image"] == "Image" and "render" in cl.LANE_LABELS
    assert cl.placeholder_for("image").startswith("Describe")
