#!/usr/bin/env python3
"""Generates the colour-coded test pictures of tests/fakes/camera.py (#32) into a folder, plus an optional clip.

    make_test_media.py OUT_DIR [--count 4] [--width 640] [--clip]

cam1.jpg .. camN.jpg (PNG without Pillow): solid colour with a big white index number, no metadata (#8).
--clip also writes test.mp4 (5 s ffmpeg testsrc, 320x180, needs ffmpeg). Nothing here is a real picture, so the
outputs may be committed (keep them tiny) or uploaded to a device for screenshots.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tests", "fakes"))
from camera import colour_frame  # noqa: E402


def make(out_dir, count=4, width=640, clip=False):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for i in range(1, count + 1):
        ctype, data = colour_frame(i, width)
        path = os.path.join(out_dir, "cam%d.%s" % (i, "jpg" if ctype == "image/jpeg" else "png"))
        with open(path, "wb") as f:
            f.write(data)
        written.append(path)
    if clip:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise SystemExit("--clip needs ffmpeg")
        path = os.path.join(out_dir, "test.mp4")
        subprocess.check_call([ffmpeg, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                               "testsrc=duration=5:size=320x180:rate=10", "-map_metadata", "-1",
                               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", path])
        written.append(path)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--clip", action="store_true")
    a = ap.parse_args()
    for p in make(a.out, a.count, a.width, a.clip):
        print(p)
