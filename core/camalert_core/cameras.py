# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Camera names, titles and per-camera settings (orientation, refresh interval, substreams)."""

import re


def slug(name):
    """'Front Door' -> 'front_door' (also handles umlauts)."""
    n = (name or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("è", "e"), ("à", "a")):
        n = n.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")


def display_name(stream):
    """'front_door' -> 'Front door'."""
    s = (stream or "").replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:]


def parse_camera_file(text):
    """Direct mode (no go2rtc). One camera per line:  name | rtsp-url | snapshot-url (optional).  # = comment."""
    cams = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[1].startswith(("rtsp://", "rtsps://", "rtspt://", "http://", "https://")):
            continue
        name = slug(parts[0])
        if not name or any(c["name"] == name for c in cams):
            continue
        snap = parts[2] if len(parts) > 2 and parts[2].startswith(("http://", "https://")) else None
        cams.append({"name": name, "title": parts[0], "rtsp": parts[1], "snapshot": snap})
    return cams


def parse_cams(value):
    """'front_door, garden' -> ['front_door', 'garden'] (max 9, duplicates removed)."""
    out = []
    for c in re.split(r"[,\s]+", value or ""):
        if re.match(r"^[A-Za-z0-9_.-]+$", c) and c not in out:
            out.append(c)
    return out[:9]


def neighbour(items, current, step):
    """Next/previous item in a list (wraps around); first item if current is unknown."""
    if not items:
        return None
    if current not in items:
        return items[0]
    return items[(items.index(current) + step) % len(items)]


def known_camera(name, names):
    """False only if we know the camera list and the name is not in it (an empty list = unknown, allow)."""
    return bool(name) and (not names or name in names)


def parse_titles(text):
    """'front_door=Front door|garden=Garden' -> {'front_door': 'Front door', 'garden': 'Garden'}."""
    out = {}
    for part in (text or "").split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if re.match(r"^[A-Za-z0-9_.-]+$", k) and v:
                out[k] = v
    return out


def format_titles(titles):
    """Inverse of parse_titles; empty names are dropped, '|' and newlines are removed from names."""
    items = []
    for k in sorted(titles):
        v = re.sub(r"[|\r\n]", " ", titles[k] or "").strip()
        if v:
            items.append("%s=%s" % (k, v))
    return "|".join(items)


def title_for(name, titles):
    return (titles or {}).get(name) or display_name(name)


ORIENTATIONS = ("mirror", "flip", "rot180")


def parse_map(text):
    """'cam=value|cam2=value2' -> {'cam': 'value', ...} (generic form of parse_titles)."""
    return parse_titles(text)


def format_map(values):
    return format_titles(values)


def parse_orientation(text):
    """'garden=rot180|drive=mirror' -> {'garden': 'rot180', 'drive': 'mirror'}; unknown values are dropped."""
    return {k: v.lower() for k, v in parse_map(text).items() if v.lower() in ORIENTATIONS}


def parse_refresh(text):
    """'garden=5|drive=2.5' -> seconds between snapshots per camera (0.5..300); invalid values are dropped."""
    out = {}
    for k, v in parse_map(text).items():
        try:
            f = float(v.replace(",", "."))
        except ValueError:
            continue
        if f > 0:
            out[k] = max(0.5, min(300.0, f))
    return out


def refresh_delay(name, refresh, minimum=0.2):
    """Pause before the next snapshot of a camera: its own interval, or as fast as possible."""
    return max(minimum, (refresh or {}).get(name, 0))


def live_stream_name(name, substreams=""):
    """go2rtc stream used for live view: 'front_door=front_door_sub|...' lets a box that cannot decode the main
    stream (H.265 / 4K) use a substream; default the camera itself."""
    return parse_map(substreams).get(name) or name
