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

CACHE_SECONDS = 10  # first picture of a window may be this old; the next refresh replaces it


def with_cache(url, seconds=CACHE_SECONDS):
    """A go2rtc frame.jpeg URL with cache=<n>s for the first picture of a window (#110). Other URLs (direct
    snapshot URLs of cameras) and a URL that already has a cache parameter are returned unchanged."""
    if not url or seconds <= 0 or "/api/frame.jpeg" not in url or re.search(r"[?&]cache=", url):
        return url
    return "%s%scache=%ds" % (url, "&" if "?" in url else "?", int(seconds))


def snapshot_request(url, first):
    """The URL to ask for a snapshot: with cache for the first picture of a window, else unchanged."""
    return with_cache(url) if first else url
