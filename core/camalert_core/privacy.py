# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Privacy masks per camera and guest mode (#11).

Masks are rectangles in relative coordinates (0..1 of the camera picture) per camera:

    garden=0,0,0.3,0.5+0.7,0,1,0.4|front_door=0.6,0.6,1,1

Every player draws them as opaque black boxes on screen over the pictures it shows of that camera and over its
live video. The picture files themselves are not changed. Pictures that do not pass through CamAlert (Home
Assistant camera entities, phone notifications, go2rtc's own pages) are not masked.

Guest mode hides cameras: requests for them are ignored (reason "guest") and they are left out of the mosaic, the
tour and the camera lists of the player. An empty guest camera list means all cameras.
"""
import math
import struct

MAX_MASKS = 8  # per camera: the players reserve this many boxes per picture
GUEST = "guest"


def _num(text):
    v = float(text.strip().replace(",", "."))
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(text)
    return min(1.0, max(0.0, v))


def parse_masks(text):
    """'garden=0,0,0.3,0.5+0.7,0,1,0.4|front_door=0.6,0.6,1,1' -> {'garden': [(0.0, 0.0, 0.3, 0.5), ...]}.

    Corners in any order, values outside 0..1 are clamped, empty or broken rectangles are dropped, at most
    MAX_MASKS per camera. ';' also separates rectangles."""
    out = {}
    for part in (text or "").split("|"):
        name, sep, rects = part.partition("=")
        name = name.strip()
        if not sep or not name:
            continue
        boxes = out.get(name, [])
        for r in rects.replace(";", "+").split("+"):
            nums = r.replace(" ", "").split(",")
            if len(nums) != 4:
                continue
            try:
                x0, y0, x1, y1 = (_num(n) for n in nums)
            except ValueError:
                continue
            x0, x1 = min(x0, x1), max(x0, x1)
            y0, y1 = min(y0, y1), max(y0, y1)
            if x1 > x0 and y1 > y0:
                boxes.append((x0, y0, x1, y1))
        if boxes:
            out[name] = boxes[:MAX_MASKS]
    return out


def fit_rect(box, image_size=None):
    """(x, y, w, h) where a picture of image_size (w, h) is drawn inside box (x, y, w, h): aspect ratio kept and
    centred, as all players draw pictures and video. Without a known size: the whole box."""
    x, y, w, h = box
    if not image_size or image_size[0] <= 0 or image_size[1] <= 0 or w <= 0 or h <= 0:
        return (x, y, w, h)
    iw, ih = image_size
    scale = min(float(w) / iw, float(h) / ih)
    dw, dh = int(math.floor(iw * scale + 0.5)), int(math.floor(ih * scale + 0.5))  # half up, as Kotlin's Math.round
    return (x + (w - dw) // 2, y + (h - dh) // 2, dw, dh)


def mask_rects(name, masks, box, image_size=None):
    """Pixel rectangles (x, y, w, h) to cover on screen for camera `name` drawn in box; [] without masks.
    Rounded outwards, so a mask never leaves a visible line of the area it hides."""
    boxes = (masks or {}).get(name) or []
    if not boxes:
        return []
    fx, fy, fw, fh = fit_rect(box, image_size)
    out = []
    for x0, y0, x1, y1 in boxes:
        a, b = int(math.floor(fx + x0 * fw)), int(math.floor(fy + y0 * fh))
        c, d = min(int(math.ceil(fx + x1 * fw)), fx + fw), min(int(math.ceil(fy + y1 * fh)), fy + fh)
        if c > a and d > b:
            out.append((a, b, c - a, d - b))
    return out


SOF = (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)


def jpeg_size(data):
    """(width, height) of a JPEG (bytes), or None. Reads only the headers: no image library needed."""
    try:
        if not data or bytes(data[:2]) != b"\xff\xd8":
            return None
        data = bytearray(data)
        i, n = 2, len(data)
        while i + 4 <= n:
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                i += 2
                continue
            length = struct.unpack(">H", bytes(data[i + 2:i + 4]))[0]
            if marker in SOF:
                h, w = struct.unpack(">HH", bytes(data[i + 5:i + 9]))
                return (w, h) if w and h else None
            if marker == 0xDA or length < 2:
                return None
            i += 2 + length
    except (IndexError, struct.error, TypeError, ValueError):
        return None
    return None


def jpeg_file_size(path, limit=262144):
    """jpeg_size of a file (only its first bytes); None if unreadable."""
    try:
        with open(path, "rb") as f:
            return jpeg_size(f.read(limit))
    except (IOError, OSError):
        return None


def guest_cameras(text):
    """'garden|front_door' (also ',' or spaces) -> set of names; empty = all cameras."""
    return {x.strip() for x in (text or "").replace(",", "|").replace(" ", "|").split("|") if x.strip()}


def guest_hidden(name, guest_on, guest_text):
    """True when guest mode hides this camera (all cameras when the list is empty)."""
    if not guest_on:
        return False
    cams = guest_cameras(guest_text)
    return not cams or name in cams


def guest_visible(names, guest_on, guest_text):
    """names without the cameras guest mode hides (same order)."""
    return [n for n in names if not guest_hidden(n, guest_on, guest_text)]
