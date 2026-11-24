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
    problem = sources.go2rtc_problem(s)
    if problem:  # #73: say why there are no cameras instead of an empty list
        xbmcgui.Dialog().ok("CamAlert", problem)
        return
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


def service_state():
    """Asks the running service for its state (events, last caller, MQTT) via a window property."""
    w = xbmcgui.Window(10000)
    stamp = str(time.time())
    send(do="state", time=stamp)
    for _ in range(30):
        time.sleep(0.1)
        try:
            st = json.loads(w.getProperty("camalert.state") or "{}")
        except ValueError:
            st = {}
        if st.get("time") == stamp:
            return st
    return None


def diagnostics():
    from . import diag
    dialog = xbmcgui.DialogProgress()
    dialog.create("CamAlert", kodiapi.tr(30200))
    lines = diag.collect(service_state())
    dialog.close()
    xbmcgui.Dialog().textviewer("CamAlert - %s" % kodiapi.tr(30201), "\n".join(lines))


def events():
    from .camalert_core.present import event_details, event_line
    from .camalert_core.triggers.frigate import frigate_clip_url
    st = service_state()
    if st is None:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30202))
        return
    evs = st.get("events") or []
    if not evs:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30203))
        return
    items = []
    tr, lang, fmt = kodiapi.core_tr(), kodiapi.language(), kodiapi.date_format()
    for e in evs:
        rows = event_details(e, tr, lang, fmt)  # time (with date), camera, source, priority, result, reason
        li = xbmcgui.ListItem(event_line(e, tr), "   ".join([rows[0][1]] + ["%s: %s" % r for r in rows[5:]]))
        if e.get("snapshot"):
            li.setArt({"thumb": e["snapshot"], "icon": e["snapshot"]})
        items.append(li)
    i = xbmcgui.Dialog().select(kodiapi.tr(30204), items, useDetails=True)
    if i < 0:
        return
    e = evs[i]
    s = kodiapi.settings()
    clip = frigate_clip_url(s["frigate_url"], e.get("frigate_id"))
    choices = [kodiapi.tr(30205)] + ([kodiapi.tr(30206)] if clip else [])
    j = xbmcgui.Dialog().select(e["camera"], choices) if clip else 0
    if j == 0:
        time.sleep(0.3)
        send(do="show", cam=e["camera"].split(",")[0])
    elif j == 1:
        send(do="play", url=clip, title="%s %s" % (e["camera"], e.get("label") or ""))


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
    elif what == "diagnostics":
        diagnostics()
    elif what == "events":
        events()
    elif what == "devices":
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30185) % ptz.ensure_example())
    else:
        kodiapi.addon().openSettings()
