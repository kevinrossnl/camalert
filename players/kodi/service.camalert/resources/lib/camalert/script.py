# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Buttons in the settings: RunScript(service.camalert,<command>)."""
import json
import time

import xbmcgui

from . import kodiapi, ptz, sources


def send(**cmd):
    xbmcgui.Window(10000).setProperty("camalert.cmd", json.dumps(cmd))


def pick_camera():
    """A camera chosen from the list (None = cancelled or no cameras; then the dialog already said why)."""
    s = kodiapi.settings()
    problem = sources.go2rtc_problem(s)
    if problem:  # #73: say why there are no cameras instead of an empty list
        xbmcgui.Dialog().ok("CamAlert", problem)
        return None
    try:
        names = sources.all_camera_names(s)
    except Exception as e:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30181) % e)
        return None
    if not names:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30182))
        return None
    titles = [sources.title(n, s) for n in names]
    pre = names.index(s["camera"]) if s["camera"] in names else -1
    i = xbmcgui.Dialog().select(kodiapi.tr(30026), titles, preselect=pre)
    return names[i] if i >= 0 else None


def choose_camera():
    name = pick_camera()
    if name:
        kodiapi.set_setting("camera", name)


def open_settings():
    kodiapi.addon().openSettings()


# #106: what opening the add-on (Add-ons > Program add-ons, a favourite) offers: (label id, action)
MENU = ((30171, lambda: send(do="mosaic")), (30172, lambda: send(do="tour")), (30205, lambda: show_camera()),
        (30204, lambda: events()), (30201, lambda: diagnostics()), (30284, lambda: open_settings()))


def show_camera():
    name = pick_camera()
    if name:
        send(do="show", cam=name)


def menu():
    i = xbmcgui.Dialog().select("CamAlert", [kodiapi.tr(label) for label, _action in MENU])
    if 0 <= i < len(MENU):
        MENU[i][1]()


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


def camera_password():
    """#55: the default camera password is kept in devices.conf; show whether one is stored, change or remove it."""
    ptz.move_camera_password()  # one typed in the settings just now
    stored = bool(ptz.default_login()[1])
    choices = [kodiapi.tr(30279)] + ([kodiapi.tr(30280)] if stored else [])
    heading = "%s: %s" % (kodiapi.tr(30154), kodiapi.tr(30277 if stored else 30278))
    i = xbmcgui.Dialog().select(heading, choices)
    if i == 0:
        password = xbmcgui.Dialog().input(kodiapi.tr(30154), type=xbmcgui.INPUT_ALPHANUM,
                                          option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not password:
            return
        ptz.store_default_password(password)
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30281))
    elif i == 1:
        ptz.store_default_password("")
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30282))


def run(args):
    if not args:
        menu()
        return
    what = args[0]
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
    elif what == "camera_password":
        camera_password()
    elif what == "devices":
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30185) % ptz.ensure_example())
    else:
        open_settings()
