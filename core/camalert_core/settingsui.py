# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""How the settings screens are laid out, the same on every player (#130).

- The first screen holds the basic settings; every other setting lives in the screen of its section.
- A setting that only matters while another one has a certain value is hidden otherwise (DEPENDS): turning
  Frigate, Foscam, UniFi Protect or MQTT on shows their fields, turning them off hides them again.
- Expert settings only show after "More settings" (a player keeps that choice).

Everything is data from the schema: a new setting lands in the right screen by its section and level, and a
new dependency only needs a line in DEPENDS. Kodi's settings.xml carries the same dependencies as
<dependency type="visible"> (checked by tests/kodi/test_settings_schema.py); Android TV gets them via core.json.
"""
from . import schema

# setting id -> (setting id it depends on, values of that setting for which it applies)
DEPENDS = {
    # go2rtc only
    "server": ("source", ("go2rtc",)), "more_servers": ("source", ("go2rtc",)), "rtsp_port": ("source", ("go2rtc",)),
    "substreams": ("source", ("go2rtc",)), "titles": ("source", ("go2rtc",)), "orientation": ("source", ("go2rtc",)),
    "refresh": ("source", ("go2rtc",)), "cooldown": ("source", ("go2rtc",)), "camera_file": ("source", ("direct",)),
    # the photo window / live view
    "position": ("mode", ("photo",)), "size": ("mode", ("photo",)), "window_keys": ("mode", ("photo",)),
    "title_size": ("mode", ("photo",)), "strip_layout": ("mode", ("photo",)),
    "pause_tv": ("mode", ("photo", "notify")), "live_return": ("mode", ("live",)), "live_volume": ("mode", ("live",)),
    # active hours
    "from_time": ("limit_hours", (True,)), "until_time": ("limit_hours", (True,)),
    # MQTT, and Frigate over MQTT
    "mqtt_host": ("mqtt_enabled", (True,)), "mqtt_port": ("mqtt_enabled", (True,)),
    "mqtt_user": ("mqtt_enabled", (True,)), "mqtt_password": ("mqtt_enabled", (True,)),
    "mqtt_discovery": ("mqtt_enabled", (True,)), "mqtt_name": ("mqtt_enabled", (True,)),
    "frigate_enabled": ("mqtt_enabled", (True,)),
    "frigate_prefix": ("frigate_enabled", (True,)), "frigate_labels": ("frigate_enabled", (True,)),
    "frigate_map": ("frigate_enabled", (True,)), "frigate_priority": ("frigate_enabled", (True,)),
    "frigate_url": ("frigate_enabled", (True,)), "frigate_mode": ("frigate_enabled", (True,)),
    "frigate_seconds": ("frigate_enabled", (True,)),
    # Foscam and UniFi Protect
    "foscam_priority": ("foscam_enabled", (True,)), "foscam_interval": ("foscam_enabled", (True,)),
    "foscam_mode": ("foscam_enabled", (True,)), "foscam_seconds": ("foscam_enabled", (True,)),
    "unifi_kinds": ("unifi_enabled", (True,)), "unifi_cameras": ("unifi_enabled", (True,)),
    "unifi_priority": ("unifi_enabled", (True,)), "unifi_mode": ("unifi_enabled", (True,)),
    "unifi_seconds": ("unifi_enabled", (True,)), "unifi_interval": ("unifi_enabled", (True,)),
    "unifi_rules": ("unifi_enabled", (True,)), "unifi_camera_rules": ("unifi_enabled", (True,)),
}
# Certificates only matter with https (or direct mode, where a camera can be https): not one parent value.
HTTPS_ONLY = ("verify_ssl",)
LEVEL_ORDER = {"basic": 0, "advanced": 1, "expert": 2}


def _value(values, sid, platform=None):
    s = schema.BY_ID.get(sid)
    if s is None:
        return values.get(sid)
    key = s.key(platform) if platform else sid
    if key in values:
        return values[key]
    return values.get(sid, s.default_for(platform))


def applies(sid, values, platform=None):
    """Whether setting sid matters with these values ({id or platform key: value}); follows the chain (Frigate
    needs MQTT). A setting whose parent the player lacks always applies."""
    seen = set()
    while sid not in seen:
        seen.add(sid)
        if sid in HTTPS_ONLY:
            if _value(values, "source", platform) == "go2rtc" and \
                    not str(_value(values, "server", platform) or "").strip().lower().startswith("https"):
                return False
        dep = DEPENDS.get(sid)
        if dep is None:
            return True
        parent, allowed = dep
        p = schema.BY_ID.get(parent)
        if p is None or (platform and platform not in p.platforms):
            return True
        if _value(values, parent, platform) not in allowed:
            return False
        sid = parent
    return True


def _shown(platform):
    return [s for s in schema.for_platform(platform) if s.level != "internal"]


def main_settings(platform, values):
    """The basic settings that apply, in schema order: the first screen."""
    return [s for s in _shown(platform) if s.level == "basic" and applies(s.id, values, platform)]


def sections(platform):
    """Sections that have settings besides the basic ones on this player, in schema order."""
    have = {s.section for s in _shown(platform) if s.level != "basic"}
    return [x for x in schema.SECTIONS if x in have]


def section_settings(section, platform, values, expert=False):
    """The settings of one section's screen: not basic (those are on the first screen), expert ones only with
    "More settings", and only those that apply."""
    top = LEVEL_ORDER["expert" if expert else "advanced"]
    return [s for s in _shown(platform) if s.section == section and s.level != "basic"
            and LEVEL_ORDER[s.level] <= top and applies(s.id, values, platform)]


def hidden_expert(section, platform, values):
    """How many expert settings "More settings" would add to this section's screen."""
    return len(section_settings(section, platform, values, True)) - len(section_settings(section, platform, values))


def switches(section, platform):
    """On/off settings of a section that other settings depend on (Frigate, MQTT ...): shown in the summary."""
    parents = {p for p, _v in DEPENDS.values()}
    return [s for s in _shown(platform) if s.section == section and s.type == "bool" and s.id in parents
            and s.level != "basic"]


def section_summary(section, platform, values):
    """(label msgids of the switches that are on, number of other settings that differ from the default) for the
    line of a section on the first screen; the player translates and joins them."""
    on = [s.label for s in switches(section, platform) if _value(values, s.id, platform) is True]
    sw = {s.id for s in switches(section, platform)}
    changed = 0
    for s in _shown(platform):
        if s.section != section or s.level == "basic" or s.id in sw:
            continue
        if _value(values, s.id, platform) != s.default_for(platform):
            changed += 1
    return on, changed


def chain(sid, platform):
    """[(parent key, allowed values), ...] that must all hold for setting sid on a platform: its own parent first,
    then the parent's parent (Kodi's settings.xml writes them as one visible condition, #130)."""
    out, seen = [], set()
    while sid in DEPENDS and sid not in seen:
        seen.add(sid)
        parent, allowed = DEPENDS[sid]
        p = schema.BY_ID.get(parent)
        if p is None or platform not in p.platforms:
            break
        out.append((p.key(platform), tuple(allowed)))
        sid = parent
    return out
