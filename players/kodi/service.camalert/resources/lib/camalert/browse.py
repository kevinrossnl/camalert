# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""The camera list of the video add-on (#107): items and plugin URLs, without Kodi imports (tested).

Labels are Kodi string ids (int) or plain text (camera titles, a problem); plugin.py translates the ids.
Item URLs only carry the action and the camera name: never an address, user, password or token."""
try:
    from urllib.parse import parse_qsl, urlencode, urlsplit
except ImportError:  # pragma: no cover - Python 2 is not supported, Kodi 19+ only
    raise

CAMERA_ACTIONS = ("live", "show")
ACTIONS = ("mosaic", "tour", "events", "settings") + CAMERA_ACTIONS
THUMB_SECONDS = 30  # thumbnails are refreshed at most every 30 s (Kodi caches images by URL)
_SECRET_WORDS = ("token", "pass", "pwd", "user", "secret", "auth", "key")


def url(base, action, cam=None):
    q = [("do", action)] + ([("cam", cam)] if cam is not None else [])
    return base + "?" + urlencode(q)


def parse(query):
    """{'do': action[, 'cam': name]} for a plugin query, None for the root list, {'do': 'unknown'} for anything
    else (an unknown action, or a camera action without a camera)."""
    q = dict(parse_qsl((query or "").lstrip("?")))
    if not q:
        return None
    action = q.get("do")
    if action not in ACTIONS or (action in CAMERA_ACTIONS and not q.get("cam")):
        return {"do": "unknown"}
    return {"do": action, "cam": q["cam"]} if action in CAMERA_ACTIONS else {"do": action}


def safe_thumb(snapshot, stamp):
    """The snapshot URL with a cache-busting parameter (changes every THUMB_SECONDS), or None when the URL is not
    plain http(s) or could carry a secret (user info, token or password in the query): those never go to Kodi."""
    if not snapshot:
        return None
    try:
        p = urlsplit(snapshot)
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or "@" in p.netloc:
        return None
    if any(w in k.lower() for k, _v in parse_qsl(p.query, keep_blank_values=True) for w in _SECRET_WORDS):
        return None
    t = int(stamp) // THUMB_SECONDS * THUMB_SECONDS
    return "%s%scamalert_t=%d" % (snapshot, "&" if p.query else "?", t)


def _item(kind, label, link, label2=None, thumb=None, camera=None, context=()):
    return {"kind": kind, "label": label, "label2": label2, "url": link, "folder": False, "thumb": thumb,
            "camera": camera, "context": list(context)}


def root_items(base, cameras, problem, stamp):
    """The root list: mosaic, tour, one item per camera (name, title, snapshot url or None), event list, settings.
    With a problem (no go2rtc address, go2rtc not reachable): that problem (opens the settings) and the settings."""
    if problem:
        return [_item("problem", problem, url(base, "settings")), _item("settings", 30284, url(base, "settings"))]
    items = [_item("mosaic", 30171, url(base, "mosaic")), _item("tour", 30172, url(base, "tour"))]
    for name, title, snapshot in cameras:
        items.append(_item("camera", title, url(base, "live", name), label2=30043, thumb=safe_thumb(snapshot, stamp),
                           camera=name, context=[(30291, url(base, "show", name))]))
    items += [_item("events", 30204, url(base, "events")), _item("settings", 30284, url(base, "settings"))]
    return items
