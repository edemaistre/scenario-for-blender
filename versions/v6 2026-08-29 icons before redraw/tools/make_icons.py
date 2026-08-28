# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the modality icons (image, video, audio, 3d, text) and the prompt-tool icons (dice, sparkles, translate)
as line art matching the Scenario web app.

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


def _star(d, cx, cy, outer, inner, width=W):
    """Four-point star (concave), outline only."""
    pts = []
    for k in range(8):
        a = math.radians(-90 + 45 * k)
        r = outer if k % 2 == 0 else inner
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    line(d, pts + [pts[0]], width=width)


def icon_dice():
    """Two dice outlines, the back one offset up-right, three dots on the front one (Scenario's 'Generate a new prompt')."""
    im, d = canvas()
    m = 10 * SCALE
    side = 34 * SCALE
    back = (S - m - side, m, S - m, m + side)
    front = (m, S - m - side, m + side, S - m)
    rounded(d, back, 6 * SCALE)
    # erase the part of the back die hidden by the front one, then draw the front one
    d.rounded_rectangle(front, radius=6 * SCALE, fill=(0, 0, 0, 0))
    rounded(d, front, 6 * SCALE)
    fx0, fy0, fx1, fy1 = front
    r = 3 * SCALE
    for fx, fy in ((0.3, 0.3), (0.5, 0.5), (0.7, 0.7)):
        cx, cy = fx0 + (fx1 - fx0) * fx, fy0 + (fy1 - fy0) * fy
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=STROKE)
    return im


def icon_sparkles():
    """One large four-point star with two small ones (Scenario's 'Rewrite your prompt')."""
    im, d = canvas()
    _star(d, S * 0.44, S * 0.56, 24 * SCALE, 7 * SCALE)
    _star(d, S * 0.80, S * 0.24, 8 * SCALE, 2.5 * SCALE, width=int(W * 0.8))
    _star(d, S * 0.84, S * 0.72, 6 * SCALE, 2 * SCALE, width=int(W * 0.8))
    return im


def icon_translate():
    """A stylised character top-left and a Latin A bottom-right (Scenario's 'Translate to English')."""
    im, d = canvas()
    # character: a top bar, a stem, two legs spreading from the stem (reads as 文)
    cx, top = S * 0.34, S * 0.14
    line(d, [(cx - 12 * SCALE, top + 8 * SCALE), (cx + 12 * SCALE, top + 8 * SCALE)])
    line(d, [(cx, top), (cx, top + 8 * SCALE)], width=int(W * 0.9))
    line(d, [(cx - 11 * SCALE, top + 32 * SCALE), (cx + 2 * SCALE, top + 8 * SCALE)])
    line(d, [(cx - 6 * SCALE, top + 14 * SCALE), (cx + 11 * SCALE, top + 32 * SCALE)])
    # A: two legs and a crossbar
    ax, base = S * 0.70, S * 0.90
    h = 30 * SCALE
    line(d, [(ax - 12 * SCALE, base), (ax, base - h), (ax + 12 * SCALE, base)])
    line(d, [(ax - 7 * SCALE, base - h * 0.38), (ax + 7 * SCALE, base - h * 0.38)])
    return im


ICONS = {"image": icon_image, "video": icon_video, "audio": icon_audio, "3d": icon_3d, "text": icon_text,
         "dice": icon_dice, "sparkles": icon_sparkles, "translate": icon_translate}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in ICONS.items():
        im = fn()
        im.resize((SIZE, SIZE), Image.LANCZOS).save(OUT / f"{name}.png", optimize=True)
        im.resize((32, 32), Image.LANCZOS).save(OUT / f"{name}_32.png", optimize=True)
        print(f"{name}.png {SIZE}px, {name}_32.png 32px")


if __name__ == "__main__":
    main()
