# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Event list, caller sources and the lines of the diagnostics and event screens."""

from .obs.log import redact


EVENT_LIMIT = 20
SOURCES = ("api", "ha", "mqtt", "frigate", "foscam", "menu")


def add_event(events, event, limit=EVENT_LIMIT):
    """Newest first, at most `limit`; returns the events that fell off (their snapshots can be removed)."""
    events.insert(0, event)
    dropped = events[limit:]
    del events[limit:]
    return dropped


def caller_source(user_agent, path=""):
    """Who called the API: 'ha' for Home Assistant (integration / rest_command use aiohttp), else 'api'."""
    ua = (user_agent or "").lower()
    return "ha" if "homeassistant" in ua or "home assistant" in ua or "aiohttp" in ua else "api"


def event_title(title, label=None):
    """'Person at Front door' style title (label translated by the caller)."""
    return "%s · %s" % (label, title) if label else title


def diag_line(ok, text):
    """One line of the diagnostics screen: ok True / False / None (= note)."""
    return "%s  %s" % ({True: "[ OK ]", False: "[FAIL]", None: "[ -- ]"}[ok], redact(text))


def event_line(e):
    """English line with raw codes (old screens); new screens use present.event_line(e, tr) (#41)."""
    import time as _t
    who = (" · " + e["label"]) if e.get("label") else ""
    return "%s  %s%s  (%s, %s) -> %s" % (_t.strftime("%H:%M:%S", _t.localtime(e["time"])), e["camera"], who,
                                          e["source"], e["priority"], e["action"])
