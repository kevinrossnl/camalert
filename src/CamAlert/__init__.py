# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
import gettext

from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigText, ConfigInteger, \
    ConfigSelection, ConfigSelectionNumber, ConfigClock, ConfigPassword

__version__ = "1.0.0"
PluginLanguageDomain = "CamAlert"
PluginLanguagePath = "Extensions/CamAlert/locale"


def localeInit():
    gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
    t = gettext.dgettext(PluginLanguageDomain, txt)
    if t == txt:
        t = gettext.gettext(txt)
    return t


localeInit()
language.addCallback(localeInit)

config.plugins.camalert = ConfigSubsection()
c = config.plugins.camalert


def _add(name, factory):
    """Adds a setting. A broken saved value (e.g. edited by hand) must never stop the plugin from loading:
    then the saved value is dropped and the default is used."""
    try:
        setattr(c, name, factory())
    except Exception as e:
        print("[CamAlert] invalid saved value for %s (%s), using the default" % (name, e))
        try:
            c.content.stored_values.pop(name, None)
        except Exception:
            pass
        setattr(c, name, factory())


_add("enabled", lambda: ConfigYesNo(default=True))
_add("source", lambda: ConfigSelection(default="go2rtc", choices=[
    ("go2rtc", _("go2rtc server")), ("direct", _("Directly from the cameras"))]))
_add("server", lambda: ConfigText(default="http://192.168.1.10:1984", fixed_size=False))
_add("rtsp_port", lambda: ConfigInteger(default=8554, limits=(1, 65535)))
_add("camera", lambda: ConfigText(default="", fixed_size=False))
_add("mode", lambda: ConfigSelection(default="photo", choices=[
    ("photo", _("Photo window")),
    ("live", _("Switch to live stream")),
    ("notify", _("Notification only"))]))
_add("duration", lambda: ConfigSelectionNumber(5, 300, 5, default=30))
_add("position", lambda: ConfigSelection(default="top_right", choices=[
    ("top_right", _("Top right")), ("top_left", _("Top left")),
    ("bottom_right", _("Bottom right")), ("bottom_left", _("Bottom left"))]))
_add("size", lambda: ConfigSelection(default="medium", choices=[
    ("small", _("Small")), ("medium", _("Medium")), ("large", _("Large"))]))
_add("live_return", lambda: ConfigYesNo(default=True))
_add("pause_tv", lambda: ConfigYesNo(default=False))
_add("live_volume", lambda: ConfigSelectionNumber(0, 100, 10, default=100))
_add("skip_recording", lambda: ConfigYesNo(default=False))
_add("limit_hours", lambda: ConfigYesNo(default=False))
_add("from_time", lambda: ConfigClock(default=7 * 3600))
_add("until_time", lambda: ConfigClock(default=23 * 3600))
_add("verify_ssl", lambda: ConfigYesNo(default=True))
_add("api_https", lambda: ConfigYesNo(default=False))
_add("http_port", lambda: ConfigInteger(default=8099, limits=(1024, 65535)))
_add("allow", lambda: ConfigSelection(default="lan", choices=[
    ("lan", _("Local network only")), ("any", _("Any address"))]))
_add("token", lambda: ConfigText(default="", fixed_size=False))
_add("bouquet_name", lambda: ConfigText(default="Cameras", fixed_size=False))
_add("mosaic", lambda: ConfigText(default="", fixed_size=False))
_add("alarm_wake", lambda: ConfigYesNo(default=False))
_add("window_keys", lambda: ConfigYesNo(default=True))
_add("tour_interval", lambda: ConfigSelectionNumber(3, 60, 1, default=8))
_add("mqtt_enabled", lambda: ConfigYesNo(default=False))
_add("mqtt_host", lambda: ConfigText(default="", fixed_size=False))
_add("mqtt_port", lambda: ConfigInteger(default=1883, limits=(1, 65535)))
_add("mqtt_user", lambda: ConfigText(default="", fixed_size=False))
_add("mqtt_password", lambda: ConfigPassword(default="", fixed_size=False))
_add("mqtt_discovery", lambda: ConfigYesNo(default=True))
_add("mqtt_name", lambda: ConfigText(default="", fixed_size=False))
