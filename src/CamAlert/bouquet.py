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
from .logic import BOUQUET_FILE, bouquet_text, normalize_server, parse_titles, place_in_bouquets, valid_port

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
    return bouquet_text(c.bouquet_name.value or "Cameras", normalize_server(c.server.value), names,
                        valid_port(c.rtsp_port.value, 8554), cameras=direct, titles=parse_titles(c.titles.value))


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
    return changed, len(names)


def reload():
    eDVBDB.getInstance().reloadBouquets()
    try:
        from Screens.InfoBar import InfoBar
        if InfoBar.instance and hasattr(InfoBar.instance, "servicelist"):
            InfoBar.instance.servicelist.reloadBouquets()
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
