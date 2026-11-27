"""camalert_core.mqtt: codec, commands, Home Assistant discovery."""
import json
import unittest

import _paths

_paths.core()
from camalert_core import keymap  # noqa: E402
from camalert_core.mqtt import codec as mqtt_codec  # noqa: E402
from camalert_core.mqtt import topics as mqtt_topics  # noqa: E402


class TestMqtt(unittest.TestCase):
    def test_mqtt_packets(self):
        c = mqtt_codec.mqtt_connect("dc1", "user", "pw", "camalert/x/availability")
        self.assertEqual(c[0], 0x10)
        self.assertIn(b"MQTT\x04", c)
        self.assertEqual(c[c.index(b"MQTT") + 5], 0x02 | 0x04 | 0x20 | 0x80 | 0x40)
        p = mqtt_codec.mqtt_publish("a/b", "x" * 200, retain=True)
        self.assertEqual(p[0], 0x31)
        self.assertEqual(p[1:3], bytes([0xCD, 0x01]))  # 205 = 0xCD 0x01 (variable length)
        pk, rest = mqtt_codec.mqtt_split(p + b"\x20\x02\x00" )
        self.assertEqual(len(pk), 1)
        self.assertEqual(rest, b"\x20\x02\x00")
        pk, rest = mqtt_codec.mqtt_split(rest + b"\x00")
        self.assertEqual((pk[0][0], rest), (2, b""))
        topic, payload = mqtt_codec.mqtt_parse_publish(0, mqtt_codec.mqtt_publish("camalert/x/show", "garden")[2:])
        self.assertEqual((topic, payload), ("camalert/x/show", b"garden"))
        self.assertEqual(mqtt_codec.mqtt_subscribe(1, ["a/#"]), b"\x82\x08\x00\x01\x00\x03a/#\x00")

    def test_mqtt_command(self):
        self.assertEqual(mqtt_topics.mqtt_command(b"garden"), {"cam": "garden"})
        self.assertEqual(mqtt_topics.mqtt_command(b'{"cam": "garden", "sec": 20, "x": 1}'), {"cam": "garden", "sec": 20})
        self.assertEqual(mqtt_topics.mqtt_command(b""), {})
        self.assertEqual(mqtt_topics.mqtt_command(b"{bad"), {})

    def test_discovery(self):
        msgs = dict(mqtt_topics.discovery("abc123", "CamAlert kitchen", [("front_door", "Front door")]))
        import json
        btn = json.loads(msgs["homeassistant/button/camalert_abc123/show_front_door/config"])
        self.assertEqual(btn["command_topic"], "camalert/abc123/show")
        self.assertEqual(btn["payload_press"], "front_door")
        self.assertEqual(btn["device"]["identifiers"], ["camalert_abc123"])
        self.assertIn("homeassistant/sensor/camalert_abc123/on_screen/config", msgs)

    def test_discovery_dnd(self):
        import json
        msgs = dict(mqtt_topics.discovery("abc", "X", []))
        sw = json.loads(msgs["homeassistant/switch/camalert_abc/dnd/config"])
        self.assertEqual(sw["command_topic"], "camalert/abc/dnd/set")
        self.assertEqual(sw["state_topic"], "camalert/abc/dnd")

    def test_buttons_discovery(self):
        msgs = dict(mqtt_topics.discovery("abc", "CamAlert test", [("garden", "Garden")]))
        conf = json.loads(msgs["homeassistant/event/camalert_abc/button/config"])
        self.assertEqual(conf["event_types"], ["red", "green", "yellow", "blue"])
        self.assertEqual(conf["state_topic"], "camalert/abc/button")
        self.assertEqual(json.loads(keymap.button_event("abc", "garden", "red")),
                         {"event_type": "red", "button": "red", "camera": "garden", "receiver": "abc"})


if __name__ == "__main__":
    unittest.main()


class TestDiscoveryCleaner(unittest.TestCase):
    """#116: retained discovery configs of cameras that are gone (renamed, removed, a helper stream) are removed with
    an empty retained payload; with discovery off every config of this player goes. Read back from the broker, so
    it also works after a reinstall (no state file)."""

    def setUp(self):
        from camalert_core.mqtt.topics import DiscoveryCleaner, discovery_filter
        self.filter = discovery_filter("node1")
        self.c = DiscoveryCleaner("node1")

    def cfg(self, oid, kind="button", node="node1"):
        return "homeassistant/%s/camalert_%s/%s/config" % (kind, node, oid)

    def test_filter(self):
        self.assertEqual(self.filter, "homeassistant/+/camalert_node1/+/config")

    def test_waits_for_the_camera_list(self):
        self.assertEqual(self.c.seen(self.cfg("show_old"), b"{}"), [])  # list not known yet: nothing removed
        self.assertEqual(self.c.seen(self.cfg("show_garden"), b"{}"), [])
        self.assertEqual(self.c.known(["garden", "front_door"]), [self.cfg("show_old")])
        self.assertEqual(self.c.seen(self.cfg("show_garden"), b"{}"), [])  # our own discovery comes back
        self.assertEqual(self.c.seen(self.cfg("show_front_door_jpeg"), b"{}"), [self.cfg("show_front_door_jpeg")])

    def test_keeps_the_fixed_entities_and_other_players(self):
        self.c.known(["garden"])
        for oid, kind in (("mosaic", "button"), ("hide", "button"), ("on_screen", "sensor"), ("dnd", "switch"),
                          ("button", "event")):
            self.assertEqual(self.c.seen(self.cfg(oid, kind), b"{}"), [], oid)
        self.assertEqual(self.c.seen(self.cfg("show_old", node="other"), b"{}"), [])
        self.assertEqual(self.c.seen("homeassistant/button/camalert_node1/show_old/config/x", b"{}"), [])
        self.assertEqual(self.c.seen("camalert/node1/show", b"garden"), [])

    def test_empty_payload_is_already_removed(self):
        self.c.known(["garden"])
        self.assertEqual(self.c.seen(self.cfg("show_old"), b""), [])

    def test_unknown_list_removes_nothing(self):
        """go2rtc not reachable: the camera list is unknown, never 'no cameras' (would remove every button)."""
        for i in range(600):
            self.c.seen(self.cfg("show_%d" % i), b"{}")
        self.assertLessEqual(len(self.c.pending), 500)

    def test_discovery_off_removes_everything_of_this_player(self):
        self.assertEqual(self.c.seen(self.cfg("show_garden"), b"{}"), [])
        self.assertEqual(self.c.disabled(), [self.cfg("show_garden")])
        self.assertEqual(self.c.seen(self.cfg("mosaic"), b"{}"), [self.cfg("mosaic")])
        self.assertEqual(self.c.seen(self.cfg("show_x", node="other"), b"{}"), [])

    def test_discovery_on_again(self):
        self.c.disabled()
        self.assertEqual(self.c.known(["garden"]), [])
        self.assertEqual(self.c.seen(self.cfg("mosaic"), b"{}"), [])
