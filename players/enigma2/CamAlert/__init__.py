# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
import gettext

from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigText, ConfigInteger, \
    ConfigSelection, ConfigSelectionNumber, ConfigClock, ConfigPassword, ConfigNumber

__version__ = "1.2.0"
PluginLanguageDomain = "CamAlert"
PluginLanguagePath = "Extensions/CamAlert/locale"


def localeInit():
    gettext.bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
    """Translation from CamAlert's own catalogue only (#56): never the image's enigma2 domain, which has some of our
    msgids with another meaning or case (English images translate "Normal" to "normal"). English has no catalogue,
    so the msgid itself is the English text."""
    return gettext.dgettext(PluginLanguageDomain, txt)


localeInit()
language.addCallback(localeInit)

config.plugins.camalert = ConfigSubsection()
c = config.plugins.camalert

# Defaults of version 1 that changed in version 2: a version-1 install did not store them, so they are filled in
# before migrating (an existing install keeps polling its Foscam cameras).
V1_DEFAULTS = {"foscam_poll": "true"}
# Always stored (save_forced): marks settings that were saved by version 2 or later.
V2_MARKER = "foscam_enabled"


def _migrate():
    """Settings saved by a version-1 plugin -> settings schema version 2 (#39), before the settings are created:
    renamed keys move, the yes/no chime becomes off/high, skip_media becomes skip_playing. Never fails."""
    try:
        from .camalert_core import schema
        stored = c.content.stored_values
        if not stored or V2_MARKER in stored:
            return
        values = dict(V1_DEFAULTS, **stored)
        new = schema.migrate(values, "enigma2")
        for key, value in list(new.items()):
            if isinstance(value, bool):
                new[key] = "true" if value else "false"
        stored.clear()  # old keys must go: Enigma2 writes every stored value back
        stored.update(new)
        print("[CamAlert] settings migrated to schema version %d" % schema.SCHEMA_VERSION)
    except Exception as e:
        print("[CamAlert] settings migration failed (%s), using the saved values as they are" % e)


_migrate()


def MODES():
    return [("photo", _("Photo window")), ("live", _("Live view")), ("notify", _("Notification"))]


def PRIORITIES():
    return [("normal", _("Normal")), ("high", _("High (doorbell)")), ("alarm", _("Alarm"))]


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
_add("server", lambda: ConfigText(default="", fixed_size=False))  # empty = not set (#73)
_add("rtsp_port", lambda: ConfigNumber(default=8554))
_add("camera", lambda: ConfigText(default="", fixed_size=False))
_add("mode", lambda: ConfigSelection(default="photo", choices=MODES()))
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
_add("http_port", lambda: ConfigNumber(default=8099))
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
_add("mqtt_port", lambda: ConfigNumber(default=1883))
_add("mqtt_user", lambda: ConfigText(default="", fixed_size=False))
_add("mqtt_password", lambda: ConfigPassword(default="", fixed_size=False))
_add("mqtt_discovery", lambda: ConfigYesNo(default=True))
_add("mqtt_name", lambda: ConfigText(default="", fixed_size=False))
_add("titles", lambda: ConfigText(default="", fixed_size=False))
_add("auto_bouquet", lambda: ConfigYesNo(default=True))
_add("bouquet_position", lambda: ConfigSelection(default="keep", choices=[
    ("keep", _("Where I put it")), ("bottom", _("At the bottom")), ("top", _("At the top"))]))
_add("dnd", lambda: ConfigYesNo(default=False))
_add("dnd_level", lambda: ConfigSelection(default="normal", choices=[
    # short values like Kodi (#56): long ones overlapped the label; HELP explains the rest
    ("normal", _("Normal priority")), ("high", _("Normal and high priority"))]))
_add("skip_playing", lambda: ConfigSelection(default="off", choices=[
    ("off", _("Always show")), ("video", _("Not during movies and recordings")),
    ("all", _("Not during anything (also live TV)"))]))
_add("orientation", lambda: ConfigText(default="", fixed_size=False))
_add("protect_snapshots", lambda: ConfigYesNo(default=True))
_add("ready_cameras", lambda: ConfigText(default="", fixed_size=False))
_add("refresh", lambda: ConfigText(default="", fixed_size=False))
_add("strip_layout", lambda: ConfigSelection(default="auto", choices=[
    ("auto", _("Automatic")), ("vertical", _("Below each other")), ("horizontal", _("Next to each other")),
    ("grid", _("2 x 2"))]))
_add("frigate_enabled", lambda: ConfigYesNo(default=False))
_add("frigate_prefix", lambda: ConfigText(default="frigate", fixed_size=False))
_add("frigate_labels", lambda: ConfigText(default="person", fixed_size=False))
_add("frigate_map", lambda: ConfigText(default="", fixed_size=False))
_add("frigate_priority", lambda: ConfigSelection(default="normal", choices=PRIORITIES()))
_add("frigate_mode", lambda: ConfigSelection(default="photo", choices=MODES()))
_add("frigate_seconds", lambda: ConfigSelectionNumber(5, 300, 5, default=30))
_add("log_level", lambda: ConfigSelection(default="normal", choices=[
    ("off", _("Off")), ("errors", _("Errors only")), ("normal", _("Normal")), ("verbose", _("Verbose"))]))
_add("log_syslog", lambda: ConfigText(default="", fixed_size=False))
_add("ptz_key", lambda: ConfigSelection(default="blue", choices=[
    ("blue", _("BLUE")), ("yellow", _("YELLOW")), ("red", _("RED")), ("green", _("GREEN")), ("off", _("Off"))]))
_add("ha_buttons", lambda: ConfigYesNo(default=True))
_add("ha_webhook", lambda: ConfigText(default="", fixed_size=False))
_add("wizard_done", lambda: ConfigYesNo(default=False))  # first-start wizard (#120)
_add("foscam_enabled", lambda: ConfigYesNo(default=False))
c.foscam_enabled.save_forced = True  # V2_MARKER
_add("foscam_priority", lambda: ConfigSelection(default="normal", choices=PRIORITIES()))
_add("foscam_mode", lambda: ConfigSelection(default="photo", choices=MODES()))
_add("foscam_seconds", lambda: ConfigSelectionNumber(5, 300, 5, default=30))
_add("foscam_interval", lambda: ConfigSelectionNumber(1, 60, 1, default=2))
_add("unifi_enabled", lambda: ConfigYesNo(default=False))
_add("unifi_kinds", lambda: ConfigText(default="ring,person", fixed_size=False))
_add("unifi_cameras", lambda: ConfigText(default="", fixed_size=False))
_add("unifi_priority", lambda: ConfigSelection(default="normal", choices=PRIORITIES()))
_add("unifi_mode", lambda: ConfigSelection(default="photo", choices=MODES() + [("log", _("Log only"))]))
_add("unifi_seconds", lambda: ConfigSelectionNumber(5, 300, 5, default=30))
_add("unifi_interval", lambda: ConfigSelectionNumber(2, 60, 1, default=5))
_add("unifi_rules", lambda: ConfigText(default="", fixed_size=False))
_add("unifi_camera_rules", lambda: ConfigText(default="", fixed_size=False))
_add("event_folder", lambda: ConfigText(default="/tmp/camalert_events", fixed_size=False))
_add("title_size", lambda: ConfigSelection(default="normal", choices=[
    ("small", _("Small")), ("normal", _("Normal")), ("large", _("Large"))]))
_add("update_check", lambda: ConfigYesNo(default=True))
_add("frigate_url", lambda: ConfigText(default="", fixed_size=False))
_add("update_checked", lambda: ConfigText(default="0", fixed_size=False))  # internal: time of the last check
_add("update_seen", lambda: ConfigText(default="", fixed_size=False))  # internal: newest version already announced
_add("chime", lambda: ConfigSelection(default="off", choices=[
    ("off", _("Off")), ("high", _("Doorbell and alarm")), ("all", _("Every request"))]))
_add("picons", lambda: ConfigYesNo(default=False))
_add("cooldown", lambda: ConfigText(default="", fixed_size=False))
_add("substreams", lambda: ConfigText(default="", fixed_size=False))
try:
    c.foscam_enabled.save()  # with save_forced the marker is written with the next configfile.save()
except Exception:
    pass
