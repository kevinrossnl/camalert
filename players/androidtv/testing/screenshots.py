#!/usr/bin/env python3
"""Docs screenshots of the Android TV player with demo cameras (#69), over adb. Never a real camera picture.

    python3 players/androidtv/testing/screenshots.py --serial 192.168.1.30:5555 --out shots/ [--token-env CAMALERT_TOKEN]
                                                     [--scenes photo,strip,mosaic,tour,settings] [--adb adb]
                                                     [--restore-server http://192.168.1.5:1984]

The app's go2rtc address must point at the fake go2rtc ON the device (http://127.0.0.1:11984, see
fake_go2rtc_on_device.py, which this tool starts and stops). With CamAlert 1.3+ give --restore-server (the app's
own go2rtc address): the tool switches with /camalert/setup (#122) and sends that address back at the end, also
after an error. Without it, change the address in the app's settings by hand and put it back afterwards (the tool
cannot read it: settings are private to the app). Never on a device
someone watches; the tool takes the per-device test lock (/data/local/tmp/camalert-test.lock, younger than 20 min
= busy) and gives it back. Every request carries test=1 (no chime). Nothing is muted.

Per scene the CamAlert API opens the screen, `adb exec-out screencap -p` takes the picture and the tool crops it:
photo window and multi-camera window to CamAlert's own window (from camalert_core.layout and the position/size
the player reports), so the launcher behind it (third-party content) never ends up in the docs; mosaic, tour and
settings are full screen. Every file then goes through tools/check_images.py --strip. Review them before use.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "core"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from camalert_core import layout  # noqa: E402
import fake_go2rtc_on_device as fake  # noqa: E402

LOCK = "/data/local/tmp/camalert-test.lock"
LOCK_MAX_AGE = 20 * 60
SCENES = ("photo", "strip", "mosaic", "tour", "settings")
CAMS = ("front_door", "garden", "driveway", "back_door")
SETTINGS_ACTIVITY = "org.camalert.tv/.SettingsActivity"


class Busy(Exception):
    """Another test holds the device lock."""


class Device(object):
    def __init__(self, serial, adb="adb", run=subprocess.run, now=time.time):
        self.serial, self.adb, self.run, self.now = serial, adb, run, now
        self.host = serial.split(":")[0]

    def shell(self, cmd):
        out = self.run([self.adb, "-s", self.serial, "shell", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return out.stdout.decode("utf-8", "replace") if isinstance(out.stdout, bytes) else (out.stdout or "")

    def screencap(self):
        out = self.run([self.adb, "-s", self.serial, "exec-out", "screencap", "-p"], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
        if not out.stdout.startswith(b"\x89PNG"):
            raise RuntimeError("screencap gave no PNG")
        return out.stdout

    def take_lock(self, who="screenshots"):
        text = self.shell("cat %s 2>/dev/null; echo; date +%%s" % LOCK).strip().splitlines()
        now = int(text[-1]) if text and text[-1].strip().isdigit() else int(self.now())
        held = [x for x in text[:-1] if x.strip()]
        if held:
            parts = held[0].split()
            since = int(parts[-1]) if parts and parts[-1].isdigit() else now
            if now - since < LOCK_MAX_AGE:
                raise Busy("device busy: %s" % held[0])
        self.shell("echo '%s %d' > %s" % (who, now, LOCK))

    def free_lock(self):
        self.shell("rm -f %s" % LOCK)


class Api(object):
    def __init__(self, host, token="", port=8099, opener=urllib.request.urlopen):
        self.base, self.token, self.opener = "http://%s:%d/camalert/" % (host, port), token, opener

    def call(self, name, **params):
        data = json.dumps(dict(params, test="1")).encode() if params or name not in ("status", "cameras") else None
        req = urllib.request.Request(self.base + name, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("X-CamAlert-Token", self.token)
        with self.opener(req, timeout=10) as r:
            return json.loads(r.read().decode())


def crop_box(scene, status, width, height):
    """(x0, y0, x1, y1) of CamAlert's own window on a width x height screenshot, None = full screen."""
    if scene == "photo":
        x, y, w, h, title = layout.window_geometry(status.get("position") or "top_right",
                                                   status.get("size") or "medium", width, height)
        pad = max(4, width // 160)
        return (max(0, x - pad), max(0, y - pad), min(width, x + w + pad), min(height, y + h + title + pad))
    if scene == "strip":
        x, y, w, h, title = layout.window_geometry(status.get("position") or "top_right",
                                                   status.get("size") or "medium", width, height)
        pad = max(4, width // 160)
        return (max(0, x - pad), max(0, y - pad), min(width, x + w + pad), min(height, y + 2 * (h + title) + pad))
    return None


FRAME = re.compile(r"mFrame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
BOUNDS = re.compile(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')
SETTINGS_PANEL = "org.camalert.tv:id/settings_preference_fragment_container"


def overlay_frame(dumpsys):
    """(x0, y0, x1, y1) of CamAlert's overlay window ("Window{... CamAlert}") in `dumpsys window windows`, or None.
    The real frame: the core's window_geometry differs from what Android lays out (title bar, hint line)."""
    block = None
    for line in dumpsys.splitlines():
        if "Window{" in line:
            block = line.rstrip().endswith(" CamAlert}:")
        elif block:
            m = FRAME.search(line)
            if m:
                return tuple(int(v) for v in m.groups())
    return None


def panel_frame(ui_xml):
    """(x0, y0, x1, y1) of the settings panel in a uiautomator dump, or None. The settings screen fills the whole
    display with the launcher (third-party content) visible next to the panel."""
    for node in re.findall(r"<node [^>]*>", ui_xml):
        if 'resource-id="%s"' % SETTINGS_PANEL in node:
            m = BOUNDS.search(node)
            if m:
                return tuple(int(v) for v in m.groups())
    return None


def measured_box(scene, dev):
    """The crop box measured on the device, None when it cannot be measured (then crop_box computes it)."""
    try:
        if scene in ("photo", "strip"):
            return overlay_frame(dev.shell("dumpsys window windows"))
        if scene == "settings":
            return panel_frame(dev.shell("uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1; "
                                         "cat /data/local/tmp/ui.xml; rm -f /data/local/tmp/ui.xml"))
    except Exception:  # noqa: BLE001 - fall back to the computed box
        return None
    return None


def strip_file(path):
    """tools/check_images.py --strip for one file: removes metadata in place, pixels untouched."""
    import check_images
    with open(path, "rb") as f:
        data = f.read()
    with open(path, "wb") as f:
        f.write(check_images.strip(data))


def crop(png, box):
    if box is None:
        return png
    from PIL import Image
    img = Image.open(io.BytesIO(png)).crop(box)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def open_scene(scene, api, dev):
    if scene == "photo":
        api.call("show", cam=CAMS[0], mode="photo", sec=60, priority="normal", label="Person")
    elif scene == "strip":
        api.call("show", cam=",".join(CAMS[:3]), mode="strip", sec=60, priority="normal")
    elif scene == "mosaic":
        api.call("mosaic", cam=",".join(CAMS), sec=60)
    elif scene == "tour":
        api.call("tour", cam=",".join(CAMS[:2]), interval=30)
    elif scene == "settings":
        dev.shell("am start -n %s" % SETTINGS_ACTIVITY)
    else:
        raise ValueError(scene)


def close_scene(scene, api, dev):
    api.call("hide")
    if scene == "settings":
        dev.shell("input keyevent KEYCODE_BACK")


def take(dev, api, scenes, out, wait=4.0, sleep=time.sleep, strip=None, restore_server=None):
    """Takes the scenes into out/<scene>.png; returns the written files. Always hides and frees the lock; with
    restore_server the app is pointed at the fake go2rtc first and at restore_server again at the end."""
    if strip is None:
        strip = strip_file
    os.makedirs(out, exist_ok=True)
    written = []
    dev.take_lock()
    try:
        if restore_server:
            api.call("setup", server="http://127.0.0.1:%d" % fake.PORT)
            for _ in range(20):
                if CAMS[0] in [c.get("name") for c in (api.call("cameras").get("cameras") or [])]:
                    break
                sleep(0.5)
        status = api.call("status")
        for scene in scenes:
            open_scene(scene, api, dev)
            try:
                sleep(wait)
                png = dev.screencap()
                from PIL import Image
                w, h = Image.open(io.BytesIO(png)).size
                path = os.path.join(out, "%s.png" % scene)
                box = measured_box(scene, dev) or crop_box(scene, status, w, h)
                if box is None and scene == "settings":
                    raise RuntimeError("settings panel not found: refusing a full-screen picture of the launcher")
                with open(path, "wb") as f:
                    f.write(crop(png, box))
                if strip is not None:
                    strip(path)
                written.append(path)
            finally:
                close_scene(scene, api, dev)
                sleep(1.0)
    finally:
        try:
            api.call("hide")
            if restore_server:
                api.call("setup", server=restore_server)
        finally:
            dev.free_lock()
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serial", required=True)
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--out", required=True)
    ap.add_argument("--token-env", default="", help="environment variable with the CamAlert access token")
    ap.add_argument("--scenes", default=",".join(SCENES))
    ap.add_argument("--restore-server", default="", help="the app's own go2rtc address (CamAlert 1.3+): switch to "
                    "the fake with /camalert/setup and back to this address at the end")
    a = ap.parse_args(argv)
    scenes = [s for s in a.scenes.split(",") if s]
    bad = [s for s in scenes if s not in SCENES]
    if bad:
        print("unknown scene(s): %s" % ", ".join(bad))
        return 2
    subprocess.call([a.adb, "connect", a.serial], stdout=subprocess.DEVNULL)
    dev = Device(a.serial, a.adb)
    api = Api(dev.host, os.environ.get(a.token_env, "") if a.token_env else "")
    fake.main(["start", "--serial", a.serial, "--adb", a.adb])
    try:
        files = take(dev, api, scenes, a.out, restore_server=a.restore_server or None)
    except Busy as e:
        print(e)
        return 1
    finally:
        fake.main(["stop", "--serial", a.serial, "--adb", a.adb])
    print("\n".join(files))
    print("review every picture (privacy checklist, docs/dev/privacy.md) before it goes into the docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
