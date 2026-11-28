# -*- coding: utf-8 -*-
# CamAlert for Kodi - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Pure Kodi-specific helpers (no xbmc imports), so they can be unit tested."""
import re
from urllib.parse import quote, urlsplit

from .camalert_core import schema
from .camalert_core.keymap import action_for, keys_for
from .camalert_core.layout import TITLE_SIZES, text_scale

# Kodi action ids (xbmcgui.ACTION_*)
ACTION_LEFT, ACTION_RIGHT, ACTION_UP, ACTION_DOWN = 1, 2, 3, 4
ACTION_PAGE_UP, ACTION_PAGE_DOWN, ACTION_SELECT = 5, 6, 7
ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_STOP = 10, 92, 13
ACTION_VOLUME_UP, ACTION_VOLUME_DOWN, ACTION_MUTE = 88, 89, 91
ACTION_PLAYER_PLAY, ACTION_PAUSE, ACTION_SHOW_INFO, ACTION_CONTEXT_MENU = 79, 12, 11, 117
ACTION_ENTER, ACTION_MOUSE_MOVE = 135, 107
ACTION_COLOUR = 122  # red/green/yellow/blue arrive as this action; which one is in the button code
ACTION_CHANNEL_UP, ACTION_CHANNEL_DOWN = 184, 185
# Kodi action ids -> key names of the key map (camalert_core.keymap, #42)
NAMES = {0: "NONE", ACTION_LEFT: "LEFT", ACTION_RIGHT: "RIGHT", ACTION_UP: "UP", ACTION_DOWN: "DOWN",
         ACTION_PAGE_UP: "PAGE_UP", ACTION_PAGE_DOWN: "PAGE_DOWN", ACTION_SELECT: "SELECT", ACTION_ENTER: "ENTER",
         ACTION_PREVIOUS_MENU: "PREVIOUS_MENU", ACTION_NAV_BACK: "BACK", ACTION_STOP: "STOP", ACTION_PAUSE: "PAUSE",
         ACTION_PLAYER_PLAY: "PLAY", ACTION_SHOW_INFO: "SHOW_INFO", ACTION_CONTEXT_MENU: "CONTEXT_MENU",
         ACTION_VOLUME_UP: "VOLUME_UP", ACTION_VOLUME_DOWN: "VOLUME_DOWN", ACTION_MUTE: "MUTE",
         ACTION_MOUSE_MOVE: "MOUSE_MOVE", ACTION_COLOUR: "COLOUR", ACTION_CHANNEL_UP: "CHANNEL_UP",
         ACTION_CHANNEL_DOWN: "CHANNEL_DOWN"}
CODES = {name: aid for aid, name in NAMES.items()}


def action_ids(context, action):
    """Kodi action ids of the keys that do `action` in `context`."""
    return tuple(CODES[k] for k in keys_for("kodi", context, action))


PASS_ACTIONS = set(action_ids("window", "pass"))
# keys that close the window and are then passed on to Kodi (so the user can keep zapping / navigating)
FORWARD = {ACTION_UP: "Up", ACTION_DOWN: "Down", ACTION_PAGE_UP: "PageUp", ACTION_PAGE_DOWN: "PageDown",
           ACTION_PAUSE: "Pause", ACTION_PLAYER_PLAY: "PlayPause", ACTION_STOP: "Stop", ACTION_SHOW_INFO: "Info",
           ACTION_CONTEXT_MENU: "ContextMenu"}

SCREEN_W, SCREEN_H = 1280, 720  # coordinate system of xbmcgui windows


def key_action(action_id):
    """What a remote key does while the photo window is open: live / prev / next / close / pass / close_pass
    (PTZ toggle keys are handled before this; anywhere else they close the window and do their normal job)."""
    a = action_for("kodi", "window", NAMES.get(action_id))
    return a if a in ("live", "prev", "next", "close", "pass") else "close_pass"


def forward_builtin(action_id):
    """Kodi built-in to replay a key after the window closed, or None."""
    name = FORWARD.get(action_id)
    return "Action(%s)" % name if name else None


def tour_key(action_id, button_code=0):
    """Keys in the full-screen tour: prev / next / hold / live / close / none. Colour keys arrive as one action
    (ACTION_COLOUR); the button code says which, so GREEN can be live like on Enigma2."""
    name = NAMES.get(action_id)
    if name == "COLOUR":
        name = (colour_name(button_code) or "").upper()
    return action_for("kodi", "tour", name) or "none"


def mosaic_key(action_id):
    """Keys in the full-screen mosaic: close / none."""
    return action_for("kodi", "mosaic", NAMES.get(action_id)) or "none"


def live_key(action_id):
    """Keys on the live view bar: prev / next / close / pause / ptz / None."""
    return action_for("kodi", "live", NAMES.get(action_id))


# --- settings --------------------------------------------------------------------------------------------------
DEFAULTS = {
    "enabled": True, "source": "go2rtc", "server": "", "more_servers": "", "rtsp_port": 8554,
    "verify_ssl": True, "camera_file": "", "camera": "", "titles": "", "mosaic": "",
    "orientation": "", "refresh": "", "strip_layout": "auto", "protect_snapshots": True, "ready_cameras": "",
    "privacy_masks": "", "guest_mode": False, "guest_cameras": "",
    "mode": "photo", "duration": 30, "position": "top_right", "size": "medium",
    "pause_tv": False, "video_window": "idle", "live_return": True, "live_volume": 100, "live_format": "mp4",
    "limit_hours": False, "from_time": "07:00", "until_time": "23:00", "skip_playing": "off",
    "alarm_wake": False, "tour_interval": 8, "max_windows": 2, "window_keys": True,
    "http_port": 8099, "allow": "lan", "token": "", "api_https": False,
    "mqtt_enabled": False, "mqtt_host": "", "mqtt_port": 1883, "mqtt_user": "", "mqtt_password": "",
    "mqtt_discovery": True, "mqtt_name": "",
    "dnd": False, "dnd_level": "normal",
    "frigate_enabled": False, "frigate_prefix": "frigate", "frigate_labels": "person", "frigate_map": "",
    "frigate_mode": "photo", "frigate_priority": "normal", "frigate_seconds": 30,
    "ptz_user": "", "ptz_password": "",
    "foscam_enabled": False, "foscam_interval": 2, "foscam_mode": "photo",
    "foscam_priority": "normal", "foscam_seconds": 30,
    "unifi_enabled": False, "unifi_kinds": "ring,person", "unifi_cameras": "", "unifi_priority": "normal",
    "unifi_mode": "photo", "unifi_seconds": 30, "unifi_interval": 5, "unifi_rules": "",
    "unifi_camera_rules": "",
    "log_level": "normal", "log_syslog": "", "allow_update": True, "ptz_key": "blue", "ha_buttons": True, "ha_webhook": "", "ha_webhook_secret": "", "wizard_done": False,
    "text_size": "normal", "priority_border": "steady", "language": "system",
    "title_size": "normal", "chime": "off", "speak": "high", "frigate_url": "", "cooldown": "", "substreams": "",
}
CHOICES = {
    "source": ("go2rtc", "direct"), "mode": ("photo", "live", "notify"),
    "position": ("top_right", "top_left", "bottom_right", "bottom_left"), "size": ("small", "medium", "large"),
    "skip_playing": ("off", "video", "all"), "allow": ("lan", "any"), "live_format": ("mp4", "hls", "rtsp"),
    "strip_layout": ("auto", "vertical", "horizontal", "grid"), "dnd_level": ("normal", "high"),
    "frigate_mode": ("photo", "live", "notify"), "frigate_priority": ("normal", "high", "alarm"),
    "foscam_mode": ("photo", "live", "notify"), "foscam_priority": ("normal", "high", "alarm"),
    "unifi_mode": ("photo", "live", "notify", "log"), "unifi_priority": ("normal", "high", "alarm"),
    "log_level": ("off", "errors", "normal", "verbose"), "ptz_key": ("blue", "yellow", "red", "green", "off"),
    "title_size": ("small", "normal", "large"), "chime": ("off", "high", "all"), "speak": ("off", "high", "all"),
    "text_size": ("normal", "large", "xlarge"), "priority_border": ("off", "steady", "flash"),
    "video_window": ("off", "idle", "pause"),
    "language": ("system", "en", "nl", "de", "fr", "it", "pl"),
}
RANGES = {"rtsp_port": (1, 65535), "duration": (5, 300), "frigate_seconds": (5, 300), "foscam_seconds": (5, 300),
          "foscam_interval": (1, 60), "unifi_seconds": (5, 300), "unifi_interval": (2, 60), "live_volume": (0, 100), "tour_interval": (3, 60), "max_windows": (1, 3), "http_port": (1024, 65535), "mqtt_port": (1, 65535)}


def parse_settings(raw):
    """Typed settings from Kodi's string values. Unknown or broken values fall back to the default."""
    out = {}
    for key, default in DEFAULTS.items():
        value = raw.get(key)
        if value is None or value == "":
            out[key] = default
            continue
        if isinstance(default, bool):
            out[key] = str(value).strip().lower() in ("true", "1", "yes", "on")
        elif isinstance(default, int):
            try:
                n = int(float(str(value).strip()))
            except ValueError:
                n = default
            lo, hi = RANGES.get(key, (n, n))
            out[key] = n if lo <= n <= hi else default
        elif key in CHOICES:
            v = str(value).strip()
            if v.isdigit() and int(v) < len(CHOICES[key]):  # Kodi stores the index for some spinner types
                v = CHOICES[key][int(v)]
            out[key] = v if v in CHOICES[key] else default
        elif key.endswith("password"):
            out[key] = str(value)
        else:
            out[key] = str(value).strip()
    return out


def saved_values(xml_text):
    """{id: value} of every setting in the add-on's settings file in the profile folder (Kodi 19+ writes
    '<setting id="x">value</setting>', Kodi 18 a value attribute). Unreadable file = {}."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError):
        return {}
    out = {}
    for el in root.iter("setting"):
        sid = el.get("id")
        if sid:
            out[sid] = el.get("value") if el.get("value") is not None else (el.text or "")
    return out


def migrations(saved):
    """Settings to write so a version-1 settings file keeps working with schema version 2 (#39): {key: value}
    for keys schema.migrate() renamed (live_resume -> live_return, refresh_map -> refresh) when the new key is
    not in the file yet (so a later change by the user always wins), and for values it changed; only settings
    this add-on has. Empty when nothing needs to change."""
    new = schema.migrate(saved, "kodi")
    return {k: v for k, v in new.items() if k in DEFAULTS and saved.get(k) != v}


# --- what is playing ------------------------------------------------------------------------------------------
def playing_kind(file, is_livetv, is_video):
    """'none' / 'livetv' / 'camera' / 'video' (movie, episode or recording)."""
    if not file:
        return "none"
    if "camalert=1" in file or "/api/stream." in file or file.startswith(("rtsp://", "rtsps://")):
        return "camera"
    if is_livetv or file.startswith("pvr://channels"):
        return "livetv"
    return "video" if is_video else "none"


def blocked_by_playing(setting, kind):
    """Setting 'video': no normal-priority pop-ups while a movie/episode/recording plays; 'all': also live TV."""
    if setting == "video":
        return kind == "video"
    if setting == "all":
        return kind in ("video", "livetv")
    return False


def video_window_mode(setting, busy, kind, priority, rotated=False):
    """#129: how the photo window shows a camera on Kodi. 'idle': the camera's live stream as video in the window
    (nothing plays); 'pause': stop what plays, video in the window, then play it again from where it was; None:
    snapshots as before (something plays that the setting does not pause, music, a camera, or a turned camera:
    Kodi cannot turn a video in a window). Priority alarm pauses a film or live TV unless the setting is off."""
    if setting not in ("idle", "pause") or rotated:
        return None
    if not busy:
        return "idle"
    if kind in ("video", "livetv") and (setting == "pause" or priority == "alarm"):
        return "pause"
    return None


def _xml_text(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


VIDEO_TITLE, VIDEO_HINT, VIDEO_STILL = 102, 104, 101
VIDEO_FRAME = (110, 111, 112, 113)
VIDEO_MASKS = tuple(range(120, 128))  # privacy mask boxes over the video (#11), placed from Python


def video_window_xml(x, y, w, h, t, title_font, hint_font, hint_h, mark=None, masks=False):
    """Skin XML (720p coordinates, like SCREEN_W/SCREEN_H) of the video window (#129): dark background, the still
    picture (window property 'still') under the video window (so the first picture shows until the video runs),
    title bar on top, key hint strip at the bottom, and the priority frame (#48) when mark is set. Label texts are
    set from Python (VIDEO_TITLE, VIDEO_HINT); the frame bars (VIDEO_FRAME) flash from Python too."""
    total = h + t
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<window>", "  <zorder>2</zorder>", "  <controls>"]

    def image(cid, cx, cy, cw, ch, texture, colour=None, extra=""):
        idattr = ' id="%d"' % cid if cid else ""
        diffuse = ' colordiffuse="%s"' % colour if colour else ""
        parts.append('    <control type="image"%s><left>%d</left><top>%d</top><width>%d</width><height>%d</height>'
                     '%s<texture%s>%s</texture></control>' % (idattr, cx, cy, cw, ch, extra, diffuse, texture))

    def label(cid, cx, cy, cw, ch, font, colour, align):
        parts.append('    <control type="label" id="%d"><left>%d</left><top>%d</top><width>%d</width>'
                     '<height>%d</height><font>%s</font><textcolor>%s</textcolor><align>%s</align>'
                     '<aligny>center</aligny><label></label></control>'
                     % (cid, cx, cy, cw, ch, _xml_text(font), colour, align))

    image(100, x, y, w, total, "white.png", "FF202020")
    image(VIDEO_STILL, x, y + t, w, h, "$INFO[Window.Property(still)]", extra="<aspectratio>keep</aspectratio>")
    parts.append('    <control type="videowindow"><left>%d</left><top>%d</top><width>%d</width><height>%d</height>'
                 '</control>' % (x, y + t, w, h))
    if masks:  # #11: black boxes over the video, sized from Python (0 x 0 = nothing until then)
        for cid in VIDEO_MASKS:
            image(cid, x, y + t, 0, 0, "white.png", "FF000000")
    label(VIDEO_TITLE, x + 8, y, w - 16, t, title_font, "FFFFFFFF", "left")
    image(103, x, y + total - hint_h, w, hint_h, "white.png", "99000000")
    label(VIDEO_HINT, x + 8, y + total - hint_h, w - 16, hint_h, hint_font, "FFDDDDDD", "center")
    if mark:
        b, colour = 6, "FF" + mark["colour"].lstrip("#")
        for cid, (fx, fy, fw, fh) in zip(VIDEO_FRAME, ((x, y, w, b), (x, y + total - b, w, b), (x, y, b, total),
                                                       (x + w - b, y, b, total))):
            image(cid, fx, fy, fw, fh, "white.png", colour)
    parts += ["  </controls>", "</window>", ""]
    return "\n".join(parts)


def resume_plan(file, position, kind, paused=False):
    """What to play again after the live camera: dict(file, seek, paused) or None."""
    if kind not in ("video", "livetv") or not file:
        return None
    seek = max(0.0, float(position or 0) - 2.0) if kind == "video" else 0.0
    return {"file": file, "seek": seek, "paused": bool(paused) and kind == "video"}


def live_url(server, stream, fmt="mp4", rtsp_port=8554):
    """URL Kodi plays for the live camera: go2rtc 'mp4' (HTTP), 'hls' (HTTP, a few seconds behind) or 'rtsp'."""
    p = urlsplit(server or "")
    if not p.hostname or not stream:
        return None
    if fmt == "rtsp":
        host = "[%s]" % p.hostname if ":" in p.hostname else p.hostname
        return "rtsp://%s:%d/%s" % (host, int(rtsp_port), quote(stream, safe="_.-"))
    ext = "m3u8" if fmt == "hls" else "mp4"
    return "%s/api/stream.%s?src=%s&camalert=1" % (server.rstrip("/"), ext, quote(stream, safe="_.-"))


MIME_TYPES = {".mp4": "video/mp4", ".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}


def live_mime(url):
    """Mime type to set on the ListItem: with it (and content lookup off) Kodi skips its HTTP probe, which waits
    20 seconds on an endless camera stream."""
    path = urlsplit(url or "").path
    for ext, mime in MIME_TYPES.items():
        if path.endswith(ext):
            return mime
    return ""


def kodi_volume(current, percent):
    return max(0, min(100, int(round(float(current) * max(0, min(100, int(percent))) / 100.0))))


def node_from_mac(mac, fallback="kodi"):
    m = re.sub(r"[^0-9a-f]", "", (mac or "").lower())
    return m if len(m) == 12 and m != "000000000000" else re.sub(r"[^a-z0-9]+", "_", fallback.lower()).strip("_") or "kodi"


def frame_name(prefix, counter, keep=3):
    """(new file, file to delete): every picture gets a new name (Kodi caches images by path); only the last
    `keep` files stay on disk."""
    return "%s_%d.jpg" % (prefix, counter), "%s_%d.jpg" % (prefix, counter - keep)


# --- camera control (PTZ) ------------------------------------------------------------------------------------
PTZ_TOGGLE = action_ids("window", "ptz")


def ptz_action(action_id):
    """Kodi key in PTZ mode -> up/down/left/right/zoom_in/zoom_out/home/leave (names of devices.ptz), or None
    (volume keys and everything else)."""
    a = action_for("kodi", "ptz", NAMES.get(action_id))
    return None if a == "pass" else a


def with_default_login(devs, user, password):
    """Fills in the add-on's default camera login where devices.conf has none."""
    out = {}
    for name, d in devs.items():
        d = dict(d)
        if not d.get("user") and user:
            d["user"] = user
        if not d.get("password") and password:
            d["password"] = password
        out[name] = d
    return out


# The add-on's default camera password lives in devices.conf, not in settings.xml (#55): one line
# '*|default|*|user|password'. parse_devices (both players) skips it because 'default' is no device type.
DEFAULT_LOGIN = "*|default|*"


def _is_default_login(line):
    parts = line.strip().split("|", 2)
    return len(parts) >= 2 and parts[0].strip() == "*" and parts[1].strip().lower() == "default"


def stored_default_login(text):
    """(user, password) of the default-login line in devices.conf text, ('', '') when there is none."""
    for line in (text or "").splitlines():
        if _is_default_login(line):
            parts = line.strip().split("|", 4)
            return (parts[3].strip() if len(parts) > 3 else "", parts[4] if len(parts) > 4 else "")
    return "", ""


def with_default_password(text, password):
    """devices.conf text with the default camera password set ('' removes it). Every other line stays as it is;
    there is never more than one default-login line; a user written there by hand is kept."""
    password = (password or "").replace("\r", "").replace("\n", "")
    user = stored_default_login(text)[0]
    lines = [line for line in (text or "").splitlines() if not _is_default_login(line)]
    if password:
        lines.append("%s|%s|%s" % (DEFAULT_LOGIN, user, password))
    return "\n".join(lines) + "\n" if lines else ""


# --- colour keys, title size, chime ---------------------------------------------------------------------------
# Kodi button codes of the colour keys (measured on Kodi 21): remote and CEC (251-254) and keyboard F1-F4 (KEY_VKEY | VK_F1..)
COLOUR_BUTTONS = {251: "red", 252: "green", 253: "yellow", 254: "blue",
                  0xF070: "red", 0xF071: "green", 0xF072: "yellow", 0xF073: "blue"}


def colour_name(button_code):
    """'red' / 'green' / 'yellow' / 'blue' for a Kodi colour key (remote, CEC or F1-F4), or None."""
    return COLOUR_BUTTONS.get(button_code & 0xFFFF if button_code else 0)


SAFE_FONT = "font13"  # the only font every Kodi skin has (Kodi itself falls back to it)


def skin_font_sizes(font_xml):
    """{font name: size} of the first fontset in a skin's Font.xml ({} if unreadable)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(font_xml)
    except (ET.ParseError, TypeError, ValueError):
        return {}
    for fontset in root.iter("fontset"):
        out = {}
        for f in fontset.iter("font"):
            name, size = (f.findtext("name") or "").strip(), (f.findtext("size") or "").strip()
            if name and size.isdigit():
                out[name] = int(size)
        return out
    return {}


def font_for_ratio(ratio, fonts=None):
    """Skin font about `ratio` times font13 (#46, #48). Skins only guarantee font13 (Estuary has no font30), so
    ratio 1 is always font13 and other ratios pick a plain 'fontNN' of the current skin (fonts = {name: size}, see
    skin_font_sizes) whose size is closest below the target: smaller resp. larger than font13. Unknown skin fonts
    or nothing suitable: font13."""
    fonts = fonts or {}
    base = fonts.get(SAFE_FONT)
    if not base or abs(ratio - 1.0) < 0.01:
        return SAFE_FONT
    target = base * ratio
    plain = [(size, name) for name, size in fonts.items() if re.match(r"^font\d+$", name) and size <= target + 0.5]
    plain = [p for p in plain if (p[0] > base if ratio > 1 else p[0] < base)]
    return max(plain)[1] if plain else SAFE_FONT


def title_font_name(title_size, fonts=None, text_size="normal"):
    """Skin font for the photo-window title: the title size (layout.TITLE_SIZES) times the text size (#48)."""
    ratio = TITLE_SIZES.get(title_size, TITLE_SIZES["normal"])[1] / float(TITLE_SIZES["normal"][1])
    return font_for_ratio(ratio * text_scale(text_size), fonts)


def text_font_name(text_size, fonts=None):
    """Skin font for the other CamAlert texts (hints, mosaic labels, tour, live bar) at the text size (#48)."""
    return font_for_ratio(text_scale(text_size), fonts)


def chime_wanted(setting, priority):
    """Doorbell sound: 'off', 'high' (doorbell and alarm) or 'all' requests."""
    return setting == "all" or (setting == "high" and priority in ("high", "alarm"))


def os_label(info, busy, fallback):
    """The OS for the diagnostics (#59): Kodi fills System.OSVersionInfo asynchronously and answers "Busy"
    (translated, string 503) or nothing at first; then the fallback (Python's platform) is used."""
    info = (info or "").strip()
    if not info or info.lower() in {b.strip().lower() for b in busy if b and b.strip()}:
        return fallback
    return info
