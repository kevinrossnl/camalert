#!/usr/bin/env python3
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Images of the Chrome Web Store listing (#131): docs/dev/webstore/screenshot-*.png (1280x800) and the promo tiles.

    python3 tools/webstore_images.py            draws the demo cameras (tools/readme_images.py, never a real camera),
                                                takes the raw screenshots of the real extension in Chromium against
                                                the fake Home Assistant (players/web/tests/webstore/capture.mjs; needs
                                                `cd players/web && npm ci && npx playwright install chromium`) and
                                                composes the store images
    python3 tools/webstore_images.py --raw DIR  composes from raw screenshots that are already in DIR

Needs Pillow and numpy. Run `python3 tools/check_images.py --strip docs/dev/webstore/*.png` afterwards (privacy checklist:
docs/dev/privacy.md).
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import readme_images as art  # noqa: E402

OUT = os.path.join(ROOT, "docs", "dev", "webstore")
ICON = os.path.join(ROOT, "players", "web", "extension", "icon.png")
W, H = 1280, 800
BG_TOP, BG_BOTTOM = (28, 36, 52), (12, 16, 24)
ACCENT = (230, 159, 0)  # the CamAlert doorbell colour (style.PRIORITY_COLOURS high)
TEXT = (240, 242, 245)
SUB = (170, 180, 195)
CAMERAS = (("front_door", "Front door"), ("garden", "Garden"), ("driveway", "Driveway"), ("backyard", "Backyard"))


def gradient(w, h, top=BG_TOP, bottom=BG_BOTTOM):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def shadowed(canvas, img, x, y, radius=18):
    shadow = Image.new("RGBA", (img.width + 4 * radius, img.height + 4 * radius), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([2 * radius, 2 * radius, 2 * radius + img.width, 2 * radius + img.height],
                                     fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius))
    canvas.paste(shadow, (x - 2 * radius + 6, y - 2 * radius + 10), shadow)
    canvas.paste(img, (x, y))


def caption(canvas, title, sub=""):
    d = ImageDraw.Draw(canvas)
    d.text((64, 38), title, font=art.font(40, bold=True), fill=TEXT)
    if sub:
        d.text((64, 92), sub, font=art.font(22), fill=SUB)


def desktop():
    """A neutral drawn desktop with one plain document window (no real application, no brand)."""
    img = gradient(W, H, (52, 70, 96), (24, 32, 46))
    d = ImageDraw.Draw(img)
    d.rectangle([60, 150, 820, 740], fill=(245, 246, 248))
    d.rectangle([60, 150, 820, 186], fill=(214, 218, 224))
    for i, c in enumerate(((236, 95, 85), (240, 190, 70), (98, 196, 98))):
        d.ellipse([76 + i * 22, 162, 88 + i * 22, 174], fill=c)
    for i in range(12):
        w = 620 if i % 4 else 380
        d.rectangle([100, 220 + i * 40, 100 + w, 236 + i * 40], fill=(222, 226, 232))
    d.rectangle([0, H - 44, W, H], fill=(18, 22, 30))
    return img


def window_frame(raw, title="CamAlert"):
    """The alert window as the browser draws a popup: a thin title bar above the page."""
    bar = 30
    img = Image.new("RGB", (raw.width + 2, raw.height + bar + 1), (60, 64, 72))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, bar], fill=(222, 225, 230))
    d.text((12, 6), title, font=art.font(15), fill=(40, 44, 52))
    img.paste(raw, (1, bar))
    return img


def framed(raw, title, sub, box=(1088, 600)):
    canvas = gradient(W, H)
    caption(canvas, title, sub)
    im = raw.copy()
    im.thumbnail(box, Image.LANCZOS)
    shadowed(canvas, im, (W - im.width) // 2, 150 + (box[1] - im.height) // 2)
    return canvas


def compose(raw):
    out = {}
    canvas = desktop()
    caption(canvas, "Someone rings: the camera is on your screen", "A small window in the corner, with the chime")
    win = window_frame(Image.open(os.path.join(raw, "raw-doorbell.png")).convert("RGB"), "Front door")
    shadowed(canvas, win, W - win.width - 48, 150)
    out["screenshot-1-doorbell.png"] = canvas
    out["screenshot-2-mosaic.png"] = framed(Image.open(os.path.join(raw, "raw-mosaic.png")).convert("RGB"),
                                            "Every camera at once", "A mosaic from Home Assistant, an automation or MQTT")
    for name, title, sub, src in (
            ("screenshot-3-options.png", "Connects to your own Home Assistant",
             "Address and access token stay in this browser; several go2rtc servers", "raw-options.png"),
            ("screenshot-4-mqtt.png", "Or straight to your MQTT broker",
             "MQTT over WebSocket with Home Assistant discovery", "raw-options-mqtt.png")):
        page = Image.open(os.path.join(raw, src)).convert("RGB").crop((400, 0, 880, 800))
        canvas = gradient(W, H)
        caption(canvas, title, sub)
        page.thumbnail((440, 600), Image.LANCZOS)
        shadowed(canvas, page, (W - page.width) // 2, 160)
        out[name] = canvas
    return out


def promo(w, h, tagline=True):
    canvas = gradient(w, h, (36, 46, 66), (14, 18, 28))
    icon = Image.open(ICON).convert("RGBA")
    s = int(h * 0.46)
    icon = icon.resize((s, s), Image.LANCZOS)
    x = int(w * 0.07)
    canvas.paste(icon, (x, (h - s) // 2), icon)
    d = ImageDraw.Draw(canvas)
    tx = x + s + int(w * 0.05)
    room = w - tx - int(w * 0.05)

    def fitted(text, size, bold=False):  # the largest font up to size whose text fits the room
        while size > 8 and d.textlength(text, font=art.font(size, bold)) > room:
            size -= 1
        return art.font(size, bold)

    d.text((tx, int(h * 0.24)), "CamAlert", font=fitted("CamAlert", int(h * 0.2), True), fill=TEXT)
    d.rectangle([tx, int(h * 0.5), tx + int(w * 0.12), int(h * 0.5) + max(3, h // 70)], fill=ACCENT)
    if tagline:
        small = fitted("Your cameras on your screen", int(h * 0.075))
        d.text((tx, int(h * 0.57)), "Your cameras on your screen", font=small, fill=SUB)
        d.text((tx, int(h * 0.57 + h * 0.1)), "when someone rings", font=small, fill=SUB)
    return canvas


def capture(raw):
    cams = os.path.join(raw, "cams")
    os.makedirs(cams, exist_ok=True)
    for i, (name, title) in enumerate(CAMERAS):
        art.camera(name, title, i + 1, (960, 540)).convert("RGB").save(os.path.join(cams, name + ".jpg"), quality=88)
    subprocess.run(["node", "tests/webstore/capture.mjs", cams, raw], check=True,
                   cwd=os.path.join(ROOT, "players", "web"))


def main(argv):
    if len(argv) > 2 and argv[1] == "--raw":
        raw = argv[2]
    else:
        raw = tempfile.mkdtemp(prefix="camalert-webstore-")
        capture(raw)
    os.makedirs(OUT, exist_ok=True)
    images = compose(raw)
    images["promo-440x280.png"] = promo(440, 280)
    images["marquee-1400x560.png"] = promo(1400, 560)
    for name, img in images.items():
        img.convert("RGB").save(os.path.join(OUT, name), optimize=True)
        print(os.path.join("docs", "dev", "webstore", name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
