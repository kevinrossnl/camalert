# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""UniFi Protect (#9): pure helpers for the read-only Protect API (no network here, see client.py).

Only GET requests after the login: bootstrap (camera list), events and snapshots. A local Protect user with the
role "View Only" is enough; its login lives in the devices file like every other camera password.
"""
import re

LOGIN_PATH = "/api/auth/login"
BOOTSTRAP_PATH = "/proxy/protect/api/bootstrap"
# what CamAlert can react to: the Protect event types and the kinds they stand for
EVENT_TYPES = ("ring", "motion", "smartDetectZone", "smartDetectLine")
KINDS = ("ring", "person", "vehicle", "animal", "package", "motion")
DEFAULT_KINDS = "ring,person"
PRIORITIES = ("normal", "high", "alarm")
MODES = ("photo", "live", "notify", "log")  # log = only the event list and the log (nothing on screen, no chime)
SECONDS = (5, 300)  # range of a duration in a per-camera rule (same as the setting unifi_seconds)
_FOLD = {u"ä": "ae", u"ö": "oe", u"ü": "ue", u"ß": "ss", u"é": "e", u"è": "e", u"à": "a", u"ç": "c"}


def slug(name):
    """A Protect display name as a go2rtc-style camera name: 'Front Door' -> 'front_door', 'Hügel' -> 'huegel'."""
    s = (name or "").strip().lower()
    s = "".join(_FOLD.get(ch, ch) for ch in s)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def protect_cameras(bootstrap):
    """{Protect camera id: camera name} from a bootstrap answer (adopted cameras only)."""
    out = {}
    for cam in (bootstrap or {}).get("cameras") or []:
        if not isinstance(cam, dict) or not cam.get("id") or cam.get("isAdopted") is False:
            continue
        name = slug(cam.get("displayName") or cam.get("name") or "")
        if name:
            out[cam["id"]] = name
    return out


def camera_map(text):
    """'protect_name=go2rtc_name|...' (same format as the Frigate map) -> dict; broken parts are skipped."""
    out = {}
    for part in (text or "").split("|"):
        k, sep, v = part.partition("=")
        if sep and slug(k) and v.strip():
            out[slug(k)] = v.strip()
    return out


def wanted_kinds(text):
    """'ring, person' -> ['ring', 'person'] in KINDS order; unknown words are ignored, empty = DEFAULT_KINDS."""
    words = set(w.strip().lower() for w in (text or DEFAULT_KINDS).split(",") if w.strip())
    return [k for k in KINDS if k in words] or wanted_kinds(DEFAULT_KINDS)


def kind_rules(text):
    """Per event type (#70): 'ring=alarm/live|motion=normal/log/garden' -> {kind: (priority, mode, camera)},
    each part None when empty or invalid (= the general setting). Unknown kinds and broken parts are skipped."""
    out = {}
    for part in (text or "").split("|"):
        k, sep, v = part.partition("=")
        k = k.strip().lower()
        if not sep or k not in KINDS:
            continue
        fields = [f.strip() for f in v.split("/")] + ["", "", ""]
        prio, mode, cam = fields[0].lower(), fields[1].lower(), fields[2]
        rule = (prio if prio in PRIORITIES else None, mode if mode in MODES else None, cam or None)
        if rule != (None, None, None):
            out[k] = rule
    return out


def camera_rules(text):
    """Per camera: 'front_door=high/photo/30|garage=normal/log' -> {camera: (priority, mode, seconds)}. The camera
    is the CamAlert camera name (after unifi_cameras), compared as slug(); seconds 5-300. Each part is None when
    empty or invalid (= the per-type rule or the general setting). Broken parts are skipped."""
    out = {}
    for part in (text or "").split("|"):
        k, sep, v = part.partition("=")
        k = slug(k)
        if not sep or not k:
            continue
        fields = [f.strip() for f in v.split("/")] + ["", "", ""]
        prio, mode, secs = fields[0].lower(), fields[1].lower(), fields[2]
        try:
            secs = int(secs)
        except ValueError:
            secs = None
        rule = (prio if prio in PRIORITIES else None, mode if mode in MODES else None,
                secs if secs is not None and SECONDS[0] <= secs <= SECONDS[1] else None)
        if rule != (None, None, None):
            out[k] = rule
    return out


def event_kinds(ev):
    """What a Protect event is about: ['ring'], ['person', 'vehicle'], ['motion'] or []."""
    t = (ev or {}).get("type")
    if t == "ring":
        return ["ring"]
    if t == "motion":
        return ["motion"]
    if t in ("smartDetectZone", "smartDetectLine"):
        return [k for k in KINDS if k in (ev.get("smartDetectTypes") or [])]
    return []


def events_path(start_ms, end_ms, limit=50):
    """GET path for the events between two times (ms), oldest first."""
    q = "&".join("types=%s" % t for t in EVENT_TYPES)
    return "/proxy/protect/api/events?start=%d&end=%d&limit=%d&orderDirection=ASC&%s" % (
        int(start_ms), int(end_ms), int(limit), q)


def snapshot_path(camera_id, width=1280):
    if not re.match(r"^[0-9a-fA-F]{6,64}$", camera_id or ""):
        raise ValueError("bad camera id")
    return "/proxy/protect/api/cameras/%s/snapshot?w=%d&force=true" % (camera_id, int(width))


def match(ev, cams, kinds, names=None):
    """(camera name, kind) if the event is one of `kinds` on a known camera, else None. `names` maps Protect names
    to go2rtc names (camera_map); cameras not in it keep their Protect name."""
    cam = cams.get((ev or {}).get("camera"))
    if not cam:
        return None
    for k in event_kinds(ev):
        if k in kinds:
            return (names or {}).get(cam, cam), k
    return None
