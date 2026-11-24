# -*- coding: utf-8 -*-
# CamAlert for Kodi - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Pure Kodi-specific helpers (no xbmc imports), so they can be unit tested."""
import re
from urllib.parse import quote, urlsplit

# Kodi action ids (xbmcgui.ACTION_*)
ACTION_LEFT, ACTION_RIGHT, ACTION_UP, ACTION_DOWN = 1, 2, 3, 4
ACTION_PAGE_UP, ACTION_PAGE_DOWN, ACTION_SELECT = 5, 6, 7
ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_STOP = 10, 92, 13
ACTION_VOLUME_UP, ACTION_VOLUME_DOWN, ACTION_MUTE = 88, 89, 91
ACTION_PLAYER_PLAY, ACTION_PAUSE, ACTION_SHOW_INFO, ACTION_CONTEXT_MENU = 79, 12, 11, 117
ACTION_ENTER, ACTION_MOUSE_MOVE = 135, 107
PASS_ACTIONS = {ACTION_VOLUME_UP, ACTION_VOLUME_DOWN, ACTION_MUTE, ACTION_MOUSE_MOVE, 0}
# keys that close the window and are then passed on to Kodi (so the user can keep zapping / navigating)
FORWARD = {ACTION_UP: "Up", ACTION_DOWN: "Down", ACTION_PAGE_UP: "PageUp", ACTION_PAGE_DOWN: "PageDown",
           ACTION_PAUSE: "Pause", ACTION_PLAYER_PLAY: "PlayPause", ACTION_STOP: "Stop", ACTION_SHOW_INFO: "Info",
           ACTION_CONTEXT_MENU: "ContextMenu"}

SCREEN_W, SCREEN_H = 1280, 720  # coordinate system of xbmcgui windows


def key_action(action_id):
    """What a remote key does while the photo window is open: live / prev / next / close / pass / close_pass."""
    if action_id in (ACTION_SELECT, ACTION_ENTER):
        return "live"
    if action_id == ACTION_LEFT:
        return "prev"
    if action_id == ACTION_RIGHT:
        return "next"
    if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
        return "close"
    if action_id in PASS_ACTIONS:
        return "pass"
    return "close_pass"


def forward_builtin(action_id):
    """Kodi built-in to replay a key after the window closed, or None."""
    name = FORWARD.get(action_id)
    return "Action(%s)" % name if name else None


def tour_key(action_id):
    """Keys in the full-screen tour: prev / next / hold / live / close / none."""
    if action_id == ACTION_LEFT:
        return "prev"
    if action_id == ACTION_RIGHT:
        return "next"
    if action_id in (ACTION_SELECT, ACTION_ENTER):
        return "hold"
    if action_id in (ACTION_PLAYER_PLAY, ACTION_UP):
        return "live"
    if action_id in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_STOP):
        return "close"
    return "none"


# --- settings --------------------------------------------------------------------------------------------------
DEFAULTS = {
    "enabled": True, "source": "go2rtc", "server": "http://192.168.1.10:1984", "rtsp_port": 8554,
    "verify_ssl": True, "camera_file": "", "camera": "", "titles": "", "mosaic": "",
    "orientation": "", "refresh_map": "", "strip_layout": "auto",
    "mode": "photo", "duration": 30, "position": "top_right", "size": "medium",
    "pause_tv": False, "live_resume": True, "live_volume": 100, "live_format": "mp4",
    "limit_hours": False, "from_time": "07:00", "until_time": "23:00", "skip_playing": "off",
    "alarm_wake": False, "tour_interval": 8, "window_keys": True,
    "http_port": 8099, "allow": "lan", "token": "", "api_https": False,
    "mqtt_enabled": False, "mqtt_host": "", "mqtt_port": 1883, "mqtt_user": "", "mqtt_password": "",
    "mqtt_discovery": True, "mqtt_name": "",
    "dnd": False, "dnd_level": "normal",
    "frigate_enabled": False, "frigate_prefix": "frigate", "frigate_labels": "person", "frigate_map": "",
    "frigate_mode": "photo", "frigate_priority": "normal", "frigate_seconds": 30,
    "ptz_user": "", "ptz_password": "",
    "foscam_enabled": False, "foscam_interval": 2, "foscam_mode": "photo",
    "foscam_priority": "normal", "foscam_seconds": 30,
}
CHOICES = {
    "source": ("go2rtc", "direct"), "mode": ("photo", "live", "notify"),
    "position": ("top_right", "top_left", "bottom_right", "bottom_left"), "size": ("small", "medium", "large"),
    "skip_playing": ("off", "video", "all"), "allow": ("lan", "any"), "live_format": ("mp4", "hls", "rtsp"),
    "strip_layout": ("auto", "vertical", "horizontal", "grid"), "dnd_level": ("normal", "high"),
    "frigate_mode": ("photo", "live", "notify"), "frigate_priority": ("normal", "high", "alarm"),
    "foscam_mode": ("photo", "live", "notify"), "foscam_priority": ("normal", "high", "alarm"),
}
RANGES = {"rtsp_port": (1, 65535), "duration": (5, 300), "frigate_seconds": (5, 300), "foscam_seconds": (5, 300),
          "foscam_interval": (1, 60), "live_volume": (0, 100), "tour_interval": (3, 60), "http_port": (1024, 65535), "mqtt_port": (1, 65535)}


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
PTZ_TOGGLE = (ACTION_CONTEXT_MENU, ACTION_SHOW_INFO)


def ptz_action(action_id):
    """Kodi key in PTZ mode -> up/down/left/right/zoom_in/zoom_out/home/leave (names of devices.ptz), or None."""
    return {ACTION_UP: "up", ACTION_DOWN: "down", ACTION_LEFT: "left", ACTION_RIGHT: "right",
            ACTION_PAGE_UP: "zoom_in", 184: "zoom_in", ACTION_PAGE_DOWN: "zoom_out", 185: "zoom_out",
            ACTION_SELECT: "home", ACTION_ENTER: "home", ACTION_PREVIOUS_MENU: "leave", ACTION_NAV_BACK: "leave",
            ACTION_CONTEXT_MENU: "leave", ACTION_SHOW_INFO: "leave"}.get(action_id)


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
