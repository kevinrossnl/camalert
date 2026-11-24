# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Diagnostics: what works and what does not, as lines for a text dialog (same checks as the Enigma2 screen)."""
import platform
import socket
import time

import xbmc

from . import __version__, kodiapi, ptz, sources
from .camalert_core.events import diag_line
from .camalert_core.obs.log import redact
from .camalert_core.urls import normalize_server, valid_port


def collect(state):
    s = kodiapi.settings()
    tr = kodiapi.tr
    lines = [diag_line(True, "CamAlert %s, Kodi %s, Python %s, %s" % (
        __version__, xbmc.getInfoLabel("System.BuildVersion").split(" ")[0], platform.python_version(),
        xbmc.getInfoLabel("System.OSVersionInfo") or platform.system()))]
    names = []
    if s["source"] == "go2rtc":
        t = time.time()
        try:
            names = sources.all_camera_names(s)
            lines.append(diag_line(True, tr(30210) % (len(names), (time.time() - t) * 1000)))
        except Exception as e:
            lines.append(diag_line(False, tr(30211) % redact(e)))
        if not normalize_server(s["server"]):
            lines.append(diag_line(False, tr(30212)))
    else:
        try:
            names = sources.all_camera_names(s)
        except Exception:
            names = []
    for n in names[:12]:
        urls = sources.camera_urls(n, s)
        if not urls or not urls[1]:
            lines.append(diag_line(None, tr(30213) % n))
            continue
        t = time.time()
        try:
            with sources.open_url(urls[1].replace("width=640", "width=160"), 8, s["verify_ssl"]) as r:
                size = len(r.read())
            lines.append(diag_line(size > 1000, tr(30214) % (n, (time.time() - t) * 1000)))
        except Exception as e:
            lines.append(diag_line(False, tr(30215) % (n, type(e).__name__)))
    port = valid_port(s["http_port"], 8099)
    try:
        socket.create_connection(("127.0.0.1", port), 2).close()
        lines.append(diag_line(True, tr(30216) % port))
    except OSError:
        lines.append(diag_line(False, tr(30217) % port))
    if state is None:
        lines.append(diag_line(False, tr(30202)))
        state = {}
    if s["mqtt_enabled"]:
        lines.append(diag_line(bool(state.get("mqtt")), tr(30218) if state.get("mqtt") else tr(30219)))
    caller = state.get("last_caller")
    if caller:
        at, host, source = caller
        lines.append(diag_line(True, tr(30220) % (time.strftime("%d-%m %H:%M", time.localtime(at)), host,
                                                    "Home Assistant" if source == "ha" else source)))
    else:
        lines.append(diag_line(None, tr(30221)))
    devs = ptz.all_devices(s)
    if devs:
        lines.append(diag_line(True, tr(30222) % ", ".join("%s (%s)" % (n, d["type"]) for n, d in sorted(devs.items()))))
    if s["dnd"]:
        lines.append(diag_line(None, tr(30223)))
    lines.append(diag_line(bool(state.get("log")) or s["log_level"] == "off", tr(30224) % (state.get("log") or "-")))
    return lines
