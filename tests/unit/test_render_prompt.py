# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import render_prompt as rp


def test_image_prompt_names_the_capture_and_freezes_the_layout():
    text = rp.image_prompt("weathered copper steampunk look")
    assert text.startswith("Image 1 is a screenshot of a 3D viewport")
    assert "weathered copper steampunk look" in text
    assert "Do not add, remove, move, duplicate or rescale any object" in text
    assert "Image 2" not in text


def test_image_prompt_declares_style_references_as_look_only():
    one = rp.image_prompt("anime", style_count=1)
    many = rp.image_prompt("anime", style_count=3)
    assert "Image 2 is a style reference only" in one
    assert "Images 2 to 4 are style references only" in many
    assert "nothing from those images may appear as content" in many


def test_empty_look_falls_back_to_a_photoreal_default():
    assert rp.DEFAULT_LOOK in rp.image_prompt("")
    assert rp.DEFAULT_LOOK in rp.image_prompt("   ")
    assert rp.clean_look("  a  look. ") == "a look"


def test_video_prompt_tagged_for_seedance():
    text = rp.video_prompt("claymation", image_count=3, first_frame=True, tagged=True)
    assert text.startswith("@video1 is a playblast of a 3D animation")
    assert "@image1 shows how the finished first frame must look" in text
    assert "@image2 to @image3 are style references only" in text
    assert "do not cut, retime or invent camera moves" in text


def test_video_prompt_plain_words_for_models_without_tags():
    text = rp.video_prompt("oil painting", image_count=1, first_frame=False, tagged=False)
    assert text.startswith("The reference video is a playblast")
    assert "@video1" not in text and "@image" not in text
    assert "Reference image 1 are style references only".lower() not in text.lower() or "reference image 1" in text.lower()
    assert "re-render the reference video" in text.lower()


def test_video_prompt_without_images_has_no_image_clauses():
    text = rp.video_prompt("photoreal")
    assert "@image" not in text and "style references" not in text


def test_order_image_inputs_capture_first_then_first_frame_then_styles():
    assert rp.order_image_inputs("cap.png", ["a.png", "b.png"]) == ["cap.png", "a.png", "b.png"]
    assert rp.order_image_inputs(None, ["a.png", "a.png"], first_frame="ff.png") == ["ff.png", "a.png"]
