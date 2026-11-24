# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Buttons in the settings: RunScript(service.camalert,<command>)."""
import json
import time

import xbmcgui

from . import kodiapi, ptz, sources


def send(**cmd):
    xbmcgui.Window(10000).setProperty("camalert.cmd", json.dumps(cmd))


def choose_camera():
    s = kodiapi.settings()
    try:
        names = sources.all_camera_names(s)
    except Exception as e:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30181) % e)
        return
    if not names:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30182))
        return
    titles = [sources.title(n, s) for n in names]
    pre = names.index(s["camera"]) if s["camera"] in names else -1
    i = xbmcgui.Dialog().select(kodiapi.tr(30026), titles, preselect=pre)
    if i >= 0:
        kodiapi.set_setting("camera", names[i])


def run(args):
    what = args[0] if args else "settings"
    if what == "choose_camera":
        choose_camera()
    elif what == "test":
        s = kodiapi.settings()
        if not s["camera"]:
            xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30184))
            return
        time.sleep(0.5)  # settings dialog closes first
        send(do="show", cam=s["camera"])
    elif what in ("mosaic", "tour", "hide"):
        time.sleep(0.5)
        send(do=what)
    elif what == "devices":
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30185) % ptz.ensure_example())
    else:
        kodiapi.addon().openSettings()
