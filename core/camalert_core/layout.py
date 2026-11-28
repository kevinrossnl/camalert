# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Window and tile geometry, designed for 1920x1080 and scaled to the screen."""


POSITIONS = ("top_right", "top_left", "bottom_right", "bottom_left")
SIZES = {"small": (480, 270), "medium": (640, 360), "large": (960, 540)}
TITLE_SIZES = {"small": (32, 22), "normal": (40, 26), "large": (56, 38)}  # (title bar height, font) at 1080p
# Text size of every CamAlert screen (#48): titles, hints, camera control, tour, mosaic labels, lists.
TEXT_SIZES = {"normal": 1.0, "large": 1.25, "xlarge": 1.5}


def text_scale(text_size):
    """Factor for every font (and the title bar) of CamAlert's screens (#48); 1.0 for an unknown value."""
    return TEXT_SIZES.get(text_size, 1.0)


def font_px(px_1080, screen_w, text_size="normal"):
    """A font size designed at 1080p, scaled to the screen and the text size setting (#48)."""
    return int(px_1080 * screen_w / 1920.0 * text_scale(text_size))


def title_font(title_size, screen_w, text_size="normal"):
    return font_px(TITLE_SIZES.get(title_size, TITLE_SIZES["normal"])[1], screen_w, text_size)


def window_geometry(position, size, screen_w, screen_h, title_size="normal", text_size="normal", slot=0):
    """(x, y, w, h, title_h) for the photo window, scaled from a 1920x1080 design; the title bar grows with the
    text size (#48). slot > 0 (#87, several windows at once): the next place from the corner towards the screen
    centre (top corners downwards, bottom corners upwards); a full column continues in the next column inwards."""
    f = screen_w / 1920.0
    w, h = SIZES.get(size, SIZES["medium"])
    w, h = int(w * f), int(h * f)
    title = int(TITLE_SIZES.get(title_size, TITLE_SIZES["normal"])[0] * f * text_scale(text_size))
    margin = int(40 * f)
    total_h = h + title
    x = margin if position in ("top_left", "bottom_left") else screen_w - w - margin
    y = margin if position in ("top_left", "top_right") else screen_h - total_h - margin
    if slot > 0:
        x, y = slot_position(slot, position, x, y, w, total_h, screen_w, screen_h, margin, int(16 * f))
    return x, y, w, h, title


def slot_position(slot, position, x, y, w, total_h, screen_w, screen_h, margin, gap):
    """(x, y) of window place `slot` (0 = the corner itself) for a window of w x total_h at (x, y) (#87)."""
    rows = max(1, (screen_h - 2 * margin + gap) // (total_h + gap))
    col, row = divmod(int(slot), rows)
    down = position in ("top_left", "top_right")
    right = position in ("top_left", "bottom_left")
    y = y + row * (total_h + gap) if down else y - row * (total_h + gap)
    x = x + col * (w + gap) if right else x - col * (w + gap)
    return max(0, min(x, screen_w - w)), max(0, min(y, screen_h - total_h))


def grid(n, screen_w, screen_h, gap=8):
    """Tiles (x, y, w, h) for n cameras in a 1x1, 2x2 or 3x3 grid with 16:9 tiles, centred on the screen."""
    cols = 1 if n <= 1 else 2 if n <= 4 else 3
    rows = (n + cols - 1) // cols
    w = (screen_w - gap * (cols + 1)) // cols
    h = w * 9 // 16
    if h * rows + gap * (rows + 1) > screen_h:
        h = (screen_h - gap * (rows + 1)) // rows
        w = h * 16 // 9
    x0 = (screen_w - (w * cols + gap * (cols - 1))) // 2
    y0 = (screen_h - (h * rows + gap * (rows - 1))) // 2
    return [(x0 + (i % cols) * (w + gap), y0 + (i // cols) * (h + gap), w, h) for i in range(n)]


STRIP_LAYOUTS = ("auto", "vertical", "horizontal", "grid")


def strip_layout(n, layout="auto"):
    if layout in ("vertical", "horizontal", "grid"):
        return layout
    return "grid" if n >= 4 else "vertical"


def strip_geometry(n, layout, position, size, screen_w, screen_h, text_size="normal"):
    """One corner window with n (2..4) cameras. Returns (x, y, w, h, title_h, tiles) where tiles are (x, y, w, h)
    relative to the window. Tiles use the photo window size and shrink to fit at most 90% of the screen."""
    n = max(1, min(4, n))
    lay = strip_layout(n, layout)
    cols, rows = {"vertical": (1, n), "horizontal": (n, 1), "grid": (2, (n + 1) // 2)}[lay]
    f = screen_w / 1920.0
    tw, th = SIZES.get(size, SIZES["medium"])
    tw, th = int(tw * f), int(th * f)
    gap, title, margin = max(2, int(6 * f)), int(40 * f * text_scale(text_size)), int(40 * f)
    max_w, max_h = int(screen_w * 0.9) - margin, int(screen_h * 0.9) - margin
    scale = min(1.0, (max_w - gap * (cols - 1)) / float(tw * cols), (max_h - title - gap * (rows - 1)) / float(th * rows))
    tw, th = int(tw * scale), int(th * scale)
    w, h = tw * cols + gap * (cols - 1), th * rows + gap * (rows - 1)
    x = margin if position in ("top_left", "bottom_left") else screen_w - w - margin
    y = margin if position in ("top_left", "top_right") else screen_h - h - title - margin
    tiles = [((i % cols) * (tw + gap), title + (i // cols) * (th + gap), tw, th) for i in range(n)]
    return x, y, w, h, title, tiles
