# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Cameras: go2rtc or direct (camera file), snapshot download."""
import os
import ssl
import urllib.request

from . import kodiapi
from .klogic import live_url
from .camalert_core.cameras import display_name, live_stream_name, parse_camera_file, parse_titles, title_for
from .camalert_core.devices.client import load_devices
from .camalert_core.frames import ProtectSnapshots, snapshot_request, url_width
from .camalert_core.warm import WarmFeeds, visible_cameras
from .camalert_core.present import go2rtc_problem as _problem_text
from .camalert_core.urls import (go2rtc_state, normalize_server, overview_cameras, snapshot_url, split_credentials,
                                 stream_info_from_json, streams_from_json)


def camera_file():
    s = kodiapi.settings()
    return s["camera_file"] or os.path.join(kodiapi.profile_dir(), "cameras.conf")


def direct_cameras():
    try:
        with open(camera_file(), encoding="utf-8") as f:
            return parse_camera_file(f.read())
    except OSError:
        return []


def open_url(url, timeout=8, verify=True):
    """urlopen with user:password@ (basic and digest) and optional certificate check."""
    url, user, password = split_credentials(url)
    handlers = []
    if url.startswith("https://") and not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    if user is not None:
        mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, user, password)
        handlers += [urllib.request.HTTPBasicAuthHandler(mgr), urllib.request.HTTPDigestAuthHandler(mgr)]
    return urllib.request.build_opener(*handlers).open(url, timeout=timeout)


def go2rtc_problem(s):
    """#73: no default go2rtc address any more. In go2rtc mode without a (valid) address: the translated text that
    says so (service start notification, camera choice); None when the address is usable or in direct mode."""
    if s["source"] != "go2rtc":
        return None
    return _problem_text(go2rtc_state(s["server"]), kodiapi.core_tr())


def all_camera_names(s=None):
    s = s or kodiapi.settings()
    if s["source"] == "direct":
        return [c["name"] for c in direct_cameras()]
    srv = normalize_server(s["server"])
    if not srv:
        return []
    global COMPOSITES
    with open_url(srv + "/api/streams", 5, s["verify_ssl"]) as r:
        names, COMPOSITES = stream_info_from_json(r.read().decode("utf-8", "replace"))
    return visible_cameras(names, s.get("ready_cameras", ""))  # #113: helper streams are not cameras


COMPOSITES = set()  # composite streams (an own mosaic in go2rtc) of the last camera list (#125)


def overview_names(names):
    """Default cameras of a mosaic, tour, screensaver or camera list: all except composite streams (#125)."""
    return overview_cameras(names, COMPOSITES)


def camera_urls(name, s=None):
    """(live url, snapshot url or None, title) for a camera, None if unknown."""
    s = s or kodiapi.settings()
    if s["source"] == "direct":
        for cam in direct_cameras():
            if cam["name"] == name:
                return cam["rtsp"], cam["snapshot"], cam["title"]
        return None
    srv = normalize_server(s["server"])
    if not srv or not name:
        return None
    return (live_url(srv, live_stream_name(name, s["substreams"]), s["live_format"], s["rtsp_port"]), snapshot_url(srv, name),
            title_for(name, parse_titles(s["titles"])))


def download(url, path, verify=True, timeout=8):
    with open_url(url, timeout, verify) as r:
        data = r.read()
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


PROTECT = ProtectSnapshots()
_WARM_VERIFY = [True]
WARM = WarmFeeds(lambda url: open_url(url, 10, _WARM_VERIFY[0]))  # #111: ready cameras while Kodi is on


def warm_tick(screen_off):
    """#111, every second from the service loop: ready cameras get a warm MJPEG feed while CamAlert is on, the
    camera source is go2rtc and the screen is not off (Kodi's standby)."""
    get = kodiapi.addon_setting
    _WARM_VERIFY[0] = get("verify_ssl") != "false"
    on = get("enabled") != "false" and (get("source") or "go2rtc") == "go2rtc" and not screen_off
    WARM.update(get("server"), get("ready_cameras"), on)
_PROTECT_KEY = [None]


def protect_snapshots(s):
    """PROTECT with the UniFi Protect consoles of devices.conf (#109); configured again only when the file or the
    settings change, so a camera that failed stays with go2rtc for a while."""
    from .ptz import device_file
    path = device_file()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    key = (path, mtime, s.get("protect_snapshots", True), s.get("unifi_cameras", ""))
    if key != _PROTECT_KEY[0]:
        _PROTECT_KEY[0] = key
        PROTECT.configure(list(load_devices(path).values()) if mtime is not None else [], s.get("unifi_cameras", ""),
                          s.get("protect_snapshots", True))
    return PROTECT


def picture(name, url, path, verify=True, first=False, s=None):
    """One picture of a camera into path (in a Feeder thread), from the fastest source: the warm feed of a ready
    camera (#111), UniFi Protect for a Protect camera (#109), else go2rtc - the first picture of a window from
    go2rtc's cache (#110). Returns the source."""
    data = WARM.frame(name) if name else None  # #111
    source = "warm"
    if not data and name:
        data = protect_snapshots(s or kodiapi.settings())(name, url_width(url))
        source = "protect"
    if data:
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return source
    asked = snapshot_request(url, first)
    download(asked, path, verify)
    return "cache" if asked != url else "go2rtc"


def title(name, s=None):
    urls = camera_urls(name, s)
    return urls[2] if urls else display_name(name)
