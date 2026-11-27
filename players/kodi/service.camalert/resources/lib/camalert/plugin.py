# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Video add-on (#107): the cameras as a list for the Kodi home screen (Videos > Video add-ons > CamAlert,
favourites). Selecting an item hands a command to the running service, like the settings buttons (script.py)."""
import time

import xbmcgui
import xbmcplugin

from . import browse, kodiapi, script, sources
from .camalert_core.obs.log import redact


def pause():
    time.sleep(0.3)  # let Kodi close the list first


def text(label):
    return kodiapi.tr(label) if isinstance(label, int) else label


def set_plot(li, plot):
    """#108: InfoTagVideo.setPlot on Kodi 20+ (setInfo is deprecated there), ListItem.setInfo on Kodi 19."""
    tag = li.getVideoInfoTag()
    if hasattr(tag, "setPlot"):
        tag.setPlot(plot)
    else:
        li.setInfo("video", {"plot": plot})


def cameras():
    """([(name, title, snapshot url or None)], problem text or None)."""
    s = kodiapi.settings()
    problem = sources.go2rtc_problem(s)
    if problem:
        return [], problem.replace("\n", " ")
    try:
        names = sources.overview_names(sources.all_camera_names(s))  # #125: no own mosaic stream in the list
    except Exception as e:
        return [], redact(kodiapi.tr(30181) % e).replace("\n", " ")
    out = []
    for name in names:
        urls = sources.camera_urls(name, s)
        out.append((name, urls[2], urls[1]) if urls else (name, name, None))
    return out, None


def listing(base, handle):
    cams, problem = cameras()
    icon = kodiapi.addon_path("resources", "icon.png")
    items = []
    for it in browse.root_items(base, cams, problem, time.time()):
        li = xbmcgui.ListItem(text(it["label"]), text(it["label2"]) if it["label2"] else "")
        art = {"icon": icon, "thumb": icon}
        if it["thumb"]:
            art = {"icon": it["thumb"], "thumb": it["thumb"]}
        li.setArt(art)
        if it["context"]:
            li.addContextMenuItems([(text(label), "RunPlugin(%s)" % link) for label, link in it["context"]])
        if it["plot"]:
            set_plot(li, text(it["plot"]))
        items.append((it["url"], li, it["folder"]))
    xbmcplugin.setContent(handle, "videos")
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_NONE)  # #108: keep our order, no "Sort by: Date"
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def run(argv):
    base, handle = argv[0], int(argv[1])
    p = browse.parse(argv[2] if len(argv) > 2 else "")
    if p is None:
        listing(base, handle)
    elif p["do"] in browse.CAMERA_ACTIONS:
        pause()
        script.send(do="show", cam=p["cam"], mode="live" if p["do"] == "live" else "photo")
    elif p["do"] in ("mosaic", "tour"):
        pause()
        script.send(do=p["do"])
    elif p["do"] == "events":
        script.events()
    elif p["do"] == "settings":
        kodiapi.addon().openSettings()
