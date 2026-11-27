# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""The first-start wizard (#120) with Kodi dialogs: find go2rtc, choose the default camera (with a preview), a test
and how to add this Kodi in Home Assistant. The logic is camalert_core.wizard. It runs in the add-on script (not in
the service): the search runs in its own thread while a progress dialog shows (Cancel stops it); the preview and
the test go to the service as commands. Leaving the wizard at any point marks it done."""
import threading
import time

import xbmcgui

from . import kodiapi
from .camalert_core import wizard as core

TITLE, SEARCHING, CAMERAS, MANUAL, DIRECT, NONE_FOUND, NO_ANSWER, ADDRESS = (30441, 30442, 30443, 30444, 30445,
                                                                              30446, 30447, 30016)
WHICH, RIGHT, NO_CAMERAS, TEST, READY, NAME, ADDR, AGAIN, DIRECT_DONE = (30449, 30450, 30451, 30452, 30453, 30454,
                                                                         30455, 30456, 30457)


def should_start(s=None):
    return core.should_start(s or kodiapi.settings())


def search(dialog=None):
    """[(server, cameras)] of every go2rtc in the network; a progress dialog while it runs (Cancel stops it)."""
    s = kodiapi.settings()
    stop, out = threading.Event(), {}
    addresses = core.candidates(core.own_ip(), core.ha_host(s))

    def work():
        out["found"] = core.unique_servers(core.scan(addresses, stop=stop))
    t = threading.Thread(target=work, name="camalert-wizard")
    t.daemon = True
    t.start()
    progress = dialog or xbmcgui.DialogProgress()
    progress.create(kodiapi.tr(TITLE), kodiapi.tr(SEARCHING))
    start = time.time()
    while t.is_alive():
        if progress.iscanceled():
            stop.set()
        progress.update(min(99, int((time.time() - start) * 100 / core.BUDGET)))
        t.join(0.2)
    progress.close()
    return out.get("found", [])


def send(**cmd):
    from .script import send as _send
    _send(**cmd)


def check(srv):
    """Cameras of a typed address, or None when nothing answers like go2rtc there."""
    from .sources import open_url
    from .camalert_core.urls import streams_from_json
    try:
        with open_url(srv + "/api/streams", 5, kodiapi.settings()["verify_ssl"]) as r:
            return streams_from_json(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - refused, timed out, certificate
        return None


def choose_server(found, dialog):
    """(server, cameras), "direct", or None (cancelled)."""
    tr = kodiapi.tr
    if not found:
        dialog.ok(tr(TITLE), tr(NONE_FOUND))
    labels = ["%s (%s)" % (srv, tr(CAMERAS) % len(cams)) for srv, cams in found] + [tr(MANUAL), tr(DIRECT)]
    while True:
        i = dialog.select(tr(TITLE), labels)
        if i < 0:
            return None
        if i < len(found):
            return found[i]
        if i == len(found) + 1:
            return "direct"
        typed = dialog.input(tr(ADDRESS), defaultt=kodiapi.settings()["server"] or "http://")
        if not typed:
            continue
        srv = core.server_from_input(typed)
        cams = check(srv) if srv else None
        if cams is None:
            dialog.ok(tr(TITLE), tr(NO_ANSWER) % (srv or typed))
            continue
        return srv, cams


def run(dialog=None, progress=None, wait=time.sleep):
    """The whole wizard. Returns the settings it saved."""
    dialog = dialog or xbmcgui.Dialog()
    tr = kodiapi.tr
    server = camera = None
    try:
        chosen = choose_server(search(progress), dialog)
        if chosen is None:
            return finish()
        if chosen == "direct":
            from .sources import camera_file
            saved = finish(core.result(direct=True))
            dialog.ok(tr(TITLE), tr(DIRECT_DONE) % camera_file())
            return saved
        server, cams = chosen
        kodiapi.set_setting("source", "go2rtc")
        kodiapi.set_setting("server", server)  # the preview needs the address
        if not cams:
            dialog.ok(tr(TITLE), tr(NO_CAMERAS))
            return finish()
        while True:
            current = kodiapi.settings()["camera"]
            i = dialog.select(tr(WHICH), list(cams), preselect=cams.index(current) if current in cams else 0)
            if i < 0:
                return finish()
            camera = cams[i]
            send(do="show", cam=camera, mode="photo", seconds=15, test=True)  # preview
            right = dialog.yesno(tr(TITLE), tr(RIGHT))
            send(do="hide")
            if right:
                break
        kodiapi.set_setting("camera", camera)
        if dialog.yesno(tr(TITLE), tr(TEST)):
            wait(0.5)
            send(do="show", cam=camera, mode="notify", seconds=10, test=True)
        saved = finish(core.result(server, camera))
        from .server import node_name
        name, address = core.add_text(node_name(), core.own_ip(), kodiapi.settings()["http_port"])
        dialog.ok(tr(TITLE), "\n".join([tr(READY), tr(NAME) % name, tr(ADDR) % address]))
        return saved
    except Exception:
        finish()
        raise


def finish(values=None):
    values = dict(values or {}, wizard_done=True)
    for key, value in values.items():
        kodiapi.set_setting(key, value)
    return values
