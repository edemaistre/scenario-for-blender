# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the modality icons (image, video, audio, 3d, text) and the prompt-tool icons (dice, sparkles, translate)
as glyphs matching the Scenario web app: 1.5 px strokes on a 16 px grid, light grey on transparent.

Usage: python3 tools/make_icons.py [--sheet review.png]
    needs Pillow; writes scenario/icons/<name>.png at 64 px and <name>_32.png at 32 px.
    --sheet also writes a contact sheet (16 px box-filtered like Blender does, 32, 64 and 8x blow-ups) for review.

Every icon is designed in 16 px units (what Blender shows at 1x UI scale), drawn at 8x the 64 px output on a
transparent canvas, then downscaled with Lanczos. Blender loads the 64 px files through bpy.utils.previews and
box-filters them down to the button size, so the 16 px preview in the sheet is the closest proxy of the real UI.
The Latin A of the translate icon is drawn with strokes like the rest of the set (the web app's glyph is a stroked A);
--font-a renders it with a font instead (DejaVu Sans, Blender's bundled Inter, Arial), which came out narrower and
denser than the 1.5 px strokes at 16 px, so it is opt-in."""
import argparse
import glob
import math
import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "scenario" / "icons"
COLOR = (230, 230, 230, 255)   # #E6E6E6
GRID = 16                      # design grid, in Blender 1x pixels
SIZE = 64                      # shipped size
SUPER = 8                      # supersampling of the shipped size
S = SIZE * SUPER               # working canvas, 512 px
U = S / GRID                   # canvas px per grid unit (32)
STROKE = 1.5                   # grid units, the web app's stroke at 16 px
W = STROKE * U

# proportional fonts first; Blender's bundled DejaVu is the monospaced one in recent releases, its A is condensed
FONT_CANDIDATES = [
    "/System/Library/Fonts/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    *sorted(glob.glob("/Applications/Blender*.app/Contents/Resources/*/datafiles/fonts/Inter.woff2"), reverse=True),
    *sorted(glob.glob("/Applications/Blender*.app/Contents/Resources/*/datafiles/fonts/DejaVuSans.woff2")),
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
    *sorted(glob.glob("/Applications/Blender*.app/Contents/Resources/*/datafiles/fonts/DejaVuSans*.woff2")),
]


# ---------------------------------------------------------------- drawing helpers (grid units in, canvas px out)

def P(x, y):
    return (x * U, y * U)


def canvas():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def dot(d, cx, cy, r, fill=COLOR):
    x, y, rr = cx * U, cy * U, r * U
    d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=fill)


def stroke(d, pts, width=STROKE, closed=False):
    """Polyline with round caps and round joins (a disc of the stroke diameter sits on every vertex)."""
    pts = list(pts)
    if closed:
        pts = pts + [pts[0]]
    d.line([P(x, y) for x, y in pts], fill=COLOR, width=round(width * U))
    for x, y in pts:
        dot(d, x, y, width / 2)


def rrect(d, x0, y0, x1, y1, radius, width=STROKE):
    d.rounded_rectangle((x0 * U, y0 * U, x1 * U, y1 * U), radius=radius * U, outline=COLOR, width=round(width * U))


def arc(d, cx, cy, r, start, end, width=STROKE):
    """Arc in degrees (PIL convention: 0 at 3 o'clock, clockwise on screen) with round caps. PIL draws the
    width inward from the bounding ellipse, so the box is grown by half a stroke to keep the centreline at r."""
    x, y, rr = cx * U, cy * U, (r + width / 2) * U
    d.arc((x - rr, y - rr, x + rr, y + rr), start=start, end=end, fill=COLOR, width=round(width * U))
    for a in (start, end):
        dot(d, cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)), width / 2)


def star(d, cx, cy, radius, waist=0.42, steps=24):
    """Filled four-point sparkle: tips on the axes, concave quadratic sides whose midpoint sits at waist * radius."""
    c = (waist * math.sqrt(2) - 0.5) * radius  # control point on the diagonal giving that waist
    tips = [(radius, 0), (0, radius), (-radius, 0), (0, -radius)]
    pts = []
    for i in range(4):
        (ax, ay), (bx, by) = tips[i], tips[(i + 1) % 4]
        sx, sy = math.copysign(c, ax + bx), math.copysign(c, ay + by)
        for k in range(steps):
            t = k / steps
            x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * sx + t ** 2 * bx
            y = (1 - t) ** 2 * ay + 2 * (1 - t) * t * sy + t ** 2 * by
            pts.append(P(cx + x, cy + y))
    d.polygon(pts, fill=COLOR)


def find_font():
    for path in FONT_CANDIDATES:
        try:
            ImageFont.truetype(path, 100)
            return path
        except OSError:
            continue
    return None


def glyph_mask(path, char, cap_height):
    """Render `char` with the font at `cap_height` grid units, thickened so its legs match STROKE.
    Returns an L mask at canvas resolution, tightly cropped."""
    probe = ImageFont.truetype(path, 400)
    l, t, r, b = probe.getbbox(char)
    font = ImageFont.truetype(path, round(400 * cap_height * U / (b - t)))

    def render(sw):
        l, t, r, b = font.getbbox(char, stroke_width=sw)
        pad = round(W)
        mask = Image.new("L", (r - l + 2 * pad, b - t + 2 * pad), 0)
        ImageDraw.Draw(mask).text((pad - l, pad - t), char, fill=255, font=font, stroke_width=sw, stroke_fill=255)
        return mask.crop(mask.getbbox())

    mask = render(0)

    def left_leg(frac):
        """(left edge x, horizontal run) of the first filled span on the row at `frac` of the height."""
        y = round(frac * (mask.height - 1))
        row = [mask.getpixel((x, y)) > 127 for x in range(mask.width)]
        x0 = row.index(True)
        x1 = x0
        while x1 < mask.width and row[x1]:
            x1 += 1
        return x0, x1 - x0

    # leg thickness measured perpendicular to the leg (its slope comes from two rows), then thicken to STROKE
    (xa, run), (xb, _) = left_leg(0.85), left_leg(0.65)
    dy = 0.2 * (mask.height - 1)
    thickness = run * dy / math.hypot(xa - xb, dy)
    extra = max(0, round((W - thickness) / 2))
    return render(extra) if extra else mask


def paste_mask(im, mask, cx, cy):
    im.paste(COLOR, (round(cx * U - mask.width / 2), round(cy * U - mask.height / 2)), mask)


# ---------------------------------------------------------------- modality icons

def icon_image():
    """Landscape frame, a sun and one mountain running to the frame."""
    im, d = canvas()
    rrect(d, 1.25, 3.0, 14.75, 13.0, 2.0)
    dot(d, 5.25, 6.5, 1.5)
    stroke(d, [(14.75, 10.75), (10.75, 6.75), (4.5, 13.0)])
    return im


def icon_video():
    """Camera body with a lens wedge on the right."""
    im, d = canvas()
    rrect(d, 1.25, 4.0, 10.75, 12.0, 1.75)
    stroke(d, [(10.75, 8.75), (14.5, 11.0), (14.5, 5.0), (10.75, 7.25)])
    return im


def icon_audio():
    """Speaker (box + cone) and two sound waves."""
    im, d = canvas()
    stroke(d, [(3.75, 5.5), (1.25, 5.5), (1.25, 10.5), (3.75, 10.5), (7.25, 12.75), (7.25, 3.25)], closed=True)
    arc(d, 8.25, 8.0, 3.25, -40, 40)
    arc(d, 8.25, 8.0, 6.25, -45, 45)
    return im


def icon_3d():
    """Cube seen from above: a hexagon with an inner Y to the upper corners and the bottom."""
    im, d = canvas()
    cx, cy, r = 8.0, 8.0, 6.75
    hexagon = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (270, 330, 30, 90, 150, 210)]
    stroke(d, hexagon, closed=True)
    for a in (210, 330, 90):  # upper-left, upper-right, bottom
        stroke(d, [(cx, cy), (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))])
    return im


def icon_text():
    """Page with a folded corner and three lines of text."""
    im, d = canvas()
    stroke(d, [(3.0, 1.5), (9.5, 1.5), (13.0, 5.0), (13.0, 14.5), (3.0, 14.5)], closed=True)
    stroke(d, [(9.5, 1.5), (9.5, 5.0), (13.0, 5.0)])
    stroke(d, [(5.5, 6.5), (7.25, 6.5)])
    stroke(d, [(5.5, 9.25), (10.5, 9.25)])
    stroke(d, [(5.5, 12.0), (10.5, 12.0)])
    return im


# ---------------------------------------------------------------- prompt tool icons

def icon_dice():
    """One rounded die with five pips (Scenario's 'Generate a new prompt')."""
    im, d = canvas()
    rrect(d, 1.5, 1.5, 14.5, 14.5, 2.6)
    for cx, cy in ((4.75, 4.75), (11.25, 4.75), (8.0, 8.0), (4.75, 11.25), (11.25, 11.25)):
        dot(d, cx, cy, 1.1)
    return im


def icon_sparkles():
    """One large sparkle with a small one top-right and a tiny one bottom-left (Scenario's 'Rewrite your prompt')."""
    im, d = canvas()
    star(d, 7.5, 8.5, 6.25)
    star(d, 13.0, 3.25, 2.5, waist=0.46)
    star(d, 2.75, 13.25, 2.0, waist=0.5)
    return im


def icon_translate(font=None):
    """A simplified 文 top-left and a Latin A bottom-right (Scenario's 'Translate to English')."""
    im, d = canvas()
    # 文: stem, bar, crossing legs
    stroke(d, [(5.0, 1.25), (5.0, 3.5)])
    stroke(d, [(1.25, 3.5), (8.75, 3.5)])
    stroke(d, [(3.0, 6.25), (7.0, 10.25)])
    stroke(d, [(7.0, 6.25), (3.0, 10.25)])
    # A
    if font:
        paste_mask(im, glyph_mask(font, "A", 6.5), 11.25, 11.25)
    else:
        stroke(d, [(8.0, 14.5), (11.25, 8.0), (14.5, 14.5)])
        stroke(d, [(9.25, 12.0), (13.25, 12.0)])
    return im


ICONS = {"image": icon_image, "video": icon_video, "audio": icon_audio, "3d": icon_3d, "text": icon_text,
         "dice": icon_dice, "sparkles": icon_sparkles, "translate": icon_translate}


def render_all(font):
    return {name: (fn(font) if name == "translate" else fn()) for name, fn in ICONS.items()}


def sheet(images, path):
    """Contact sheet on Blender's dark grey: 16 px (box filter, as Blender scales previews), 32, 64, then 16 and 64 blown up 8x."""
    names = list(images)
    cell, bg = 300, (48, 48, 48, 255)
    out = Image.new("RGBA", (cell * len(names), 320), bg)
    for i, name in enumerate(names):
        im64 = images[name].resize((SIZE, SIZE), Image.LANCZOS)
        im32 = images[name].resize((32, 32), Image.LANCZOS)
        im16 = im64.resize((16, 16), Image.BOX)
        x = i * cell + 10
        for im, dx in ((im16, 0), (im32, 26), (im64, 68)):
            out.alpha_composite(im, (x + dx, 10))
        out.alpha_composite(im16.resize((128, 128), Image.NEAREST), (x, 90))
        out.alpha_composite(im64.resize((128, 128), Image.NEAREST), (x + 150, 90))
        out.alpha_composite(im32.resize((64, 64), Image.NEAREST), (x + 150, 230))
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheet", type=pathlib.Path, help="also write a review contact sheet here")
    ap.add_argument("--font-a", action="store_true",
                    help="render the translate A with a font (Inter or DejaVu from Blender, Arial) instead of strokes")
    args = ap.parse_args()
    font = find_font() if args.font_a else None
    print(f"translate A: {font or 'strokes'}")
    OUT.mkdir(parents=True, exist_ok=True)
    images = render_all(font)
    for name, im in images.items():
        im.resize((SIZE, SIZE), Image.LANCZOS).save(OUT / f"{name}.png", optimize=True)
        im.resize((32, 32), Image.LANCZOS).save(OUT / f"{name}_32.png", optimize=True)
        print(f"{name}.png {SIZE}px, {name}_32.png 32px")
    if args.sheet:
        sheet(images, args.sheet)
        print(f"sheet {args.sheet}")


if __name__ == "__main__":
    main()
