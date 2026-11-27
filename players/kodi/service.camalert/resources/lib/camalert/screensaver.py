# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Screensaver (#99): the CamAlert mosaic while Kodi is idle (Settings > Interface > Screensaver). Kodi starts
screensaver.py in its own Python process, so the warm feeds of the service (#111) are not there: the pictures come
from UniFi Protect (#109), the go2rtc cache (#110) or frame.jpeg, like a mosaic before the warm feed is ready.
Any key or Kodi ending the screensaver closes it. Without a usable camera source: black, with the reason."""
import threading

import xbmc
import xbmcgui

from . import display, kodiapi, sources
from .camalert_core.cameras import parse_cams
from .klogic import SCREEN_H, SCREEN_W

MAX_CAMS = 9


def cameras(s):
    """[(name, title, snapshot url)] of the mosaic cameras (setting 'mosaic', otherwise all), at most nine."""
    names = parse_cams(s.get("mosaic", "")) or sources.all_camera_names(s)
    out = []
    for name in names:
        u = sources.camera_urls(name, s)
        if u and u[1]:
            out.append((name, u[2], u[1]))
        if len(out) == MAX_CAMS:
            break
    return out


class Done(object):
    """Stands in for the controller of the mosaic window: closing ends the screensaver."""

    def __init__(self):
        self.event = threading.Event()

    def fullscreen_closed(self, win):
        self.event.set()

    def show(self, *args):
        self.event.set()


class ScreenSaver(display.FullScreen):
    """The mosaic without title or key hints; every key closes it."""

    def update_title(self):
        self.title.setLabel("")

    def onAction(self, action):
        self.ctl.fullscreen_closed(self)


class Blank(xbmcgui.WindowDialog):
    """Black screen with a short reason (no go2rtc address, no cameras); every key closes it."""

    def __init__(self, ctl, text=""):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl = ctl
        self.addControl(xbmcgui.ControlImage(-40, -40, SCREEN_W + 80, SCREEN_H + 80, display.white(),
                                             colorDiffuse="FF000000"))
        if text:
            self.addControl(xbmcgui.ControlLabel(40, SCREEN_H // 2 - 40, SCREEN_W - 80, 80, text, font="font13",
                                                 textColor="80FFFFFF", alignment=0x00000002 | 0x00000004))

    def start(self):
        pass

    def stop(self):
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        self.ctl.fullscreen_closed(self)


class Monitor(xbmc.Monitor):
    def __init__(self, done):
        xbmc.Monitor.__init__(self)
        self.done = done

    def onScreensaverDeactivated(self):
        self.done.event.set()


def window(done, s):
    problem = sources.go2rtc_problem(s)
    if problem:
        return lambda: Blank(done, problem.replace("\n", " "))
    try:
        cams = cameras(s)
    except Exception as e:
        kodiapi.log("screensaver: no cameras: %s" % e)
        cams = []
    if not cams:
        return lambda: Blank(done)
    return lambda: ScreenSaver(done, cams, s, tour=False)


def run():
    done = Done()
    monitor = Monitor(done)
    win = None
    try:
        win = display.open_window(window(done, kodiapi.settings()))
        win.start()
        while not done.event.is_set() and not monitor.waitForAbort(0.2):
            pass
    except Exception as e:
        kodiapi.log("screensaver failed: %s" % e, "error")
    finally:
        if win is not None:
            win.stop()
