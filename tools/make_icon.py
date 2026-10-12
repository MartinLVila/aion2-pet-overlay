"""Draws the app icon: a paw inside a ring split 5 : 25 : 75, like the level bar.

Writes assets/icon.ico (16-256 px, for the exe, window and taskbar) and assets/icon.png (tray).

    python tools/make_icon.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SURFACE, LINE, ACCENT, TEXT = "#121821", "#283345", "#7adfd0", "#e6ebf2"
S = 1024  # drawn large, then downsampled for clean edges


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = S / 64  # the design is laid out on a 64-unit grid, same as the UI's SVG
    d.rounded_rectangle((1 * k, 1 * k, 63 * k, 63 * k), radius=15 * k, fill=SURFACE, outline=LINE, width=round(2 * k))

    # ring: three arcs sized 5 : 25 : 75 with 10 degree gaps; the big one 55% filled
    r, width = 23 * k, 5.5 * k
    a, b, c = (330 * n / 105 for n in (5, 25, 75))
    t = -90 + 5
    s1 = (t, t + a); t += a + 10
    s2 = (t, t + b); t += b + 10
    s3 = (t, t + c)
    fill = s3[0] + c * .55
    for (start, end), color in ((s1, ACCENT), (s2, ACCENT), ((s3[0], fill), ACCENT), ((fill + 7, s3[1]), LINE)):
        arc(d, 32 * k, 32 * k, r, start, end, width, color)

    for cx, cy, rx, ry, rot in ((32, 37.5, 7.6, 6.4, 0), (23.6, 30.5, 2.9, 3.6, -18), (28.6, 25.4, 2.9, 3.7, 0),
                                (35.4, 25.4, 2.9, 3.7, 0), (40.4, 30.5, 2.9, 3.6, 18)):
        ellipse(img, cx * k, cy * k, rx * k, ry * k, rot, TEXT)
    return img


def arc(d, cx, cy, r, start, end, width, color):
    """Flat-ended arc, so the gaps between the 5 / 25 / 75 segments stay visible."""
    d.arc((cx - r, cy - r, cx + r, cy + r), start, end, fill=color, width=round(width))


def ellipse(img, cx, cy, rx, ry, rotation, color):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=color)
    if rotation:
        layer = layer.rotate(-rotation, center=(cx, cy), resample=Image.BICUBIC)
    img.alpha_composite(layer)


def main():
    big = draw()
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "assets", "icon.ico"), sizes=[(s, s) for s in sizes])
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "assets", "icon.png"))
    print("assets/icon.ico, assets/icon.png")


if __name__ == "__main__":
    main()
