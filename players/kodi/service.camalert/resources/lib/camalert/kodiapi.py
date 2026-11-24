# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Thin wrapper around the Kodi modules (one place to mock in tests)."""
import json
import os
import platform
import re

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import ADDON_ID
from .klogic import DEFAULTS, os_label, parse_settings

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


_core_ids = None


def core_tr():
    """tr(msgid) for the texts of camalert_core (key hints, event-list values, #41): Kodi string ids from our
    English strings.po (i18n.kodi_ids), translated by Kodi, the English text when Kodi has no string yet."""
    global _core_ids
    from .camalert_core.i18n import kodi_ids, kodi_translator
    if _core_ids is None:
        try:
            with open(addon_path("resources", "language", "resource.language.en_gb", "strings.po"), encoding="utf-8") as f:
                _core_ids = kodi_ids(f.read())
        except OSError:
            _core_ids = {}
    return kodi_translator(tr, _core_ids)


def language():
    """Kodi's GUI language as ISO 639-1 ('nl'), '' if unknown."""
    try:
        return xbmc.getLanguage(xbmc.ISO_639_1) or ""
    except Exception:
        return ""


def date_format():
    """Kodi's short date format of the region (strftime), or None."""
    try:
        return xbmc.getRegion("dateshort") or None
    except Exception:
        return None


_camlog = None


def camlog():
    """Own rotating log (camalert.log, 2 x 1 MB) in the add-on data folder, plus optional remote syslog."""
    global _camlog
    if _camlog is None:
        from .camalert_core.obs.camlog import CamLog
        _camlog = CamLog(dirs=(profile_dir(),))
    return _camlog


def log(msg, level="normal"):
    """level: error / normal / verbose. Everything is redacted; verbose only goes to camalert.log."""
    from .camalert_core.obs.log import redact
    msg = redact(msg)
    if level != "verbose":
        xbmc.log("[CamAlert] %s" % msg, xbmc.LOGERROR if level == "error" else xbmc.LOGINFO)
    try:
        camlog().write(level, msg)
    except Exception:  # never let logging break anything
        pass


def settings():
    a = xbmcaddon.Addon(ADDON_ID)  # fresh object: Kodi caches settings per instance
    raw = {k: a.getSetting(k) for k in DEFAULTS}
    return parse_settings(raw)


def migrate_settings():
    """Moves settings saved by a version-1 add-on to their schema-version-2 keys (once; afterwards there is
    nothing left to move). Returns the keys that were written."""
    from .klogic import migrations, saved_values
    path = os.path.join(profile_dir(), "settings.xml")
    try:
        with open(path, encoding="utf-8") as f:
            todo = migrations(saved_values(f.read()))
    except OSError:
        return []
    for key, value in sorted(todo.items()):
        set_setting(key, value)
    if todo:
        log("settings migrated to schema version 2: %s" % ", ".join(sorted(todo)))
    return sorted(todo)


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


_fonts = {}


def skin_fonts():
    """{font name: size} of the current skin (its Font.xml), cached per skin; {} when it cannot be read."""
    from .klogic import skin_font_sizes
    skin = xbmcvfs.translatePath("special://skin/")
    if skin not in _fonts:
        found = {}
        try:
            for sub in sorted(os.listdir(skin)):
                path = os.path.join(skin, sub, "Font.xml")
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        found = skin_font_sizes(f.read())
                    if found:
                        break
        except OSError:
            pass
        _fonts[skin] = found
    return _fonts[skin]


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


def chime():
    """Doorbell sound (Kodi's GUI sound output, follows Kodi's volume and mute)."""
    try:
        xbmc.playSFX(addon_path("resources", "media", "chime.wav"), False)
    except Exception as e:
        log("chime failed: %s" % e, "error")


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



def os_version(tries=8):
    """System.OSVersionInfo once Kodi has it (it answers "Busy" at first), else platform system + release (#59)."""
    busy = ("Busy", xbmc.getLocalizedString(503))
    fallback = ("%s %s" % (platform.system(), platform.release())).strip()
    info = ""
    for i in range(tries):
        info = xbmc.getInfoLabel("System.OSVersionInfo")
        if os_label(info, busy, None) is not None:
            break
        if i < tries - 1:
            xbmc.sleep(250)
    return os_label(info, busy, fallback)
