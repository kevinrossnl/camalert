# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Buttons in the settings: RunScript(service.camalert,<command>)."""
import json
import time

import xbmcgui

from . import kodiapi, ptz, sources


def send(**cmd):
    xbmcgui.Window(10000).setProperty("camalert.cmd", json.dumps(cmd))


def camera_names():
    """All camera names, or None when there are none (the dialog already said why)."""
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
    return names


def pick_camera():
    """A camera chosen from the list (None = cancelled or no cameras; then the dialog already said why)."""
    names = camera_names()
    if not names:
        return None
    s = kodiapi.settings()
    titles = [sources.title(n, s) for n in names]
    pre = names.index(s["camera"]) if s["camera"] in names else -1
    i = xbmcgui.Dialog().select(kodiapi.tr(30026), titles, preselect=pre)
    return names[i] if i >= 0 else None


# ---- #50: per-camera settings edited with choice lists (like the Enigma2 settings screen) ----

ALL = "*"  # cooldown for every camera
MOSAIC_MAX = 9


def raw_setting(key):
    return kodiapi.addon_setting(key)


def save_setting(key, value):
    kodiapi.set_setting(key, value)


def pairs(text):
    """'cam=value|*=30' -> {'cam': 'value', '*': '30'}; parts without a name or value are dropped."""
    out = {}
    for part in (text or "").split("|"):
        if "=" in part:
            k, v = (x.strip() for x in part.split("=", 1))
            if k and v:
                out[k] = v
    return out


def unpairs(values):
    keys = sorted(values, key=lambda k: (k != ALL, k))
    return "|".join("%s=%s" % (k, values[k].replace("|", " ")) for k in keys if values[k])


def map_values(setting, cam, names):
    """[(label, value)] for one camera; value '' removes the camera from the setting (= default)."""
    tr = kodiapi.tr
    if setting == "orientation":
        return [(tr(30298), ""), (tr(30299), "mirror"), (tr(30300), "flip"), (tr(30301), "rot180")]
    if setting == "refresh":
        return [(tr(30302), "")] + [(tr(30303) % v, v) for v in ("1", "2", "5", "10", "30", "60")]
    if setting == "cooldown":
        return [(tr(30305), "")] + [(tr(30306) % v, v) for v in ("10", "30", "60", "120", "300")]
    if setting == "substreams":
        return [(tr(30309), "")] + [(sources.title(n), n) for n in names if n != cam]
    return []


PICKERS = ("titles", "orientation", "refresh", "cooldown", "substreams")


def pick_map(setting):
    names = camera_names()
    if not names:
        return
    current = pairs(raw_setting(setting))
    cams = ([ALL] if setting == "cooldown" else []) + names

    def shown(cam):
        title = kodiapi.tr(30304) if cam == ALL else sources.title(cam)
        value = current.get(cam, "")
        if setting == "titles":
            return "%s  ->  %s" % (cam, value or title)
        labels = dict((v, label) for label, v in map_values(setting, cam, names))
        return "%s  ->  %s" % (title, labels.get(value, value))
    i = xbmcgui.Dialog().select(kodiapi.tr(30026), [shown(c) for c in cams])
    if i < 0:
        return
    cam = cams[i]
    if setting == "titles":
        name = xbmcgui.Dialog().input(kodiapi.tr(30307) % cam, defaultt=current.get(cam, "")).strip()
        if not name and (not current.get(cam) or not xbmcgui.Dialog().yesno("CamAlert", kodiapi.tr(30308) % cam)):
            return  # Kodi also returns "" for a cancelled keyboard: only remove a name after a yes
        value = name
    else:
        values = map_values(setting, cam, names)
        pre = [v for _label, v in values].index(current.get(cam, "")) if current.get(cam, "") in \
            [v for _label, v in values] else 0
        j = xbmcgui.Dialog().select(shown(cam), [label for label, _v in values], preselect=pre)
        if j < 0:
            return
        value = values[j][1]
    if value:
        current[cam] = value
    else:
        current.pop(cam, None)
    save_setting(setting, unpairs(current))


def pick_mosaic():
    names = camera_names()
    if not names:
        return
    current = [c.strip() for c in raw_setting("mosaic").split(",") if c.strip()]
    pre = [i for i, n in enumerate(names) if n in current]
    chosen = xbmcgui.Dialog().multiselect(kodiapi.tr(30297), [sources.title(n) for n in names], preselect=pre)
    if chosen is None:
        return
    cams = [names[i] for i in chosen]
    if len(cams) > MOSAIC_MAX:
        xbmcgui.Dialog().ok("CamAlert", kodiapi.tr(30310))
        cams = cams[:MOSAIC_MAX]
    save_setting("mosaic", ",".join(cams))


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
    elif what == "pick":
        setting = args[1] if len(args) > 1 else ""
        if setting == "mosaic":
            pick_mosaic()
        elif setting in PICKERS:
            pick_map(setting)
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
