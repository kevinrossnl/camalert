#!/usr/bin/env python3
"""Draws the illustrations in docs/images/ (no real cameras, no real TV pictures).

    python3 tools/readme_images.py

Needs Pillow and numpy. Geometry follows players/enigma2/CamAlert/logic.py (window_geometry, grid).
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "players", "enigma2", "CamAlert"))
from logic import grid, window_geometry  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1920, 1080


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


# ---------------------------------------------------------------- camera scenes (drawn at 1280x720)
SW, SH = 1280, 720


def finish(img, seed, ir=True, stamp=None, stamp_y=10):
    """Camera look: IR grey, vignette, sensor noise, slight blur, timestamp."""
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(img.convert("L") if ir else img).astype(np.float32)
    yy, xx = np.mgrid[0:SH, 0:SW]
    r = np.sqrt(((xx - SW / 2) / (SW / 2)) ** 2 + ((yy - SH / 2) / (SH / 2)) ** 2)
    vign = np.clip(1.15 - 0.45 * r ** 2, 0.35, 1.0)
    rng = np.random.default_rng(seed)
    if a.ndim == 2:
        a = a * vign + rng.normal(0, 7, a.shape)
        out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGB")
    else:
        a = a * vign[..., None] + rng.normal(0, 6, a.shape)
        out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if stamp:
        d = ImageDraw.Draw(out)
        d.text((14, stamp_y), stamp, font=font(26, True), fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    return out


def glow(img, cx, cy, radius, strength):
    a = np.asarray(img).astype(np.float32)
    yy, xx = np.mgrid[0:SH, 0:SW]
    g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * radius ** 2))) * strength
    a = a + g[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def quad(d, pts, fill, outline=None):
    d.polygon(pts, fill=fill, outline=outline)


def plant(d, x, y, s, shade):
    rnd = random.Random(x * 7 + y)
    for _ in range(18):
        ox, oy = rnd.uniform(-1, 1) * s, rnd.uniform(-1.2, 0.2) * s
        r = rnd.uniform(0.25, 0.5) * s
        c = shade + rnd.randint(-18, 18)
        d.ellipse((x + ox - r, y + oy - r, x + ox + r, y + oy + r), fill=(c, c, c))


def scene_front_door():
    img = Image.new("RGB", (SW, SH), (40, 40, 40))
    d = ImageDraw.Draw(img)
    # wall with siding on the right, ground in perspective
    quad(d, [(0, 360), (SW, 330), (SW, SH), (0, SH)], (70, 70, 70))
    quad(d, [(860, 0), (SW, 0), (SW, SH), (930, SH)], (150, 145, 135))
    for i in range(0, 40):
        y = i * 22
        d.line([(860 + i * 0.0, y), (SW, y - 8)], fill=(120, 116, 108), width=3)
    # door
    quad(d, [(960, 120), (1120, 105), (1125, 560), (965, 590)], (55, 55, 58))
    quad(d, [(985, 150), (1100, 138), (1100, 300), (987, 310)], (110, 112, 118))
    d.ellipse((1088, 360, 1102, 374), fill=(200, 200, 200))
    # porch light
    d.rectangle((1150, 140, 1180, 190), fill=(235, 235, 235))
    # doormat and path tiles
    quad(d, [(900, 600), (1080, 585), (1110, 650), (900, 668)], (35, 35, 35))
    for row in range(9):
        y0 = 400 + row * 36
        y1 = y0 + 34
        x0a, x1a = 330 - row * 30, 760 + row * 26
        quad(d, [(x0a, y0), (x1a, y0 - 12), (x1a + 26, y1 - 12), (x0a - 30, y1)], (165 - row * 3,) * 3)
        for k in range(1, 4):
            t = k / 4
            xa = x0a + (x1a - x0a) * t
            d.line([(xa, y0 - 12 * t), (xa - 30 + 56 * t, y1 - 12 * t)], fill=(110, 110, 110), width=3)
    # gravel beds and plants
    quad(d, [(0, 450), (300, 420), (220, SH), (0, SH)], (95, 95, 95))
    for (x, y, s) in [(90, 470, 70), (200, 560, 90), (60, 640, 80), (830, 470, 60), (870, 560, 55)]:
        plant(d, x, y, s, 120)
    # pot by the door
    d.ellipse((1150, 560, 1250, 600), fill=(60, 60, 60))
    plant(d, 1200, 540, 45, 140)
    img = glow(img, 1165, 165, 160, 120)
    return img


def scene_garden():
    img = Image.new("RGB", (SW, SH), (30, 30, 30))
    d = ImageDraw.Draw(img)
    quad(d, [(0, 250), (SW, 230), (SW, SH), (0, SH)], (110, 110, 110))
    for i in range(14):  # mowing stripes
        x = -400 + i * 140
        quad(d, [(x, SH), (x + 70, SH), (640 + (x - 640) * 0.15 + 12, 240), (640 + (x - 640) * 0.15, 240)],
             (122, 122, 122) if i % 2 else (104, 104, 104))
    # fence
    for i in range(48):
        x = i * 28
        d.rectangle((x, 150, x + 22, 250), fill=(150, 150, 150) if i % 2 else (140, 140, 140))
    # trees and shed
    for (x, y, s) in [(160, 120, 120), (420, 90, 150), (1080, 110, 130)]:
        d.rectangle((x - 10, y + s * 0.5, x + 10, y + s * 1.3), fill=(60, 60, 60))
        plant(d, x, y + 40, s, 80)
    quad(d, [(700, 110), (900, 80), (930, 240), (700, 250)], (90, 90, 90))
    quad(d, [(690, 112), (800, 40), (912, 82)], (60, 60, 60))
    d.rectangle((760, 160, 820, 245), fill=(55, 55, 55))
    # bushes in front, garden lights
    for (x, y, s) in [(80, 640, 120), (1220, 620, 130), (980, 690, 90)]:
        plant(d, x, y, s, 70)
    for x in (300, 640, 980):
        img = glow(img, x, 300, 30, 90)
    return img


def scene_driveway():
    img = Image.new("RGB", (SW, SH), (35, 35, 35))
    d = ImageDraw.Draw(img)
    quad(d, [(0, 300), (SW, 300), (SW, SH), (0, SH)], (120, 120, 120))
    for i in range(12):  # paving lines
        y = 300 + i * i * 4.2
        d.line([(0, y), (SW, y)], fill=(100, 100, 100), width=2)
    for i in range(-8, 9):
        d.line([(640 + i * 40, 300), (640 + i * 190, SH)], fill=(100, 100, 100), width=2)
    # garage and door
    quad(d, [(380, 60), (900, 60), (900, 300), (380, 300)], (150, 150, 150))
    for i in range(6):
        d.rectangle((410, 90 + i * 35, 870, 118 + i * 35), fill=(170, 170, 170), outline=(120, 120, 120))
    # car (simple side-rear view)
    d.rounded_rectangle((420, 330, 860, 560), radius=60, fill=(210, 210, 210))
    d.rounded_rectangle((470, 280, 810, 400), radius=50, fill=(190, 190, 190))
    d.rounded_rectangle((500, 300, 780, 380), radius=30, fill=(60, 60, 60))
    for x in (440, 790):
        d.rounded_rectangle((x, 430, x + 50, 460), radius=8, fill=(250, 250, 250))
    d.rectangle((600, 470, 680, 500), fill=(240, 240, 240))
    for x in (440, 760):
        d.ellipse((x, 520, x + 90, 610), fill=(25, 25, 25))
    plant(d, 1150, 520, 120, 80)
    plant(d, 120, 560, 110, 85)
    img = glow(img, 640, 40, 220, 70)
    return img


def scene_backyard():
    img = Image.new("RGB", (SW, SH), (30, 30, 30))
    d = ImageDraw.Draw(img)
    quad(d, [(0, 280), (SW, 280), (SW, SH), (0, SH)], (130, 130, 130))
    for i in range(10):
        y = 280 + i * i * 5
        d.line([(0, y), (SW, y)], fill=(105, 105, 105), width=2)
    for i in range(-7, 8):
        d.line([(640 + i * 60, 280), (640 + i * 200, SH)], fill=(105, 105, 105), width=2)
    # hedge
    for x in range(0, SW, 60):
        plant(d, x + 30, 250, 60, 70)
    # table and chairs
    d.ellipse((480, 380, 800, 460), fill=(190, 190, 190))
    d.rectangle((630, 420, 650, 560), fill=(150, 150, 150))
    for (x, y) in [(400, 420), (840, 420), (520, 520), (720, 520)]:
        d.rectangle((x, y, x + 70, y + 80), fill=(160, 160, 160))
        d.rectangle((x, y - 60, x + 70, y), fill=(140, 140, 140))
    # parasol
    d.polygon([(640, 140), (420, 260), (860, 260)], fill=(170, 170, 170))
    d.line([(640, 140), (640, 400)], fill=(120, 120, 120), width=6)
    img = glow(img, 1180, 120, 140, 90)
    return img


SCENES = {"front_door": scene_front_door, "garden": scene_garden, "driveway": scene_driveway, "backyard": scene_backyard}


def camera(name, title, seed, size, stamp_time="21:05:12", stamp_y=10):
    img = finish(SCENES[name](), seed, stamp="2026-01-01 %s  %s" % (stamp_time, title), stamp_y=stamp_y)
    return img.resize(size, Image.LANCZOS)


# ---------------------------------------------------------------- TV picture: own colourful test pattern
def test_pattern():
    img = Image.new("RGB", (W, H), (20, 24, 40))
    a = np.zeros((H, W, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    a[..., 0] = 40 + 60 * (xx / W)
    a[..., 1] = 50 + 40 * (yy / H)
    a[..., 2] = 110 + 60 * (1 - xx / W)
    img = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(img)
    colours = [(240, 240, 240), (235, 210, 40), (40, 200, 220), (60, 200, 80), (220, 60, 200), (220, 60, 50),
               (40, 70, 220), (25, 25, 25)]
    bw = 1200 // len(colours)
    for i, c in enumerate(colours):
        d.rectangle((360 + i * bw, 330, 360 + (i + 1) * bw, 650), fill=c)
    for i in range(12):  # grey steps
        g = int(i * 255 / 11)
        d.rectangle((360 + i * 100, 650, 360 + (i + 1) * 100, 740), fill=(g, g, g))
    for r in range(80, 520, 60):  # rings
        d.ellipse((960 - r, 540 - r, 960 + r, 540 + r), outline=(255, 255, 255), width=2)
    d.line([(960, 20), (960, 1060)], fill=(255, 255, 255), width=2)
    d.line([(20, 540), (1900, 540)], fill=(255, 255, 255), width=2)
    for x in range(0, W, 120):  # frame ticks
        d.rectangle((x, 0, x + 60, 18), fill=(255, 255, 255))
        d.rectangle((x + 60, H - 18, x + 120, H), fill=(255, 255, 255))
    d.rounded_rectangle((720, 790, 1200, 880), radius=14, fill=(15, 15, 25))
    d.text((960, 835), "TEST  CHANNEL", font=font(44, True), fill=(255, 255, 255), anchor="mm")
    d.rounded_rectangle((760, 200, 1160, 290), radius=14, fill=(15, 15, 25))
    d.text((960, 245), "21:05", font=font(52, True), fill=(255, 255, 255), anchor="mm")
    return img


# ---------------------------------------------------------------- images
def hero():
    img = test_pattern()
    x, y, w, h, t = window_geometry("top_right", "medium", W, H)
    d = ImageDraw.Draw(img)
    d.rectangle((x, y, x + w - 1, y + t - 1), fill=(0x20, 0x20, 0x20))
    d.text((x + 10, y + t // 2), "Front door   OK = live  ◀ ▶  EXIT", font=font(26), fill=(255, 255, 255), anchor="lm")
    img.paste(camera("front_door", "Front door", 1, (w, h)), (x, y + t))
    return img


def mosaic():
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    top = 50
    d.text((20, 8), "Cameras  ·  EXIT = close", font=font(28), fill=(255, 255, 255))
    names = [("front_door", "Front door"), ("garden", "Garden"), ("driveway", "Driveway"), ("backyard", "Backyard")]
    for i, ((x, y, w, h), (n, title)) in enumerate(zip(grid(4, W, H - top), names)):
        img.paste(camera(n, title, 10 + i, (w, h), "21:05:%02d" % (10 + i)), (x, y + top))
        ov = Image.new("RGBA", (w // 2, 34), (0, 0, 0, 128))
        img.paste(ov, (x + 8, y + top + 8 + 40), ov)
        ImageDraw.Draw(img).text((x + 14, y + top + 8 + 40 + 17), " %s " % title, font=font(24),
                                 fill=(255, 255, 255), anchor="lm")
    return img


def tour():
    img = camera("garden", "Garden", 30, (W, H), "21:06:40", stamp_y=675)
    ov = Image.new("RGBA", (W - 60, 46), (0, 0, 0, 128))
    img.paste(ov, (30, 20), ov)
    ImageDraw.Draw(img).text((30, 43), " Garden   (2/4, tour)   ◀ ▶  OK  GREEN = live  EXIT ", font=font(30),
                             fill=(255, 255, 255), anchor="lm")
    return img


def flow():
    img = Image.new("RGB", (W, 900), (250, 251, 253))
    d = ImageDraw.Draw(img)

    def box(x, y, w, h, title, sub, colour):
        d.rounded_rectangle((x + 6, y + 8, x + w + 6, y + h + 8), radius=22, fill=(220, 224, 232))
        d.rounded_rectangle((x, y, x + w, y + h), radius=22, fill=(255, 255, 255), outline=colour, width=5)
        d.rounded_rectangle((x, y, x + w, y + 64), radius=22, fill=colour)
        d.rectangle((x, y + 40, x + w, y + 64), fill=colour)
        d.text((x + w / 2, y + 33), title, font=font(34, True), fill=(255, 255, 255), anchor="mm")
        for i, line in enumerate(sub):
            d.text((x + w / 2, y + 104 + i * 40), line, font=font(26), fill=(40, 48, 64), anchor="mm")
        return (x, y, w, h)

    def arrow(p, q, label, colour=(70, 80, 100), above=True):
        d.line([p, q], fill=colour, width=6)
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        for s in (-1, 1):
            d.line([q, (q[0] - 28 * math.cos(ang + s * 0.45), q[1] - 28 * math.sin(ang + s * 0.45))], fill=colour, width=6)
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        if label:
            d.text((mx, my - 26 if above else my + 26), label, font=font(24, True), fill=colour, anchor="mm")

    blue, green, orange, purple = (52, 110, 200), (40, 150, 100), (220, 120, 40), (130, 80, 190)
    d.text((W / 2, 50), "How CamAlert fits together", font=font(44, True), fill=(30, 36, 50), anchor="mm")
    box(60, 160, 330, 260, "Cameras", ["UniFi, Reolink,", "Hikvision, Dahua,", "Tapo, Axis, ..."], (90, 100, 120))
    box(560, 160, 360, 260, "go2rtc", ["one link per camera", "RTSP + snapshots", "(optional)"], blue)
    box(1090, 160, 360, 260, "Receiver", ["Enigma2 + CamAlert", "photo window, live,", "mosaic, tour"], green)
    box(1580, 160, 280, 260, "TV", ["camera on screen", "while you watch"], (60, 60, 70))
    box(1090, 560, 360, 260, "Home Assistant", ["CamAlert integration", "blueprints, MQTT"], orange)
    box(560, 560, 360, 260, "Sensors", ["motion, person,", "doorbell, alarm"], purple)
    arrow((390, 290), (560, 290), "RTSP")
    arrow((920, 290), (1090, 290), "RTSP / JPEG")
    arrow((1450, 290), (1580, 290), "HDMI")
    arrow((920, 690), (1090, 690), "events")
    arrow((1270, 560), (1270, 420), "")
    d.text((1290, 490), "show / mosaic / hide", font=font(24, True), fill=(70, 80, 100), anchor="lm")
    d.text((W / 2, 870), "Without go2rtc the receiver can also talk to the cameras directly.", font=font(24),
           fill=(90, 98, 115), anchor="mm")
    return img


def save(img, name):
    path = os.path.join(OUT, name)
    if name.endswith(".jpg"):
        img.convert("RGB").save(path, quality=86, optimize=True, progressive=True)
    else:
        img.convert("RGB").quantize(colors=128, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG).save(path, optimize=True)
    print(name, os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    save(hero(), "hero.jpg")
    save(mosaic(), "mosaic.jpg")
    save(tour(), "tour.jpg")
    save(flow(), "flow.png")
