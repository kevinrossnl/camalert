# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""CamAlert MQTT commands and Home Assistant discovery."""

import json


def mqtt_command(payload):
    """Payload of a show command: 'front_door' or JSON {"cam": ..., "sec": ..., "mode": ...}."""
    text = payload.decode("utf-8", "replace").strip() if isinstance(payload, bytes) else str(payload).strip()
    if text.startswith("{"):
        try:
            d = json.loads(text)
        except ValueError:
            return {}
        return {k: d[k] for k in ("cam", "sec", "mode", "priority", "label") if k in d}
    return {"cam": text} if text else {}


def discovery(node, name, cameras, prefix="camalert", base="homeassistant"):
    """Home Assistant MQTT discovery messages: [(topic, json payload)]. cameras: [(name, title)]."""
    avail = "%s/%s/availability" % (prefix, node)
    device = {"identifiers": ["camalert_%s" % node], "name": name, "manufacturer": "CamAlert", "model": "Enigma2 receiver"}
    msgs = []

    def add(kind, oid, conf):
        conf.update({"unique_id": "camalert_%s_%s" % (node, oid), "object_id": "camalert_%s_%s" % (node, oid),
                     "availability_topic": avail, "device": device})
        msgs.append(("%s/%s/camalert_%s/%s/config" % (base, kind, node, oid), json.dumps(conf, sort_keys=True)))

    for cam, title in cameras:
        add("button", "show_" + cam, {"name": "Show %s" % title, "icon": "mdi:cctv",
                                      "command_topic": "%s/%s/show" % (prefix, node), "payload_press": cam})
    add("button", "mosaic", {"name": "Mosaic", "icon": "mdi:view-grid", "command_topic": "%s/%s/mosaic" % (prefix, node),
                             "payload_press": ""})
    add("button", "hide", {"name": "Hide camera", "icon": "mdi:close-box", "command_topic": "%s/%s/hide" % (prefix, node),
                           "payload_press": ""})
    add("sensor", "on_screen", {"name": "Camera on screen", "icon": "mdi:television",
                                "state_topic": "%s/%s/state" % (prefix, node)})
    add("switch", "dnd", {"name": "Do not disturb", "icon": "mdi:bell-off",
                          "command_topic": "%s/%s/dnd/set" % (prefix, node), "state_topic": "%s/%s/dnd" % (prefix, node),
                          "payload_on": "ON", "payload_off": "OFF"})
    add("event", "button", {"name": "Remote button", "icon": "mdi:remote", "state_topic": "%s/%s/button" % (prefix, node),
                            "event_types": ["red", "green", "yellow", "blue"]})
    return msgs
