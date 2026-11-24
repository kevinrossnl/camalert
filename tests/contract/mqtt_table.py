"""The MQTT contract (#31): topics, direction, retain flag and payload of both players.

{node} is the player's id (MAC address). Home Assistant discovery must be the same on every player apart from
PLATFORM_FIELDS.
"""
import json

NODE = "node1"
PLATFORM_FIELDS = (("device", "model"),)  # documented per-platform values in the discovery payload


def _json_keys(*keys):
    def check(payload):
        d = json.loads(payload)
        return all(k in d for k in keys)
    check.__name__ = "json with %s" % ", ".join(keys)
    return check


def _one_of(*values):
    def check(payload):
        return payload.decode() in values
    check.__name__ = "one of %s" % ", ".join(values)
    return check


# published by the player: topic template, retain, payload check
PUBLISHED = [
    ("camalert/{node}/availability", True, _one_of("online", "offline")),
    ("camalert/{node}/state", True, lambda p: len(p) > 0),
    ("camalert/{node}/dnd", True, _one_of("ON", "OFF")),
    ("camalert/{node}/button", False, _json_keys("event_type", "button", "camera", "receiver")),
    ("homeassistant/+/camalert_{node}/+/config", True, _json_keys("unique_id", "object_id", "availability_topic",
                                                                  "device", "name")),
]
# the player subscribes to (Frigate only when enabled)
SUBSCRIBED = ["camalert/{node}/show", "camalert/{node}/mosaic", "camalert/{node}/hide", "camalert/{node}/dnd/set",
              "frigate/events"]
LAST_WILL = ("camalert/{node}/availability", b"offline", True)

FRIGATE_EVENT = json.dumps({"type": "new", "after": {"camera": "garden", "label": "person", "id": "1.5-abc",
                                                     "has_snapshot": True, "false_positive": False}})
# commands: (name, topic, payload, expected controller call)
COMMANDS = [
    ("show_name", "camalert/{node}/show", "garden", ("show", "garden", None, None, None, "mqtt", None)),
    ("show_json", "camalert/{node}/show",
     json.dumps({"cam": "garden", "sec": 20, "mode": "live", "priority": "alarm", "label": "Person"}),
     ("show", "garden", 20, "live", "alarm", "mqtt", "Person")),
    ("mosaic_cameras", "camalert/{node}/mosaic", "a,b", ("mosaic", "a,b", 60)),
    ("mosaic_all", "camalert/{node}/mosaic", "", ("mosaic", None, 60)),
    ("hide", "camalert/{node}/hide", "", ("hide",)),
    ("dnd_on", "camalert/{node}/dnd/set", "ON", ("dnd", True)),
    ("dnd_off", "camalert/{node}/dnd/set", "OFF", ("dnd", False)),
    ("frigate_person", "frigate/events", FRIGATE_EVENT, ("show", "garden", 30, "photo", "normal", "frigate", "Person")),  # frigate_seconds/_mode (#39)
]


def topic(template, node=NODE):
    return template.format(node=node)
