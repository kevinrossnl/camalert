# -*- coding: utf-8 -*-
# DoorCam - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 DoorCam developers. Licensed under the GNU GPL v2 (see LICENSE).
import gettext

from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigText, ConfigInteger, \
    ConfigSelection, ConfigSelectionNumber, ConfigClock

__version__ = "1.0.0"
PluginLanguageDomain = "DoorCam"
PluginLanguagePath = "Extensions/DoorCam/locale"


def localeInit():
    gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
    t = gettext.dgettext(PluginLanguageDomain, txt)
    if t == txt:
        t = gettext.gettext(txt)
    return t


localeInit()
language.addCallback(localeInit)

config.plugins.doorcam = ConfigSubsection()
c = config.plugins.doorcam
c.enabled = ConfigYesNo(default=True)
c.source = ConfigSelection(default="go2rtc", choices=[
    ("go2rtc", _("go2rtc server")), ("direct", _("Directly from the cameras"))])
c.server = ConfigText(default="http://192.168.1.10:1984", fixed_size=False)
c.rtsp_port = ConfigInteger(default=8554, limits=(1, 65535))
c.camera = ConfigText(default="", fixed_size=False)
c.mode = ConfigSelection(default="photo", choices=[
    ("photo", _("Photo window")),
    ("live", _("Switch to live stream")),
    ("notify", _("Notification only"))])
c.duration = ConfigSelectionNumber(5, 300, 5, default=30)
c.position = ConfigSelection(default="top_right", choices=[
    ("top_right", _("Top right")), ("top_left", _("Top left")),
    ("bottom_right", _("Bottom right")), ("bottom_left", _("Bottom left"))])
c.size = ConfigSelection(default="medium", choices=[
    ("small", _("Small")), ("medium", _("Medium")), ("large", _("Large"))])
c.live_return = ConfigYesNo(default=True)
c.pause_tv = ConfigYesNo(default=False)
c.live_volume = ConfigSelectionNumber(0, 100, 10, default=100)
c.skip_recording = ConfigYesNo(default=False)
c.limit_hours = ConfigYesNo(default=False)
c.from_time = ConfigClock(default=7 * 3600)
c.until_time = ConfigClock(default=23 * 3600)
c.verify_ssl = ConfigYesNo(default=True)
c.api_https = ConfigYesNo(default=False)
c.http_port = ConfigInteger(default=8099, limits=(1024, 65535))
c.allow = ConfigSelection(default="lan", choices=[
    ("lan", _("Local network only")), ("any", _("Any address"))])
c.token = ConfigText(default="", fixed_size=False)
c.bouquet_name = ConfigText(default="Cameras", fixed_size=False)
c.mosaic = ConfigText(default="", fixed_size=False)
