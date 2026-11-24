# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Camera devices file (credentials stay in a local file, never in settings or logs)."""

from ..urls import valid_port


# Credentials live only in a local file on the receiver (DEVICES_FILE), never in the settings or in logs.
DEVICES_FILE = "/etc/enigma2/camalert_devices.conf"
DEVICE_TYPES = ("foscam", "onvif")
PTZ_ACTIONS = ("up", "down", "left", "right", "zoom_in", "zoom_out", "home", "stop")


def parse_devices(text):
    """Lines 'name|type|host:port|user|password' (# = comment) -> {name: {type, host, port, user, password}}.
    The password is the rest of the line, so it may contain '|'. Unknown types and broken lines are skipped."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 4)
        if len(parts) < 3:
            continue
        name, kind, addr = parts[0].strip(), parts[1].strip().lower(), parts[2].strip()
        if not name or kind not in DEVICE_TYPES or not addr:
            continue
        host, _sep, port = addr.rpartition(":") if addr.count(":") == 1 else (addr, "", "")
        default = 88 if kind == "foscam" else 80
        out[name] = {"type": kind, "host": host, "port": valid_port(port, default) if port else default,
                     "user": parts[3].strip() if len(parts) > 3 else "",
                     "password": parts[4] if len(parts) > 4 else ""}
    return out


def device_base(dev):
    return "http://%s:%d" % (dev["host"], dev["port"])


PTZ_VECTORS = {"up": (0, 0.5, 0), "down": (0, -0.5, 0), "left": (-0.5, 0, 0), "right": (0.5, 0, 0),
               "zoom_in": (0, 0, 0.5), "zoom_out": (0, 0, -0.5)}
