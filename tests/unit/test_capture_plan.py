# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import capture_plan as cp


def test_frame_span_uses_preview_range_when_asked():
    assert cp.frame_span(1, 250, 24) == (1, 250, 250 / 24)
    assert cp.frame_span(1, 250, 24, use_preview=True, preview_start=10, preview_end=57) == (10, 57, 48 / 24)


def test_choose_duration_rounds_up_and_clamps():
    allowed = (-1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
    assert cp.choose_duration(2.0, allowed) == (4, "padded to the 4 s minimum")
    assert cp.choose_duration(6.2, allowed) == (7, "")
    assert cp.choose_duration(40.0, allowed) == (15, "trimmed to the 15 s maximum")
    assert cp.choose_duration(5.0, (-1,)) == (-1, "")


def test_clip_frames_for_limit():
    assert cp.clip_frames_for(15, 24, 1, 1000) == (1, 360)
    assert cp.clip_frames_for(15, 24, 1, 100) == (1, 100)


def test_tag_prompt_adds_missing_mentions_once():
    assert cp.tag_prompt("a wolf running", True, True).startswith("@video1 @image1 ")
    assert cp.tag_prompt("use @image1 as style", False, True) == "use @image1 as style"
    assert cp.tag_prompt("", True, False) == "@video1"


def test_ensure_min_frames_pads_short_clips():
    assert cp.ensure_min_frames(1, 12, 24) == (1, 96, True)
    assert cp.ensure_min_frames(10, 200, 24) == (10, 200, False)
    assert cp.ensure_min_frames(1, 48, 24, min_seconds=2.0) == (1, 48, False)


def test_clamp_duration_for_numeric_ranges():
    assert cp.clamp_duration(6.0, 5, 15) == (6, "")
    assert cp.clamp_duration(6.04, 5, 15) == (7, "")
    assert cp.clamp_duration(2.0, 5, 15) == (5, "padded to the 5 s minimum")
    assert cp.clamp_duration(30.0, 5, 15) == (15, "trimmed to the 15 s maximum")
    assert cp.clamp_duration(2.5, None, None, integer=False) == (2.5, "")
