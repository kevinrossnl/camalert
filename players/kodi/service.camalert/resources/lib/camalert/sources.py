# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Cameras: go2rtc or direct (camera file), snapshot download."""
import os
import ssl
import urllib.request

from . import kodiapi
from .klogic import live_url
from .camalert_core.cameras import display_name, live_stream_name, parse_camera_file, parse_titles, title_for
from .camalert_core.present import go2rtc_problem as _problem_text
from .camalert_core.urls import go2rtc_state, normalize_server, snapshot_url, split_credentials, streams_from_json


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
    with open_url(srv + "/api/streams", 5, s["verify_ssl"]) as r:
        return streams_from_json(r.read().decode("utf-8", "replace"))


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


def title(name, s=None):
    urls = camera_urls(name, s)
    return urls[2] if urls else display_name(name)
