# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Where the pictures of the photo window, the multi-camera window, the mosaic and the tour come from.

go2rtc's /api/frame.jpeg waits for the next keyframe of the camera and transcodes it: 2-5 s with cameras that send
a keyframe every few seconds (measured on go2rtc 1.9.15, #110). The first request of a window therefore asks for
a cached picture (``cache=<n>s``, go2rtc 1.9.14+; older versions ignore the parameter): a camera that was shown
in the last few seconds appears at once. Later refreshes ask for a new picture.
"""
import re
import time

from .devices import unifi

CACHE_SECONDS = 10  # first picture of a window may be this old; the next refresh replaces it
PROTECT_ERROR_SKIP = 60  # s: after a Protect error the camera's pictures come from go2rtc for a while (#109)
PROTECT_UNKNOWN_SKIP = 600  # s: a camera that is not a Protect camera is not asked again for this long


def with_cache(url, seconds=CACHE_SECONDS):
    """A go2rtc frame.jpeg URL with cache=<n>s for the first picture of a window (#110). Other URLs (direct
    snapshot URLs of cameras) and a URL that already has a cache parameter are returned unchanged."""
    if not url or seconds <= 0 or "/api/frame.jpeg" not in url or re.search(r"[?&]cache=", url):
        return url
    return "%s%scache=%ds" % (url, "&" if "?" in url else "?", int(seconds))


def snapshot_request(url, first):
    """The URL to ask for a snapshot: with cache for the first picture of a window, else unchanged."""
    return with_cache(url) if first else url


def url_width(url, default=640):
    """The width parameter of a snapshot URL (frame.jpeg?...&width=640), else the default."""
    m = re.search(r"[?&]width=(\d+)", url or "")
    return int(m.group(1)) if m else default


class ProtectSnapshots(object):
    """Pictures of UniFi Protect cameras through the read-only Protect session (#109): Protect hands out a fresh
    picture at once, without waiting for a keyframe like go2rtc's frame.jpeg. Only for consoles in the devices file
    (type unifi) and cameras that Protect knows (names mapped by unifi_cameras). After an error the camera is left
    to go2rtc for PROTECT_ERROR_SKIP seconds, so a console that is down never slows the window down twice."""

    def __init__(self, fetch=None, clock=time.time):
        self.fetch = fetch  # (device, camera, names, width) -> bytes or None; default: devices.client
        self.clock = clock
        self.consoles, self.names, self.enabled = [], {}, True
        self.skip = {}  # camera -> time until which Protect is not asked

    def configure(self, devices, names_text="", enabled=True):
        """devices: parsed devices file entries; only those of type unifi are used."""
        self.consoles = [d for d in devices or [] if d.get("type") == "unifi"]
        self.names = unifi.camera_map(names_text)
        self.enabled = bool(enabled)
        self.skip = {}

    def active(self):
        return self.enabled and bool(self.consoles)

    def __call__(self, camera, width=640):
        """JPEG bytes of the camera, or None (not a Protect camera, Protect off, an error: use go2rtc)."""
        now = self.clock()
        if not camera or not self.active() or self.skip.get(camera, 0) > now:
            return None
        fetch = self.fetch
        if fetch is None:
            from .devices.client import protect_snapshot as fetch
        for dev in self.consoles:
            try:
                data = fetch(dev, camera, self.names, width)
            except Exception:  # login refused, console down, rate limited: go2rtc for a while
                self.skip[camera] = now + PROTECT_ERROR_SKIP
                return None
            if data:
                return data
        self.skip[camera] = now + PROTECT_UNKNOWN_SKIP
        return None


class Snapshots(object):
    """One picture of a camera for a window, from the fastest source that has one (#109, #110): UniFi Protect
    (fresh, no keyframe wait), else go2rtc frame.jpeg (cached for the first picture of a window).
    download(url) -> bytes is the player's own HTTP fetch (certificate setting, user:password@)."""

    def __init__(self, download, protect=None):
        self.download = download
        self.protect = protect
        self.last_source = {}  # camera -> 'protect' / 'cache' / 'go2rtc' (diagnostics, tests)

    def fetch(self, camera, url, first=False):
        """(JPEG bytes, source). Raises what download() raises when go2rtc fails too."""
        data, source = None, None
        if camera and self.protect is not None:
            data = self.protect(camera, url_width(url))
            source = "protect" if data else None
        if data is None:
            asked = snapshot_request(url, first)
            data = self.download(asked)
            source = "cache" if asked != url else "go2rtc"
        if camera:
            self.last_source[camera] = source
        return data, source
