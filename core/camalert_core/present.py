# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""What the players show as text (#41): event-list values as codes with translated labels, dates, and the
on-screen key hints built from the key map (keymap.KEYMAP), so text and behaviour cannot drift.

Every function takes `tr` (msgid -> translated text, see i18n.py). Events keep codes, never English:

    event = {"time", "camera", "label", "source": SOURCES, "priority": PRIORITIES, "action": RESULTS,
             "reason": reason(code[, seconds])}
    reason codes: REASONS; stored as "code" or "code:<number>" (cooldown), also in the API /events answer.
"""
import time as _time

from .i18n import N_
from .keymap import KEYMAP

# --- event list values ------------------------------------------------------------------------------------------
SOURCE_LABELS = {
    "api": N_("API"), "ha": N_("Home Assistant"), "mqtt": N_("MQTT"), "frigate": N_("Frigate"),
    "foscam": N_("Foscam"), "menu": N_("Menu"), "wake": N_("Wake up"),
}
SOURCES = tuple(SOURCE_LABELS)
PRIORITY_LABELS = {"normal": N_("Normal"), "high": N_("High"), "alarm": N_("Alarm")}  # glossary (#2)
PRIORITIES = ("normal", "high", "alarm")
RESULT_LABELS = {"show": N_("Shown"), "extend": N_("Extended"), "ignore": N_("Ignored"), "error": N_("Error"),
                 "wake": N_("Woken up")}
RESULTS = tuple(RESULT_LABELS)
REASON_LABELS = {
    "dnd": N_("Do not disturb"),
    "outside_hours": N_("Outside the chosen times"),
    "recording": N_("Recording in progress"),
    "playing": N_("Something is playing"),
    "standby": N_("In standby"),
    "screen_off": N_("Screen off"),
    "woken": N_("Woken up from standby"),
    "cooldown": N_("Cooldown (%d s)"),
    "on_screen": N_("Already on screen"),
    "no_camera": N_("No camera given and no default camera set"),
    "unknown_camera": N_("Unknown camera"),
    "no_address": N_("Unknown camera or no valid go2rtc address"),
    "unreachable": N_("Camera not reachable"),
}
REASONS = tuple(REASON_LABELS)
WITH_NUMBER = ("cooldown",)
# English reason texts of players before #41 -> code (events saved by an older version)
LEGACY_REASONS = {
    "do not disturb": "dnd", "outside active hours": "outside_hours", "recording": "recording",
    "media playback": "playing", "playing": "playing", "standby": "standby", "screen off": "screen_off",
    "receiver was in standby: woken up": "woken", "already on screen": "on_screen", "no camera": "no_camera",
    "unknown camera": "unknown_camera", "unknown camera or no valid go2rtc address": "no_address",
}


def reason(code, number=None):
    """The stored form of a reason: 'dnd', 'cooldown:30'. ValueError for an unknown code."""
    if code not in REASON_LABELS:
        raise ValueError("unknown reason %r" % code)
    if code in WITH_NUMBER:
        return "%s:%d" % (code, int(number or 0))
    return code


def parse_reason(text):
    """(code, number or None) of a stored reason (also the English texts of older players); (None, None) for
    an empty reason, (text, None) for something unknown."""
    t = (text or "").strip()
    if not t:
        return None, None
    code, _sep, number = t.partition(":")
    if code in REASON_LABELS:
        try:
            return code, int(number) if code in WITH_NUMBER else None
        except ValueError:
            return code, 0
    low = t.lower()
    if low in LEGACY_REASONS:
        return LEGACY_REASONS[low], None
    if low.startswith("cooldown (") and low.endswith(" s)"):
        digits = low[len("cooldown ("):-3]
        return "cooldown", int(digits) if digits.isdigit() else 0
    return t, None


def _label(table, code, tr):
    return tr(table[code]) if code in table else (code or "")


def source_label(code, tr):
    return _label(SOURCE_LABELS, code, tr)


def priority_label(code, tr):
    return _label(PRIORITY_LABELS, code, tr)


def result_label(code, tr):
    return _label(RESULT_LABELS, code, tr)


def reason_label(text, tr):
    """Translated reason ('' for none; an unknown value is shown as it is)."""
    code, number = parse_reason(text)
    if code is None:
        return ""
    if code not in REASON_LABELS:
        return code
    label = tr(REASON_LABELS[code])
    return label % (number or 0) if code in WITH_NUMBER else label


# --- dates ---------------------------------------------------------------------------------------------------------
DATE_FORMATS = {"en": "%d/%m/%Y", "nl": "%d-%m-%Y", "de": "%d.%m.%Y", "fr": "%d/%m/%Y", "it": "%d/%m/%Y",
                "pl": "%d.%m.%Y"}


def date_format(language):
    """strftime date format of a language ('nl', 'de_DE', 'fr-FR', ...); English (UK) for anything else.
    Kodi can pass its own region format instead (xbmc.getRegion('dateshort'))."""
    lang = (language or "").replace("-", "_").split("_")[0].lower()
    return DATE_FORMATS.get(lang, DATE_FORMATS["en"])


def event_time(ts, language=None, date=True, fmt=None):
    """'24-11-2026 14:03:05' (date in the language's format) or '14:03:05' (date=False)."""
    t = _time.localtime(ts)
    clock = _time.strftime("%H:%M:%S", t)
    if not date:
        return clock
    return "%s %s" % (_time.strftime(fmt or date_format(language), t), clock)


# --- event list ----------------------------------------------------------------------------------------------------
def event_line(e, tr):
    """One line of the event list: '14:03:05  front_door · Person  (Frigate, High) -> Shown'."""
    who = (" · " + e["label"]) if e.get("label") else ""
    return "%s  %s%s  (%s, %s) -> %s" % (event_time(e["time"], date=False), e["camera"], who,
                                          source_label(e.get("source"), tr), priority_label(e.get("priority"), tr),
                                          result_label(e.get("action"), tr))


def event_details(e, tr, language=None, fmt=None):
    """[(label, value)] for the detail pane of one event: time, camera, source, priority, result, reason."""
    rows = [(tr(N_("Time")), event_time(e["time"], language, fmt=fmt)),
            (tr(N_("Camera")), e["camera"] + ((" · " + e["label"]) if e.get("label") else "")),
            (tr(N_("Source")), source_label(e.get("source"), tr)),
            (tr(N_("Priority")), priority_label(e.get("priority"), tr)),
            (tr(N_("Result")), result_label(e.get("action"), tr))]
    why = reason_label(e.get("reason"), tr)
    if why:
        rows.append((tr(N_("Reason")), why))
    return rows


# --- key hints -------------------------------------------------------------------------------------------------------
# How a key is printed in a hint (the label on the remote: not translated, except the colour keys).
KEY_NAMES = {
    "enigma2": {"OK": "OK", "EXIT": "EXIT", "LEFT": "◀", "RIGHT": "▶", "UP": "▲", "DOWN": "▼", "CHANNEL_UP": "CH+",
                "CHANNEL_DOWN": "CH-", "GREEN": N_("GREEN"), "PLAY": "PLAY"},
    "kodi": {"SELECT": "OK", "ENTER": "OK", "PREVIOUS_MENU": "BACK", "BACK": "BACK", "STOP": "STOP", "LEFT": "◀",
             "RIGHT": "▶", "UP": "▲", "DOWN": "▼", "PAGE_UP": "CH+", "CHANNEL_UP": "CH+", "PAGE_DOWN": "CH-",
             "CHANNEL_DOWN": "CH-", "CONTEXT_MENU": "MENU", "SHOW_INFO": "INFO", "PLAY": "PLAY", "PAUSE": "PAUSE",
             "GREEN": N_("GREEN")},
}
COLOUR_NAMES = {"red": N_("RED"), "green": N_("GREEN"), "yellow": N_("YELLOW"), "blue": N_("BLUE")}
ASCII = {"◀": "<", "▶": ">", "▲": "^", "▼": "v"}
# per context: (actions shown together, label) in the order of the hint
HINTS = {
    "window": ((("live",), N_("live")), (("prev", "next"), N_("other camera")), (("ptz",), N_("camera control")),
               (("close",), N_("close"))),
    "ptz": ((("up", "down", "left", "right"), N_("move")), (("zoom_in", "zoom_out"), N_("zoom")),
            (("home",), N_("home position")), (("leave",), N_("end camera control"))),
    "tour": ((("prev", "next"), N_("other camera")), (("hold",), N_("pause")), (("live",), N_("live")),
             (("close",), N_("close"))),
    "mosaic": ((("close",), N_("close")),),
    "live": ((("prev", "next"), N_("other camera")), (("pause",), N_("pause")), (("ptz",), N_("camera control")),
             (("close",), N_("close"))),
}
SEPARATOR = "   "


def _keys_text(player, context, actions, tr, glyphs):
    names = []
    for action in actions:
        for key in KEYMAP[player][context].get(action, ()):
            name = KEY_NAMES[player].get(key)
            if name is None:
                continue
            name = tr(name) if name.isupper() and name.lower() in COLOUR_NAMES else name
            if not glyphs:
                name = ASCII.get(name, name)
            if name not in names:
                names.append(name)
    if len(actions) == 1:
        names = names[:2]  # 'MENU/INFO', not every alias
        return "/".join(names)
    return " ".join(names)


def key_hint(player, context, tr, ptz_key=None, has_ptz=False, glyphs=True):
    """The key hint of a screen: 'OK = live   ◀ ▶ = other camera   EXIT = close' (translated).
    ptz_key: the configured colour key ('blue', ... or 'off'): shown as a key that ends camera control (ptz) and,
    for a camera with PTZ (has_ptz), as the key that starts it (window, live). glyphs=False uses < > ^ v for fonts without ◀ ▶ ▲ ▼."""
    if not KEYMAP[player][context]:
        return ""  # e.g. Enigma2 live view: the camera is a normal channel, no CamAlert screen
    colour = tr(COLOUR_NAMES[ptz_key]) if ptz_key in COLOUR_NAMES else None
    parts = []
    for actions, label in HINTS[context]:
        keys = _keys_text(player, context, actions, tr, glyphs)
        if actions == ("ptz",):
            if not has_ptz:
                continue
            keys = "/".join(x for x in (colour, keys) if x)
        elif actions == ("leave",):
            keys = "/".join(x for x in (keys, colour) if x)
        if keys:
            parts.append("%s = %s" % (keys, tr(label)))
    return SEPARATOR.join(parts)


def tour_status(title, index, total, paused, tr):
    """'Front door   (2/5, tour)' / '(2/5, paused)' for the tour title bar."""
    return "%s   (%d/%d, %s)" % (title, index, total, tr(N_("paused")) if paused else tr(N_("tour")))
