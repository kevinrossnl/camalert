#!/usr/bin/env python3
"""Draws the Home Assistant brand images of the integration (#23): the CamAlert icon (a TV with a camera window in
the corner, the same design as the Kodi add-on icon) on a transparent background.

    make_brand.py [outdir]     default: custom_components/camalert/brand/

Writes icon.png (256x256) and icon@2x.png (512x512). HACS accepts a brand/ folder with icon.png instead of an entry
in home-assistant/brands; Home Assistant 2026.3 and newer shows it (older versions use the brands CDN).
Needs Pillow. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "custom_components", "camalert", "brand")
FRAME = (232, 238, 244, 255)
SCREEN = (31, 39, 53, 255)
BADGE = (240, 172, 44, 255)
DOT = (229, 57, 53, 255)
SUPER = 4  # draw 4x larger, then scale down: smooth edges without anti-aliasing support in ImageDraw


def draw(size):
    s = size * SUPER / 256.0
    img = Image.new("RGBA", (size * SUPER, size * SUPER), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1):
        return [round(x0 * s), round(y0 * s), round(x1 * s), round(y1 * s)]

    d.rounded_rectangle(box(16, 40, 240, 192), radius=round(18 * s), fill=FRAME)        # TV frame
    d.rounded_rectangle(box(32, 56, 224, 176), radius=round(8 * s), fill=SCREEN)        # screen
    d.rectangle(box(112, 192, 144, 212), fill=FRAME)                                    # neck
    d.rounded_rectangle(box(76, 206, 180, 220), radius=round(7 * s), fill=FRAME)       # foot
    d.rounded_rectangle(box(128, 68, 214, 124), radius=round(6 * s), fill=BADGE)       # camera window
    d.rounded_rectangle(box(142, 82, 182, 110), radius=round(5 * s), fill=SCREEN)      # camera body
    d.polygon([(round(180 * s), round(96 * s)), (round(200 * s), round(82 * s)), (round(200 * s), round(110 * s))],
              fill=SCREEN)                                                              # lens
    d.ellipse(box(199, 70, 209, 80), fill=DOT)                                          # recording dot
    return img.resize((size, size), Image.LANCZOS)


def build(outdir=OUT):
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        path = os.path.join(outdir, name)
        draw(size).save(path, optimize=True)  # Pillow writes no metadata for a new image
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in build(sys.argv[1] if len(sys.argv) > 1 else OUT):
        print(p)
