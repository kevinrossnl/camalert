# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""CamAlert MQTT commands and Home Assistant discovery."""

import json
import threading


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


def discovery_filter(node, base="homeassistant"):
    """Subscription for this player's own retained discovery configs (#116)."""
    return "%s/+/camalert_%s/+/config" % (base, node)


class DiscoveryCleaner(object):
    """Removes this player's Home Assistant discovery configs that are no longer valid (#116).

    The player subscribes to discovery_filter() and hands every message to seen(); the broker sends the retained
    configs, so this also works after a reinstall (no state file). A config is stale when discovery is off (every
    config of this player) or when it is the button of a camera that is no longer in the camera list (renamed,
    removed, or a helper stream of 'Keep cameras ready', #113). The answer is the list of topics to clear with an
    empty retained payload. As long as the camera list is unknown (go2rtc not reachable) nothing is removed.
    """

    MAX_PENDING = 500

    def __init__(self, node, base="homeassistant"):
        self.node, self.base = node, base
        self.cameras = None  # set of names once known
        self.enabled = True
        self.pending = []
        self.lock = threading.Lock()

    def ours(self, topic):
        p = topic.split("/")
        return len(p) == 5 and p[0] == self.base and p[2] == "camalert_%s" % self.node and p[4] == "config"

    def _stale(self, topic):
        if not self.enabled:
            return True
        kind, oid = topic.split("/")[1], topic.split("/")[3]
        return kind == "button" and oid.startswith("show_") and oid[5:] not in self.cameras

    def seen(self, topic, payload):
        """One message on discovery_filter(): the topics to clear now."""
        if not payload or not self.ours(topic):
            return []
        with self.lock:
            if self.enabled and self.cameras is None:
                if topic not in self.pending and len(self.pending) < self.MAX_PENDING:
                    self.pending.append(topic)
                return []
            return [topic] if self._stale(topic) else []

    def _flush(self):
        out = [t for t in self.pending if self._stale(t)]
        self.pending = []
        return out

    def known(self, cameras):
        """The camera list is known (discovery on): the stale topics seen so far."""
        with self.lock:
            self.cameras, self.enabled = set(cameras), True
            return self._flush()

    def disabled(self):
        """Discovery is off: every config of this player seen so far (and later) is stale."""
        with self.lock:
            self.enabled = False
            return self._flush()
