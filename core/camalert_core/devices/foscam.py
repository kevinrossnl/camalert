# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Foscam CGI: alarm state and PTZ commands."""

import re
from urllib.parse import quote

from .config import device_base


def foscam_url(dev, cmd, **params):
    """CGI url of a Foscam camera (HD models: cgi-bin/CGIProxy.fcgi)."""
    q = [("cmd", cmd)] + sorted(params.items()) + [("usr", dev.get("user", "")), ("pwd", dev.get("password", ""))]
    return "%s/cgi-bin/CGIProxy.fcgi?%s" % (device_base(dev), "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in q))


def foscam_values(xml):
    """<CGI_Result><result>0</result><motionDetectAlarm>2</motionDetectAlarm>...</CGI_Result> -> {tag: text}."""
    return dict(re.findall(r"<(\w+)>([^<]*)</\1>", xml or ""))


def foscam_alarm(xml):
    """True if a getDevState answer reports an active motion or sound alarm (value 2; 0 = off, 1 = no alarm)."""
    v = foscam_values(xml)
    if v.get("result", "0") != "0":
        return False
    return any(v.get(k) == "2" for k in ("motionDetectAlarm", "soundAlarm", "humanDetectAlarmState"))


def alarm_edge(previous, now):
    """Show the camera only when an alarm starts, not on every poll while it lasts."""
    return bool(now) and not previous


FOSCAM_PTZ = {"up": "ptzMoveUp", "down": "ptzMoveDown", "left": "ptzMoveLeft", "right": "ptzMoveRight",
              "zoom_in": "zoomIn", "zoom_out": "zoomOut", "home": "ptzReset"}


def foscam_ptz(action):
    """(start command, stop command or None) for a PTZ action on a Foscam camera."""
    if action in ("zoom_in", "zoom_out"):
        return FOSCAM_PTZ[action], "zoomStop"
    if action == "home":
        return "ptzReset", None
    if action == "stop":
        return "ptzStopRun", None
    return FOSCAM_PTZ[action], "ptzStopRun"
