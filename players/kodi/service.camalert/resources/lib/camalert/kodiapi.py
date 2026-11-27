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


KODI_LANGUAGES = {"en": "en_gb", "nl": "nl_nl", "de": "de_de", "fr": "fr_fr", "it": "it_it", "pl": "pl_pl"}
_own = {"code": None, "at": 0.0, "strings": {}}


def own_language():
    """#10: the language setting ('nl', ...), or None for 'system' (Kodi's language). Read at most every 5 s."""
    import time
    now = time.time()
    if now - _own["at"] > 5:
        _own["at"] = now
        try:
            code = xbmcaddon.Addon(ADDON_ID).getSetting("language")
        except Exception:  # noqa: BLE001
            code = ""
        _own["code"] = code if code in KODI_LANGUAGES else None
    return _own["code"]


def po_strings(code):
    """{id: text} of the add-on's strings.po for a language (#10): msgstr, or msgid for English / untranslated."""
    if code not in _own["strings"]:
        out = {}
        try:
            with open(addon_path("resources", "language", "resource.language.%s" % KODI_LANGUAGES[code],
                                 "strings.po"), encoding="utf-8") as f:
                text = f.read()
            for m in re.finditer(r'msgctxt "#(\d+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"\s*\nmsgstr "((?:[^"\\]|\\.)*)"',
                                 text):
                value = m.group(3) or m.group(2)
                out[int(m.group(1))] = value.replace('\\n', "\n").replace('\\"', '"')
        except (OSError, KeyError):
            pass
        _own["strings"][code] = out
    return _own["strings"][code]


def tr(string_id):
    code = own_language()
    if code:  # #10: CamAlert's own language instead of Kodi's
        text = po_strings(code).get(string_id)
        if text:
            return text
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
    """The language of CamAlert's texts as ISO 639-1 ('nl'): the language setting (#10), else Kodi's GUI
    language; '' if unknown."""
    if own_language():
        return own_language()
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
    if todo:  # #7: the settings as they were, to undo the migration (Undo the last import)
        try:
            from .camalert_core.settingsfile import Backups
            with open(path, encoding="utf-8") as f:
                Backups(os.path.join(profile_dir(), "backups")).save(saved_values(f.read()), "kodi", "migration",
                                                                     schema_version=1)
        except Exception as e:  # noqa: BLE001 - never stop the migration
            log("backup before the settings migration failed: %s" % e, "error")
    for key, value in sorted(todo.items()):
        set_setting(key, value)
    if todo:
        log("settings migrated to schema version 2: %s" % ", ".join(sorted(todo)))
    return sorted(todo)


def addon_setting(key):
    """One raw setting, read from a fresh Addon object (Kodi caches settings per instance)."""
    return xbmcaddon.Addon(ADDON_ID).getSetting(key)


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
