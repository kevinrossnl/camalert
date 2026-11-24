# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Frigate detections (MQTT events) and clip URLs."""

import json
import re

from ..cameras import parse_map


def frigate_event(payload):
    """Parses a message from <prefix>/events. Returns {'type', 'camera', 'label', 'id', 'snapshot'} for a new or
    updated detection, None for anything else (end events, false positives, broken JSON)."""
    try:
        d = json.loads(payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("type") not in ("new", "update"):
        return None
    after = d.get("after") or {}
    if not isinstance(after, dict) or after.get("false_positive") or not after.get("camera"):
        return None
    sub = after.get("sub_label")
    if isinstance(sub, (list, tuple)):  # Frigate 0.13+: [name, score]
        sub = sub[0] if sub else None
    return {"type": d["type"], "camera": str(after["camera"]), "label": str(after.get("label") or ""),
            "sub_label": str(sub or ""), "id": str(after.get("id") or ""), "snapshot": bool(after.get("has_snapshot")),
            "clip": bool(after.get("has_clip"))}


def frigate_title(event):
    """Who/what for the window title: the sub label (a recognised face or plate) if any, else the label."""
    if not event:
        return None
    return event.get("sub_label") or (event.get("label") or "").replace("_", " ").capitalize() or None


def frigate_stream(event, labels="", camera_map=""):
    """Stream to show for a Frigate event, or None. labels: 'person,car' (empty = all);
    camera_map: 'frigate_name=go2rtc_name|...' (default: same name)."""
    if not event:
        return None
    wanted = [x.strip().lower() for x in (labels or "").split(",") if x.strip()]
    if wanted and event["label"].lower() not in wanted:
        return None
    stream = parse_map(camera_map).get(event["camera"], event["camera"])
    return stream if re.match(r"^[A-Za-z0-9_.-]+$", stream) else None


def frigate_clip_url(frigate_url, event_id):
    """Frigate API url of an event clip, or None."""
    base = (frigate_url or "").strip().rstrip("/")
    if not base or not event_id or not re.match(r"^[\w.-]+$", event_id):
        return None
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    return "%s/api/events/%s/clip.mp4" % (base, event_id)
