# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompts for the Render Image and Render Video lanes. No bpy.

The models we send a viewport capture to (Gemini 3.1, GPT Image 2, Seedance, Minimax H3...) treat every reference
image as loosely as the prompt lets them. The first render-to-real tests put a character from a style reference on a
roof because the prompt only said "keep the composition". These templates spell out the role of every input: the first
image or the video is the scene to render (geometry, camera and layout frozen), the other images are look references
whose content must not leak into the result."""

DEFAULT_LOOK = "photorealistic, physically based render with natural lighting"

SPARK_BRIEF = (
    "This image is a raw 3D viewport capture (grey or flat shaded). Write an art-direction brief for its finished render: "
    "the materials each visible surface should have, the lighting, the atmosphere, the colour palette and the overall style. "
    "Describe only the look, never the layout: do not mention moving, adding or removing objects, and do not change the camera."
)

IMAGE_TEMPLATE = (
    "Image 1 is a screenshot of a 3D viewport: it is the exact scene to render, nothing else. "
    "Produce the finished render of Image 1 with this look: {look}. "
    "Preserve Image 1 exactly: every object with its position, scale and orientation, the spatial arrangement and relative sizes, "
    "the camera position, angle, focal length, framing and perspective, the horizon line, the silhouettes and proportions. "
    "Do not add, remove, move, duplicate or rescale any object; do not change the viewpoint, the crop or the aspect ratio. "
    "Change only the rendering: materials, textures, surface detail, lighting, shadows, reflections, atmosphere, colour grading "
    "and the treatment of the background.{style}"
)

IMAGE_STYLE_ONE = (
    " Image 2 is a style reference only: borrow its palette, materials, lighting mood and rendering technique. "
    "Do not copy any object, character, text or composition from it; nothing from Image 2 may appear as content in the result."
)
IMAGE_STYLE_MANY = (
    " Images 2 to {last} are style references only: borrow their palette, materials, lighting mood and rendering technique. "
    "Do not copy any object, character, text or composition from them; nothing from those images may appear as content in the result."
)

VIDEO_TEMPLATE = (
    "{video} is a playblast of a 3D animation: it is the exact scene, camera move, timing and object motion to reproduce, nothing else. "
    "Re-render {video} as a finished video with this look: {look}. "
    "Keep {video} frame by frame: the camera path, framing and focal length, every object with its position, scale and motion, "
    "the timing and duration, the layout of the environment. Do not add, remove or move objects, do not change the viewpoint, "
    "do not cut, retime or invent camera moves. "
    "Change only the rendering: materials, textures, lighting, shadows, atmosphere and colour.{first_frame}{style}"
)
VIDEO_FIRST_FRAME = (
    " {image} shows how the finished first frame must look: match it exactly and stay consistent with it through the whole clip."
)
VIDEO_STYLE = (
    " {images} are style references only: use their palette, materials and lighting; do not copy their objects, characters, text or composition into the scene."
)


def clean_look(prompt):
    text = " ".join((prompt or "").split()).strip().rstrip(".")
    return text or DEFAULT_LOOK


def image_prompt(look, style_count=0):
    """Prompt for an image edit model. Image 1 = the capture, images 2..N+1 = style references."""
    style = ""
    if style_count == 1:
        style = IMAGE_STYLE_ONE
    elif style_count > 1:
        style = IMAGE_STYLE_MANY.format(last=style_count + 1)
    return IMAGE_TEMPLATE.format(look=clean_look(look), style=style)


def _image_range(first, last, tagged):
    if tagged:
        if first == last:
            return f"@image{first}"
        return f"@image{first} to @image{last}"
    if first == last:
        return f"reference image {first}"
    return f"reference images {first} to {last}"


def video_prompt(look, image_count=0, first_frame=False, tagged=True):
    """Prompt for a video model fed with the playblast plus optional images.

    `tagged` models (Seedance) address inputs as @video1 / @image1; the others get plain words. When `first_frame` is
    true the first image is the rendered first frame (a Render Image result) and the others are style references."""
    video = "@video1" if tagged else "The reference video"
    first, style = "", ""
    next_index = 1
    if first_frame and image_count >= 1:
        first = VIDEO_FIRST_FRAME.format(image="@image1" if tagged else "Reference image 1")
        next_index = 2
    if image_count >= next_index:
        style = VIDEO_STYLE.format(images=_image_range(next_index, image_count, tagged).capitalize() if not tagged else _image_range(next_index, image_count, tagged))
    text = VIDEO_TEMPLATE.format(video=video, look=clean_look(look), first_frame=first, style=style)
    if not tagged:
        text = text.replace("Re-render The reference video", "Re-render the reference video").replace("Keep The reference video", "Keep the reference video")
    return text

