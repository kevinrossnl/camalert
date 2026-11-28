# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""When a camera is shown: modes, durations, priorities, do not disturb, active hours, cooldown."""


MODES = ("photo", "live", "notify")
MIN_SECONDS, MAX_SECONDS = 5, 300
# sec=0 on show (#81): the window stays until hide or a new show, e.g. as long as there is motion; at most this long,
# so a missed hide never leaves it on screen for good.
HOLD_SECONDS = 600


def clamp_seconds(value, default=30):
    try:
        s = int(value)
    except (TypeError, ValueError, OverflowError):  # OverflowError: float('inf') (#34)
        return default
    return max(MIN_SECONDS, min(MAX_SECONDS, s))


def show_seconds(value, default=30):
    """Duration of a show request: 0 = until hide (#81), at most HOLD_SECONDS; otherwise clamp_seconds."""
    try:
        if int(value) == 0:
            return HOLD_SECONDS
    except (TypeError, ValueError, OverflowError):  # OverflowError: float('inf'), as in clamp_seconds (#34)
        pass
    return clamp_seconds(value, default)


def has_seconds(value):
    """True when a request gives a duration (0 counts: until hide, #81); False for missing, empty or false."""
    return value is not None and value is not False and str(value).strip() != ""


def pick_mode(value, default="photo"):
    return value if value in MODES else default


def decide(in_standby, current_stream, window_stream, requested_stream):
    """What to do for a request: 'ignore', 'extend' or 'show'."""
    if in_standby or not requested_stream:
        return "ignore"
    if current_stream == requested_stream:  # already watching this camera
        return "ignore"
    if window_stream == requested_stream:
        return "extend"
    return "show"


def should_pause(enabled, mode, watching_camera):
    """Pause (timeshift) the TV only for photo window / notification while watching a normal channel."""
    return bool(enabled) and mode in ("photo", "notify") and not watching_camera


def in_time_window(now, start, end):
    """now/start/end as (hour, minute). The window may pass midnight (22:00-06:00). start == end means all day."""
    n, a, b = now[0] * 60 + now[1], start[0] * 60 + start[1], end[0] * 60 + end[1]
    if a == b:
        return True
    return a <= n < b if a < b else n >= a or n < b


def lowered_volume(current, percent):
    """Volume while the live camera is shown: percent of the current volume (100 = unchanged)."""
    return max(0, min(100, int(round(current * max(0, min(100, int(percent))) / 100.0))))


PRIORITIES = ("normal", "high", "alarm")


def pick_priority(value):
    return value if value in PRIORITIES else "normal"


def blocked_by_rules(priority, limit_hours, in_hours, skip_recording, recording, skip_media=False, playing_media=False):
    """Receiver rules (active hours, not while recording, not while playing a recording/media file) only apply
    to normal priority."""
    if priority != "normal":
        return False
    return bool((limit_hours and not in_hours) or (skip_recording and recording) or (skip_media and playing_media))


DND_LEVELS = ("normal", "high")


def dnd_blocks(priority, dnd_on, level="normal"):
    """Do not disturb: blocks normal priority; with level 'high' also high priority. Alarm always passes."""
    if not dnd_on or priority == "alarm":
        return False
    return priority == "normal" or (level == "high" and priority == "high")


def clock_tuple(value):
    """(hour, minute) from a ConfigClock value: [h, m], (h, m), 'HH:MM' or seconds since midnight."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return int(value[0]) % 24, int(value[1]) % 60
    if isinstance(value, str) and ":" in value:
        h, m = value.strip().split(":")[:2]
        return int(h) % 24, int(m) % 60
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0, 0
    return (n // 3600) % 24, (n // 60) % 60


def cooldown_seconds(name, text):
    """'*=30|garden=120' -> seconds for this camera (0 = no cooldown)."""
    m = dict(p.split("=", 1) for p in (x.strip() for x in (text or "").split("|")) if "=" in p)
    m = {k.strip(): v.strip() for k, v in m.items()}
    for key in (name, "*"):
        try:
            return max(0, min(3600, int(float(m[key]))))
        except (KeyError, ValueError):
            continue
    return 0


def in_cooldown(last_shown, now, seconds):
    """A camera shown less than `seconds` ago is not shown again (an open window is still extended)."""
    return bool(seconds) and last_shown is not None and 0 <= now - last_shown < seconds
