# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Windows: photo window (one camera or a strip of 2-4), full-screen mosaic and tour."""
import os
import threading
import time

import xbmcgui

from . import kodiapi, sources
from .klogic import (PTZ_TOGGLE as TOGGLE_IDS, SCREEN_H, SCREEN_W, colour_name, forward_builtin, frame_name, key_action,
                     live_key, mosaic_key, ptz_action, title_font_name, tour_key)
from .camalert_core.cameras import parse_orientation, parse_refresh, refresh_delay
from .camalert_core.events import event_title
from .camalert_core.present import key_hint, tour_status
from .camalert_core.layout import grid, strip_geometry, window_geometry

WHITE = None
ANIM = {"rot180": "effect=rotate end=180 center=auto", "mirror": "effect=rotatey end=180 center=auto",
        "flip": "effect=rotatex end=180 center=auto"}
VOLUME_KEYS = {88: "Action(VolumeUp)", 89: "Action(VolumeDown)", 91: "Action(Mute)"}
# Arrow glyphs in key hints (#41): Estuary's NotoSans-Regular has no U+25C0/U+25B6 (checked on Kodi 21.3, only
# arial.ttf of the Arial fontset has them) and Kodi does not fall back to another font, so Kodi uses < > ^ v.
GLYPHS = False


def hint(context, s=None, has_ptz=False):
    """Translated key hint of a screen, built from the key map (camalert_core.present, #41)."""
    return key_hint("kodi", context, kodiapi.core_tr(), ptz_key=(s or {}).get("ptz_key"), has_ptz=has_ptz,
                    glyphs=GLYPHS)


def has_ptz(name, s):
    """True when devices.conf has camera control for this camera (only then the hint offers it)."""
    try:
        from .ptz import all_devices
        return name in all_devices(s)
    except Exception:  # a broken devices.conf must not stop the window
        return False


def white():
    global WHITE
    if WHITE is None:
        WHITE = kodiapi.addon_path("resources", "media", "white.png")
    return WHITE


def open_window(factory):
    """Creates a window and runs it modally in one dedicated thread, and returns it. Kodi runs a window's
    callbacks (onAction) in the thread that created it, and only a modal window gets the remote keys, so both
    have to happen in a thread that lives as long as the window. close() from any thread ends it."""
    box, ready = {}, threading.Event()

    def run():
        try:
            box["w"] = factory()
        finally:
            ready.set()
        box["w"].doModal()

    threading.Thread(target=run, name="camalert-window", daemon=True).start()
    ready.wait(10)
    if "w" not in box:
        raise RuntimeError("window could not be created")
    return box["w"]


def orient(control, name, orientation):
    eff = ANIM.get(orientation.get(name, ""))
    control.setAnimations([("conditional", eff + " time=0 condition=true")] if eff else [])


class PtzMode(object):
    """PTZ mode shared by the photo window and the live overlay: arrows pan/tilt, channel/page up-down zoom,
    OK = home position, BACK leaves PTZ mode."""
    ptz = None

    def ptz_toggle(self, name):
        if self.ptz is not None:
            self.ptz_leave()
            return True
        from .ptz import Ptz
        p = Ptz(name)
        if not p.available():
            kodiapi.notify("CamAlert", kodiapi.tr(30196), "", 3000)
            return False
        self.ptz = p
        self.ptz_label(True)
        return True

    def ptz_leave(self):
        if self.ptz is not None:
            self.ptz.stop()
        self.ptz = None
        self.ptz_label(False)

    def ptz_action(self, aid):
        """True when PTZ mode used the key."""
        if self.ptz is None:
            return False
        k = ptz_action(aid)
        if k is None:
            return aid not in VOLUME_KEYS
        if k == "leave":
            self.ptz_leave()
        else:
            self.ptz.do(k)
        self.ptz_used()
        return True

    def ptz_label(self, on):
        pass

    def ptz_used(self):
        pass


class Feeder(object):
    """Keeps fetching snapshots, one thread per tile (a slow camera never holds up the others), each camera with
    its own refresh interval. Every picture gets a new file name so Kodi never shows a cached one."""

    def __init__(self, tiles, s):
        self.tiles = list(tiles)  # dicts: name, url, control
        self.verify = s["verify_ssl"]
        self.refresh = parse_refresh(s.get("refresh", ""))
        self.active = True
        self.on_unreachable = None  # callback(tile, unreachable)
        self.retry = 2.0  # seconds between attempts while a camera does not answer

    def start(self):
        for i in range(len(self.tiles)):
            threading.Thread(target=self.loop, args=(i,), daemon=True).start()

    def loop(self, i):
        tmp = kodiapi.temp_dir()
        n = 0
        fails = {}
        while self.active:
            t = self.tiles[i]
            n += 1
            path, stale = frame_name(os.path.join(tmp, "f%d_%x" % (i, id(self) & 0xffff)), n)
            start = time.time()
            try:
                sources.download(t["url"], path, self.verify)
            except Exception as e:  # camera or go2rtc not reachable: try again a bit later
                fails[i] = fails.get(i, 0) + 1
                if fails[i] == 1:
                    kodiapi.log("snapshot failed for %s: %s" % (t["name"], e))
                if fails[i] == 2 and self.on_unreachable:  # say so instead of a black or frozen picture
                    self.on_unreachable(t, True)
                time.sleep(self.retry)
                continue
            if fails.get(i, 0) >= 2 and self.on_unreachable:
                self.on_unreachable(t, False)
            fails[i] = 0
            if not self.active:
                break
            if self.tiles[i] is t:  # not switched to another camera meanwhile
                t["control"].setImage(path, False)
            try:
                os.remove(stale)
            except OSError:
                pass
            wait = refresh_delay(t["name"], self.refresh, 0.3) - (time.time() - start)
            end = time.time() + max(0.0, wait)
            while self.active and time.time() < end and self.tiles[i] is t:
                time.sleep(0.05)
        for k in range(max(1, n - 3), n + 1):
            try:
                os.remove("%s_%d.jpg" % (os.path.join(tmp, "f%d_%x" % (i, id(self) & 0xffff)), k))
            except OSError:
                pass

    def replace(self, old_name, tile):
        self.tiles = [tile if t["name"] == old_name else t for t in self.tiles]

    def stop(self):
        self.active = False


class PhotoWindow(PtzMode, xbmcgui.WindowDialog):
    """Corner window with one camera, or a strip of 2-4 cameras."""

    def __init__(self, ctl, cams, s, keys=True, label=None):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl, self.cams, self.keys = ctl, list(cams), keys
        n = len(self.cams)
        font = title_font_name(s["title_size"], kodiapi.skin_fonts())
        if n == 1:
            x, y, w, h, t = window_geometry(s["position"], s["size"], SCREEN_W, SCREEN_H, s["title_size"])
            tiles = [(0, t, w, h)]
            total_h = h + t
        else:
            x, y, w, h, t, tiles = strip_geometry(n, s.get("strip_layout", "auto"), s["position"], s["size"],
                                                  SCREEN_W, SCREEN_H)
            total_h = h + t
        self.addControl(xbmcgui.ControlImage(x, y, w, total_h, white(), colorDiffuse="FF202020"))
        names = ", ".join(c[1] for c in self.cams)
        if n > 1:
            names = event_title(names, label)
        self.label = xbmcgui.ControlLabel(x + 8, y, w - 16, t, names, font=font, textColor="FFFFFFFF",
                                          alignment=0x00000004)
        self.addControl(self.label)
        self.settings = s
        orientation = parse_orientation(s.get("orientation", ""))
        self.tiles = []
        for (name, title, url), (tx, ty, tw, th) in zip(self.cams, tiles):
            img = xbmcgui.ControlImage(x + tx, y + ty, tw, th, "", aspectRatio=2)
            self.addControl(img)
            orient(img, name, orientation)
            self.tiles.append({"name": name, "url": url, "control": img})
        self.stream = self.cams[0][0] if n == 1 else ",".join(c[0] for c in self.cams)
        self.title_text = names
        self.hint_label = None
        if keys and n == 1:  # dark strip with the key hint at the bottom of the picture
            hh = max(22, t - 8)
            self.addControl(xbmcgui.ControlImage(x, y + total_h - hh, w, hh, white(), colorDiffuse="99000000"))
            self.hint_label = xbmcgui.ControlLabel(x + 8, y + total_h - hh, w - 16, hh, "",
                                                   font=title_font_name("small", kodiapi.skin_fonts()),
                                                   textColor="FFDDDDDD", alignment=0x00000004 | 0x00000002)
            self.addControl(self.hint_label)
        self.orientation = orientation
        self.duration = s["duration"]
        self.feeder = Feeder(self.tiles, s)
        self.feeder.on_unreachable = self.unreachable
        self.timer = None
        self.ptz_label(False)

    def start(self, seconds):
        self.feeder.start()
        self.extend(seconds)

    def extend(self, seconds):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(seconds, lambda: self.ctl.window_timeout(self))
        self.timer.daemon = True
        self.timer.start()

    def switch(self, name, title, url):
        """Show another camera in the single-camera window."""
        if len(self.tiles) != 1:
            return
        old = self.tiles[0]["name"]
        self.tiles[0] = dict(self.tiles[0], name=name, url=url)
        self.feeder.replace(old, self.tiles[0])
        orient(self.tiles[0]["control"], name, self.orientation)
        self.stream = name
        self.title_text = title
        self.ptz_label(False)

    def ptz_label(self, on):
        self.label.setLabel(self.title_text)
        if self.hint_label is not None:
            self.hint_label.setLabel(hint("ptz", self.settings) if on else
                                     hint("window", self.settings, has_ptz(self.stream, self.settings)))

    def unreachable(self, tile, bad):
        from .controller import STATS
        if bad:
            STATS["unreachable"] += 1
            self.label.setLabel(kodiapi.tr(30254) % self.title_text)
        else:
            self.ptz_label(self.ptz is not None)

    def ptz_used(self):
        self.extend(max(self.duration, 30))

    def stop(self):
        if self.timer:
            self.timer.cancel()
        if self.ptz is not None:
            self.ptz.stop()
        self.feeder.stop()
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        aid = action.getId()
        kodiapi.log("photo window key %d / button %d" % (aid, action.getButtonCode()), "verbose")
        if self.ptz_action(aid):
            return
        colour = colour_name(action.getButtonCode())
        if colour and len(self.tiles) == 1:
            if self.ctl.colour_key(self.stream, colour) == "ptz" and self.ptz_toggle(self.stream):
                self.ptz_used()
            else:
                self.extend(self.duration)
            return
        if self.keys and aid in TOGGLE_IDS and len(self.tiles) == 1:
            if self.ptz_toggle(self.stream):
                self.ptz_used()
            return
        what = key_action(aid) if self.keys else ("pass" if aid in VOLUME_KEYS or aid == 107 else "close_pass")
        if what == "pass":
            if aid in VOLUME_KEYS:
                kodiapi.builtin(VOLUME_KEYS[aid])
            return
        if what == "live" and len(self.tiles) == 1:
            self.ctl.window_to_live(self.stream)
        elif what in ("prev", "next") and len(self.tiles) == 1:
            self.ctl.other_camera(-1 if what == "prev" else 1)
        elif what in ("close", "close_pass", "live", "prev", "next"):
            self.ctl.hide()
            b = forward_builtin(aid) if what == "close_pass" else None
            if b:
                kodiapi.builtin(b)


class FullScreen(xbmcgui.WindowDialog):
    """Mosaic (all tiles at once) or tour (one camera after the other)."""

    def __init__(self, ctl, cams, s, tour=False, seconds=0, interval=8):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl, self.cams, self.tour, self.interval = ctl, list(cams), tour, interval
        self.index, self.hold, self.active = 0, False, True
        self.addControl(xbmcgui.ControlImage(-40, -40, SCREEN_W + 80, SCREEN_H + 80, white(), colorDiffuse="FF000000"))
        self.orientation = parse_orientation(s.get("orientation", ""))
        top = 36
        if tour:
            img = xbmcgui.ControlImage(0, top, SCREEN_W, SCREEN_H - top, "", aspectRatio=2)
            self.addControl(img)
            self.tiles = [{"name": self.cams[0][0], "url": self.cams[0][2], "control": img}]
            orient(img, self.cams[0][0], self.orientation)
        else:
            self.tiles = []
            cells = grid(len(self.cams), SCREEN_W, SCREEN_H - top)
            for (name, title, url), (x, y, w, h) in zip(self.cams, cells):
                img = xbmcgui.ControlImage(x, y + top, w, h, "", aspectRatio=2)
                self.addControl(img)
                orient(img, name, self.orientation)
                self.tiles.append({"name": name, "url": url, "control": img})
            for (name, title, url), (x, y, w, h) in zip(self.cams, cells):  # labels on top of all pictures
                # dark strip behind the label: ControlLabel has no shadowColor in any Kodi version (#25)
                self.addControl(xbmcgui.ControlImage(x, y + top + h - 34, w, 34, white(), colorDiffuse="99000000"))
                self.addControl(xbmcgui.ControlLabel(x + 8, y + top + h - 34, w - 16, 30, title, font="font13",
                                                     textColor="FFFFFFFF"))
        self.title = xbmcgui.ControlLabel(12, 2, SCREEN_W - 24, 32, "", font="font13", textColor="FFFFFFFF")
        self.addControl(self.title)
        self.feeder = Feeder(self.tiles, s)
        self.timer = None
        self.close_timer = None
        self.seconds = seconds
        self.update_title()

    def update_title(self):
        if self.tour:
            name, title, _url = self.cams[self.index]
            self.title.setLabel("%s      %s" % (tour_status(title, self.index + 1, len(self.cams), self.hold,
                                                            kodiapi.core_tr()), hint("tour")))
        else:
            self.title.setLabel("%s      %s" % (kodiapi.tr(30192), hint("mosaic")))

    def start(self):
        self.feeder.start()
        if self.tour:
            self.schedule()
        if self.seconds:
            self.close_timer = threading.Timer(self.seconds, lambda: self.ctl.fullscreen_closed(self))
            self.close_timer.daemon = True
            self.close_timer.start()

    def schedule(self):
        if self.timer:
            self.timer.cancel()
        if not self.hold:
            self.timer = threading.Timer(self.interval, lambda: self.step(1))
            self.timer.daemon = True
            self.timer.start()

    def step(self, delta):
        if not self.active:
            return
        self.index = (self.index + delta) % len(self.cams)
        name, title, url = self.cams[self.index]
        old = self.tiles[0]["name"]
        self.tiles[0] = dict(self.tiles[0], name=name, url=url)
        self.feeder.replace(old, self.tiles[0])
        orient(self.tiles[0]["control"], name, self.orientation)
        self.update_title()
        self.schedule()

    def stop(self):
        self.active = False
        for t in (self.timer, self.close_timer):
            if t:
                t.cancel()
        self.feeder.stop()
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        aid = action.getId()
        if aid in VOLUME_KEYS:
            kodiapi.builtin(VOLUME_KEYS[aid])
            return
        what = tour_key(aid) if self.tour else mosaic_key(aid)
        if what == "close":
            self.ctl.fullscreen_closed(self)
        elif what in ("prev", "next"):
            self.step(-1 if what == "prev" else 1)
        elif what == "hold":
            self.hold = not self.hold
            self.update_title()
            self.schedule()
        elif what == "live":
            name = self.cams[self.index][0]
            self.ctl.fullscreen_closed(self)
            self.ctl.show(name, None, "live", "high")


class LiveOverlay(PtzMode, xbmcgui.WindowDialog):

    """Thin bar over the live camera picture: BACK/STOP ends live, < > other camera, MENU/INFO = PTZ mode."""

    def __init__(self, ctl, name, title, s=None):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl, self.name, self.title_text = ctl, name, title
        self.settings = s if s is not None else kodiapi.settings()
        self.bg = xbmcgui.ControlImage(0, SCREEN_H - 40, SCREEN_W, 40, white(), colorDiffuse="99000000")
        self.addControl(self.bg)
        self.label = xbmcgui.ControlLabel(16, SCREEN_H - 38, SCREEN_W - 32, 36, "", font="font13",
                                          textColor="FFFFFFFF")
        self.addControl(self.label)
        self.ptz_label(False)

    def set_camera(self, name, title):
        if self.ptz is not None:
            self.ptz_leave()
        self.name, self.title_text = name, title
        self.ptz_label(False)

    def ptz_label(self, on):
        self.label.setLabel("%s      %s" % (self.title_text, hint("ptz", self.settings) if on else
                                           hint("live", self.settings, has_ptz(self.name, self.settings))))

    def ptz_used(self):
        self.ctl.extend_live()

    def stop(self):
        if self.ptz is not None:
            self.ptz.stop()
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        aid = action.getId()
        if self.ptz_action(aid):
            return
        colour = colour_name(action.getButtonCode())
        if colour:
            if self.ctl.colour_key(self.name, colour) == "ptz" and self.ptz_toggle(self.name):
                self.ptz_used()
            return
        what = live_key(aid)
        if what == "ptz":
            if self.ptz_toggle(self.name):
                self.ptz_used()
            return
        if aid in VOLUME_KEYS:
            kodiapi.builtin(VOLUME_KEYS[aid])
        elif what in ("prev", "next"):
            self.ctl.live_other(-1 if what == "prev" else 1)
        elif what == "close":
            self.ctl.hide()
        elif what == "pause":
            kodiapi.builtin("Action(Pause)")
