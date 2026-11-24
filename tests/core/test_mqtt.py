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
