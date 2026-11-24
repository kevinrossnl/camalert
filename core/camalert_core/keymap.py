# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Colour keys (to Home Assistant or PTZ toggle) and the button event payload."""

import json


COLOR_KEYS = {398: "red", 399: "green", 400: "yellow", 401: "blue"}
PTZ_TOGGLE_KEYS = ("blue", "yellow", "red", "green", "off")


def button_for(code, ptz_toggle="blue", has_ptz=False, enabled=True):
    """('ptz' | colour name | None) for a key while a camera is on screen. The PTZ toggle key only counts as PTZ
    for cameras that have PTZ; for all other cameras every colour key goes to Home Assistant."""
    colour = COLOR_KEYS.get(code)
    if colour is None:
        return None
    if has_ptz and colour == ptz_toggle:
        return "ptz"
    return colour if enabled else None


def button_event(node, camera, button):
    """Payload for camalert/<id>/button (MQTT event entity) and the Home Assistant webhook."""
    return json.dumps({"event_type": button, "button": button, "camera": camera or "", "receiver": node},
                      sort_keys=True)
