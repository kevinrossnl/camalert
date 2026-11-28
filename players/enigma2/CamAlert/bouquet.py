# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Camera channel list (bouquet): built from go2rtc / the camera file, updated automatically every 30 minutes.

The file and bouquets.tv are only written when something changed. Other bouquets are never removed.
If the camera source cannot be reached, the existing list is kept."""
import os

from enigma import eDVBDB, eTimer
from Components.config import config
from twisted.internet import threads

from .display import all_camera_names, direct_cameras, log
from .camalert_core.cameras import parse_titles
from .camalert_core.urls import normalize_server, valid_port
from .services import BOUQUET_FILE, bouquet_text, place_in_bouquets

E2 = "/etc/enigma2/"
INTERVAL = 30 * 60 * 1000
_timer = None


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _write(path, text):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def build(names):
    c = config.plugins.camalert
    direct = direct_cameras() if c.source.value == "direct" else None
    from .display import resolve_camera
    return bouquet_text(c.bouquet_name.value or "Cameras", normalize_server(c.server.value), names,
                        valid_port(c.rtsp_port.value, 8554), cameras=direct, titles=parse_titles(c.titles.value),
                        resolve=resolve_camera)


def apply(names, force=False):
    """Writes the list if it differs (or force). Returns (changed, number of cameras)."""
    if not names:
        log("camera list: no cameras found, keeping the current list")
        return False, 0
    text = build(names)
    changed = False
    if force or _read(E2 + BOUQUET_FILE) != text:
        _write(E2 + BOUQUET_FILE, text)
        changed = True
    tv = _read(E2 + "bouquets.tv")
    if tv is not None:
        new_tv = place_in_bouquets(tv, BOUQUET_FILE, config.plugins.camalert.bouquet_position.value)
        if new_tv != tv:
            _write(E2 + "bouquets.tv", new_tv)
            changed = True
    if changed:
        reload()
        log("camera list updated:", len(names), "cameras")
    if config.plugins.camalert.picons.value:
        make_picons(names)
    return changed, len(names)


def make_picons(names):
    from twisted.internet import threads
    from . import picons
    from .display import camera_urls
    titles = [u[2] for u in (camera_urls(n) for n in names) if u]
    threads.deferToThread(picons.make, titles).addCallbacks(
        lambda r: log("picons: %d written, %d existing kept (%s)" % r) if r[2] else
        log("picons: no writable picon folder (read-only or missing), nothing written"),
        lambda e: log("picons failed:", e.getErrorMessage()))


def reload():
    """Reloads the bouquets. The channel list screen reads them again when it is opened; on images where the
    channel selection has its own reload method (not openATV 8) that is called as well."""
    eDVBDB.getInstance().reloadBouquets()
    try:
        from Screens.InfoBar import InfoBar
        sl = getattr(InfoBar.instance, "servicelist", None) if InfoBar.instance else None
        fn = getattr(sl, "reloadBouquets", None)
        if callable(fn):
            fn()
    except Exception as e:
        log("service list reload failed:", e)


def update(force=False, done=None, failed=None):
    """Fetches the camera list in a thread and applies it. done(changed, count) / failed(message)."""
    def ok(names):
        result = apply(names, force)
        if done:
            done(*result)

    def err(e):
        log("camera list: source not reachable, keeping the current list:", e.getErrorMessage())
        if failed:
            failed(e.getErrorMessage())
    threads.deferToThread(all_camera_names).addCallbacks(ok, err)


def _tick():
    if config.plugins.camalert.enabled.value and config.plugins.camalert.auto_bouquet.value:
        update()
    _timer.start(INTERVAL, True)


def start(first_delay=30000):
    global _timer
    if _timer is None:
        _timer = eTimer()
        _timer.callback.append(_tick)
    _timer.start(first_delay, True)
