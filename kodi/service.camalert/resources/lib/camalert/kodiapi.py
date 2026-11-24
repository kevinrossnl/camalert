# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Thin wrapper around the Kodi modules (one place to mock in tests)."""
import json
import os
import re

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import ADDON_ID
from .klogic import DEFAULTS, parse_settings

_addon = None


def addon():
    global _addon
    if _addon is None:
        _addon = xbmcaddon.Addon(ADDON_ID)
    return _addon


def reload_addon():
    global _addon
    _addon = None


_english = None


def english(string_id):
    """English text from our own strings.po: Kodi only loads the strings of a freshly unpacked add-on after a
    restart, and an empty label must never break a message."""
    global _english
    if _english is None:
        _english = {}
        try:
            with open(addon_path("resources", "language", "resource.language.en_gb", "strings.po"), encoding="utf-8") as f:
                text = f.read()
            for m in re.finditer(r'msgctxt "#(\d+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"', text):
                _english[int(m.group(1))] = m.group(2).replace('\\n', "\n").replace('\\"', '"')
        except OSError:
            pass
    return _english.get(string_id, "")


def tr(string_id):
    return addon().getLocalizedString(string_id) or english(string_id)


def log(msg, level=xbmc.LOGINFO):
    xbmc.log("[CamAlert] %s" % msg, level)


def settings():
    a = xbmcaddon.Addon(ADDON_ID)  # fresh object: Kodi caches settings per instance
    raw = {k: a.getSetting(k) for k in DEFAULTS}
    return parse_settings(raw)


def set_setting(key, value):
    xbmcaddon.Addon(ADDON_ID).setSetting(key, str(value).lower() if isinstance(value, bool) else str(value))


def profile_dir():
    d = xbmcvfs.translatePath("special://profile/addon_data/%s/" % ADDON_ID)
    os.makedirs(d, exist_ok=True)
    return d


def temp_dir():
    d = os.path.join(xbmcvfs.translatePath("special://temp/"), "camalert")
    os.makedirs(d, exist_ok=True)
    return d


def addon_path(*parts):
    return os.path.join(xbmcvfs.translatePath(addon().getAddonInfo("path")), *parts)


def builtin(cmd):
    xbmc.executebuiltin(cmd)


def cond(expr):
    return xbmc.getCondVisibility(expr)


def info(label):
    return xbmc.getInfoLabel(label)


def jsonrpc(method, params=None):
    req = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        req["params"] = params
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(req))).get("result")
    except (ValueError, TypeError):
        return None


def notify(heading, message, icon="", ms=5000, sound=True):
    xbmcgui.Dialog().notification(heading, message, icon or xbmcgui.NOTIFICATION_INFO, ms, sound)


def friendly_name():
    return info("System.FriendlyName") or "Kodi"


def mac_address():
    for dev in ("eth0", "wlan0", "end0"):
        try:
            with open("/sys/class/net/%s/address" % dev) as f:
                return f.read().strip()
        except OSError:
            pass
    return info("Network.MacAddress")


class Monitor(xbmc.Monitor):
    def __init__(self, on_settings=None):
        xbmc.Monitor.__init__(self)
        self.on_settings = on_settings

    def onSettingsChanged(self):
        if self.on_settings:
            self.on_settings()
