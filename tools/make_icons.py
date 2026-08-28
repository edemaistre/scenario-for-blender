# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the five modality icons (image, video, audio, 3d, text) as line art matching the Scenario web app.

Usage: python3 tools/make_icons.py   (needs Pillow; writes scenario/icons/<name>.png at 64 px and <name>_32.png at 32 px)

Icons are drawn at 4x on a transparent canvas with light grey strokes and downscaled with Lanczos for anti-aliasing.
Blender loads the 64 px files through bpy.utils.previews (icon_value) so they scale like its own icons."""
import math
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "scenario" / "icons"
STROKE = (230, 230, 230, 255)
SIZE = 64
SCALE = 4
S = SIZE * SCALE          # working canvas
W = 5 * SCALE             # stroke width at 4x (about 5 px at 64 px)


def canvas():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def rounded(d, box, radius, width=W):
    d.rounded_rectangle(box, radius=radius, outline=STROKE, width=width)


def line(d, pts, width=W):
    d.line(pts, fill=STROKE, width=width, joint="curve")
    for x, y in pts:  # round caps
        d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=STROKE)


def icon_image():
    im, d = canvas()
    m = 30 * SCALE // 4
    rounded(d, (m, m + 4 * SCALE, S - m, S - m - 4 * SCALE), 6 * SCALE)
    # sun
    r = 4 * SCALE
    cx, cy = m + 16 * SCALE, m + 18 * SCALE
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=STROKE, width=W)
    # mountains
    base = S - m - 4 * SCALE - W
    line(d, [(m + W, base - 6 * SCALE), (m + 22 * SCALE, base - 22 * SCALE), (m + 32 * SCALE, base - 12 * SCALE), (m + 40 * SCALE, base - 18 * SCALE), (S - m - W, base - 6 * SCALE)])
    return im


def icon_video():
    im, d = canvas()
    m = 8 * SCALE
    body = (m, m + 8 * SCALE, S - m - 18 * SCALE, S - m - 8 * SCALE)
    rounded(d, body, 5 * SCALE)
    # lens triangle
    x0, y0, x1, y1 = body
    cy = (y0 + y1) / 2
    line(d, [(x1 + 2 * SCALE, cy - 7 * SCALE), (S - m, cy - 13 * SCALE), (S - m, cy + 13 * SCALE), (x1 + 2 * SCALE, cy + 7 * SCALE)])
    return im


def icon_audio():
    im, d = canvas()
    m = 10 * SCALE
    # speaker: small box + cone
    bx0, by0, bx1, by1 = m, S / 2 - 8 * SCALE, m + 10 * SCALE, S / 2 + 8 * SCALE
    line(d, [(bx1, by0), (bx0, by0), (bx0, by1), (bx1, by1), (bx1 + 16 * SCALE, by1 + 12 * SCALE), (bx1 + 16 * SCALE, by0 - 12 * SCALE), (bx1, by0)])
    # wave
    cx, cy = bx1 + 16 * SCALE, S / 2
    for radius in (14 * SCALE, 24 * SCALE):
        d.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=-40, end=40, fill=STROKE, width=W)
    return im


def icon_3d():
    im, d = canvas()
    cx, cy, r = S / 2, S / 2, 24 * SCALE
    hexagon = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (30, 90, 150, 210, 270, 330)]
    line(d, hexagon + [hexagon[0]])
    # inner Y: centre to the three alternate corners (top-left, top-right, bottom)
    for a in (150, 30, 270):
        line(d, [(cx, cy), (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))])
    return im


def icon_text():
    im, d = canvas()
    m = 12 * SCALE
    x0, y0, x1, y1 = m + 2 * SCALE, m - 4 * SCALE, S - m - 2 * SCALE, S - m + 4 * SCALE
    fold = 10 * SCALE
    line(d, [(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1), (x0, y0)])
    line(d, [(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)])
    for k in range(3):
        y = y0 + 20 * SCALE + k * 9 * SCALE
        line(d, [(x0 + 8 * SCALE, y), (x1 - 8 * SCALE if k < 2 else x1 - 18 * SCALE, y)])
    return im


ICONS = {"image": icon_image, "video": icon_video, "audio": icon_audio, "3d": icon_3d, "text": icon_text}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in ICONS.items():
        im = fn()
        im.resize((SIZE, SIZE), Image.LANCZOS).save(OUT / f"{name}.png", optimize=True)
        im.resize((32, 32), Image.LANCZOS).save(OUT / f"{name}_32.png", optimize=True)
        print(f"{name}.png {SIZE}px, {name}_32.png 32px")


if __name__ == "__main__":
    main()
