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
    hi = cl.pill_placement(1800, 900, expanded=True, scale=2.0)
    assert hi.card_rect.w == cl.CARD_WIDTH * 2
    narrow = cl.pill_placement(500, 400, expanded=True, scale=1.0)
    assert narrow.card_rect.w <= 500 - 2 * cl.MARGIN
    assert narrow.card_rect.x >= 0


def test_prompt_placeholder_and_lane_labels():
    assert cl.LANE_ORDER == ("image", "video", "3d", "material", "render_image", "render_video")
    assert cl.LANE_LABELS["image"] == "Image" and cl.LANE_LABELS["render_image"] == "Render Image" and cl.LANE_LABELS["render_video"] == "Render Video"
    assert cl.placeholder_for("image").startswith("Describe")
    assert "Prompt Spark" in cl.placeholder_for("render_image") and "Prompt Spark" in cl.placeholder_for("render_video")
    assert cl.placeholder_for("unknown") == "Type a prompt"


def test_shift_arrows_extend_and_shrink_the_selection():
    f = cl.TextField("hello world")  # caret at 11
    f.move(-1, extend=True)
    assert f.selection == (10, 11) and f.caret == 10 and f.anchor == 11
    f.move(-4, extend=True)
    assert f.selection == (6, 11) and f.selected_text() == "world"
    f.move(1, extend=True)  # shrink from the caret side
    assert f.selection == (7, 11) and f.selected_text() == "orld"
    f.move(4, extend=True)  # caret meets the anchor: no selection
    assert f.selection is None and f.caret == 11
    f.home(extend=True)
    assert f.selection == (0, 11) and f.caret == 0
    f.end(extend=True)
    assert f.selection is None and f.caret == 11
    f.move(-3)
    f.home(extend=True)
    f.end(extend=True)  # anchor stays at 8, caret to the end
    assert f.selection == (8, 11)


def test_plain_moves_collapse_onto_the_selection_edge():
    f = cl.TextField("abcdef", caret=1)
    f.move(3, extend=True)  # selects bcd, caret 4
    assert f.selection == (1, 4)
    f.move(1)
    assert f.selection is None and f.caret == 4
    f.move(-3, extend=True)
    f.move(-1)
    assert f.selection is None and f.caret == 1
    f.move(2, extend=True)
    f.home()
    assert f.selection is None and f.caret == 0
    f.move(2, extend=True)
    f.end()
    assert f.selection is None and f.caret == 6


def test_typing_paste_backspace_delete_act_on_the_selection():
    f = cl.TextField("hello world", caret=0)
    f.move(5, extend=True)
    f.insert("bye")
    assert f.text == "bye world" and f.caret == 3 and f.selection is None
    f.move(-3, extend=True)
    f.backspace()
    assert f.text == " world" and f.caret == 0
    f.move(1, extend=True)
    f.delete()
    assert f.text == "world" and f.caret == 0
    f.select_all()
    f.insert("pasted text")
    assert f.text == "pasted text" and f.caret == 11
    f.select_all()
    f.replace_selection("")
    assert f.text == "" and f.selection is None
    f.select_all()  # nothing to select in an empty field
    assert f.selection is None


def test_click_shift_click_drag_and_double_click():
    f = cl.TextField("one two  three")
    f.caret_at(2)
    assert f.caret == 2 and f.selection is None
    f.caret_at(6, extend=True)  # shift-click
    assert f.selection == (2, 6) and f.selected_text() == "e tw"
    f.caret_at(0, extend=True)  # drag back past the anchor
    assert f.selection == (0, 2)
    f.caret_at(99)
    assert f.caret == len(f.text) and f.selection is None
    f.select_word_at(5)
    assert f.selected_text() == "two" and f.caret == 7
    f.select_word_at(8)  # inside the double space
    assert f.selected_text() == "  "
    f.select_word_at(0)
    assert f.selected_text() == "one"
    f.select_word_at(50)  # clamped to the last character
    assert f.selected_text() == "three"
    empty = cl.TextField("")
    empty.select_word_at(0)
    assert empty.selection is None


def test_copy_and_cut():
    f = cl.TextField("copy me please", caret=0)
    assert f.copy() == "copy me please"  # nothing selected: the whole text
    f.move(4, extend=True)
    assert f.copy() == "copy" and f.text == "copy me please"
    assert f.cut() == "copy" and f.text == " me please" and f.caret == 0 and f.selection is None
    assert f.cut() == " me please" and f.text == ""


def test_selection_setter_keeps_compatibility_and_set_text_clears_it():
    f = cl.TextField("abcdef")
    f.selection = (1, 4)
    assert f.selection == (1, 4) and f.caret == 4
    f.selection = None
    assert f.selection is None and f.caret == 4
    f.select_all()
    f.set_text("xy")
    assert f.selection is None and f.caret == 2
    f.selection = (0, 50)  # clamped
    assert f.selection == (0, 2)


def test_visible_slice_follows_the_caret_while_selecting():
    f = cl.TextField("a" * 50, caret=50)
    f.home(extend=True)
    start, end = f.visible_slice(20)
    assert start == 0 and end == 20 and f.selection == (0, 50)
    f.caret_at(45, extend=True)
    start, end = f.visible_slice(20)
    assert start <= 45 <= end


def test_settings_chip_and_corner_minus_button():
    expanded = cl.pill_placement(1600, 900, expanded=True, scale=1.0)
    card, c = expanded.card_rect, expanded.collapse_rect
    pad = cl.PAD
    assert c.w == c.h == cl.COLLAPSE_SIZE
    assert abs((card.right - c.right) - pad) < 1e-6 and abs((card.top - c.top) - pad) < 1e-6  # same padding right and top
    for rect in expanded.tab_rects.values():
        assert rect.right <= c.x  # tabs never run under the button
    s = expanded.settings_rect
    assert s is not None and s.x > expanded.model_rect.right and s.right < expanded.generate_rect.x
    assert expanded.hit(s.x + 1, s.y + 1) == ("settings",)
    assert expanded.hit(c.x + c.w - 1, c.y + c.h - 1) == ("collapse",)
    assert len(expanded.tab_rects) == 6 and expanded.hit(*_center(expanded.tab_rects["render_video"])) == ("tab", "render_video")
    narrow = cl.pill_placement(420, 400, expanded=True, scale=1.0)
    assert narrow.settings_rect is None or narrow.settings_rect.right < narrow.generate_rect.x
    assert narrow.hit(narrow.model_rect.x + 1, narrow.model_rect.y + 1) == ("model",)


def _center(rect):
    return rect.x + rect.w / 2, rect.y + rect.h / 2
