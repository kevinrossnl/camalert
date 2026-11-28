# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Enigma2 service references, channel lists (bouquets), the chime command and the opkg update source."""

import re
from urllib.parse import unquote

from .camalert_core.cameras import display_name
from .camalert_core.urls import rtsp_url, tcp_url


SERVICE_TYPE = 4097  # GStreamer media player
BOUQUET_FILE = "userbouquet.camalert.tv"


def service_ref(url, name, number=1):
    """Enigma2 service reference for a stream URL (':' must be encoded as %3a)."""
    return "%d:0:1:DC%02X:0:0:0:0:0:0:%s:%s" % (SERVICE_TYPE, number % 256, url.replace(":", "%3a"), name.replace(":", " "))


def url_from_ref(ref):
    parts = (ref or "").split(":")
    if len(parts) < 12:
        return None
    return unquote(":".join(parts[10:-1]))


def stream_from_ref(ref, cameras=None):
    """Camera name from a service reference, or None. `cameras` (direct mode): list from parse_camera_file."""
    url = url_from_ref(ref)
    if not url:
        return None
    if cameras:
        for cam in cameras:
            if tcp_url(cam["rtsp"]) == url or cam["rtsp"] == url:
                return cam["name"]
        return None
    m = re.match(r"^rtspt?://[^/]+/([A-Za-z0-9_.-]+)$", url)
    return m.group(1) if m else None


def bouquet_text(title, server, streams, port=8554, cameras=None, titles=None, resolve=None):
    """Channel list. go2rtc mode: `streams` names via `server` (names from `titles`), or via `resolve(name)` ->
    (server, stream) with several go2rtc servers (#15); direct mode: `cameras`."""
    lines = ["#NAME %s" % title]
    where = resolve or (lambda s: (server, s))
    entries = [(c["title"], tcp_url(c["rtsp"])) for c in cameras] if cameras else \
        [((titles or {}).get(s) or display_name(s), rtsp_url(*(where(s) + (port,)))) for s in streams]
    for i, (name, url) in enumerate(entries, 1):
        lines.append("#SERVICE " + service_ref(url, name, i))
        lines.append("#DESCRIPTION " + name)
    return "\n".join(lines) + "\n"


def add_to_bouquets(bouquets_tv, filename=BOUQUET_FILE):
    """Returns bouquets.tv text with our bouquet appended (unchanged if already present)."""
    if filename in bouquets_tv:
        return bouquets_tv
    line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % filename
    text = bouquets_tv if bouquets_tv.endswith("\n") or not bouquets_tv else bouquets_tv + "\n"
    return text + line + "\n"


def is_media_ref(ref):
    """True for a service reference that plays a file (recording, video on the NAS), not a TV channel or stream."""
    parts = (ref or "").split(":")
    if len(parts) < 11:
        return False
    return ":".join(parts[10:]).startswith("/")


def place_in_bouquets(bouquets_tv, filename=BOUQUET_FILE, position="bottom"):
    """bouquets.tv with our bouquet at the top (first bouquet) or bottom; every other line is kept as it is.
    position "keep": leave it where the user put it; only add it (at the bottom) when it is missing."""
    line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % filename
    if position == "keep" and ('"%s"' % filename) in bouquets_tv:
        return bouquets_tv if bouquets_tv.endswith("\n") else bouquets_tv + "\n"
    lines = [l for l in bouquets_tv.splitlines() if ('"%s"' % filename) not in l]
    if position == "top":
        at = 1 if lines and lines[0].startswith("#NAME") else 0
        lines.insert(at, line)
    else:
        lines.append(line)
    return "\n".join(lines) + "\n"


def github_repo(control_text):
    """'owner/camalert' from the Homepage line of the installed package's opkg control file."""
    m = re.search(r"^Homepage:\s*https://github\.com/([\w.-]+/[\w.-]+?)/?\s*$", control_text or "", re.M)
    return m.group(1) if m else None


def chime_command(path, sink="alsasink"):
    """gstreamer command for the doorbell chime; ALSA plays next to the TV sound (dvbaudiosink) on Vu+ boxes."""
    return ["gst-launch-1.0", "-q", "filesrc", "location=%s" % path, "!", "wavparse", "!", "audioconvert", "!",
            "audioresample", "!", sink]
