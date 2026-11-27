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
from .camalert_core.present import go2rtc_problem
from .camalert_core.urls import go2rtc_state, valid_port


def caller_text(at, source):
    """(time with the date in Kodi's region format, translated source) of the last API caller (#41)."""
    from .camalert_core.present import event_time, source_label
    return event_time(at, kodiapi.language(), fmt=kodiapi.date_format()), source_label(source, kodiapi.core_tr())


def unifi_lines(status):
    """Diagnostics lines from the service's UniFi Protect poll status (a dict, see service.unifi_state)."""
    from .camalert_core.present import event_time
    from .camalert_core.triggers.unifi import PollStatus
    st = PollStatus()
    st.__dict__.update(status or {})
    when = lambda ts: event_time(ts, kodiapi.language(), fmt=kodiapi.date_format())  # noqa: E731
    return [diag_line(ok, text) for ok, text in st.lines(kodiapi.core_tr(), when)]


def collect(state):
    s = kodiapi.settings()
    tr = kodiapi.tr
    lines = [diag_line(True, "CamAlert %s, Kodi %s, Python %s, %s" % (
        __version__, xbmc.getInfoLabel("System.BuildVersion").split(" ")[0], platform.python_version(),
        kodiapi.os_version()))]
    names = []
    if s["source"] == "go2rtc":
        problem = go2rtc_problem(go2rtc_state(s["server"]), kodiapi.core_tr())
        t = time.time()
        if problem:  # not set or invalid: say so, contact nothing (#73)
            lines.append(diag_line(False, problem))
        else:
            try:
                names = sources.all_camera_names(s)
                lines.append(diag_line(True, tr(30210) % (len(names), (time.time() - t) * 1000)))
            except Exception as e:
                lines.append(diag_line(False, tr(30211) % redact(e)))
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
        when, who = caller_text(at, source)
        lines.append(diag_line(True, tr(30220) % (when, host, who)))
    else:
        lines.append(diag_line(None, tr(30221)))
    devs = ptz.all_devices(s)
    if devs:
        lines.append(diag_line(True, tr(30222) % ", ".join("%s (%s)" % (n, d["type"]) for n, d in sorted(devs.items()))))
    if s["unifi_enabled"]:  # UniFi Protect source (#71): last check, last event, last error (redacted)
        lines.extend(unifi_lines(state.get("unifi")))
    from .camalert_core.warm import lines_from_state  # #111: ready cameras and their last picture
    for ok, text in lines_from_state(state.get("warm"), kodiapi.core_tr()):
        lines.append(diag_line(ok, text))
    if s["dnd"]:
        lines.append(diag_line(None, tr(30223)))
    lines.append(diag_line(bool(state.get("log")) or s["log_level"] == "off", tr(30224) % (state.get("log") or "-")))
    return lines
