"""camalert_core.triggers: the registry (#6), Frigate and Foscam."""
import json
import unittest

import _paths

_paths.core()
import json  # noqa: E402

from camalert_core import triggers  # noqa: E402
from camalert_core.triggers import foscam, frigate  # noqa: E402

EVENT = json.dumps({"type": "new", "after": {"camera": "garden_cam", "label": "person", "id": "1.5-x",
                                         "sub_label": ["Anna", 0.9], "has_snapshot": True}})
from camalert_core.mqtt import topics as mqtt_topics  # noqa: E402


class TestTriggers(unittest.TestCase):
    def test_frigate(self):
        new = '{"type": "new", "before": {}, "after": {"id": "1700000000.1-abc", "camera": "front_door", "label": "person", "has_snapshot": true, "false_positive": false}}'
        ev = frigate.frigate_event(new.encode())
        self.assertEqual((ev["type"], ev["camera"], ev["label"], ev["snapshot"]), ("new", "front_door", "person", True))
        self.assertIsNone(frigate.frigate_event('{"type": "end", "after": {"camera": "x", "label": "person"}}'))
        self.assertIsNone(frigate.frigate_event('{"type": "update", "after": {"camera": "x", "label": "car", "false_positive": true}}'))
        self.assertIsNone(frigate.frigate_event(b"not json"))
        self.assertEqual(frigate.frigate_stream(ev, "person, car"), "front_door")
        self.assertIsNone(frigate.frigate_stream(ev, "car"))
        self.assertEqual(frigate.frigate_stream(ev, "", "front_door=door_cam|x=y"), "door_cam")
        self.assertIsNone(frigate.frigate_stream(None))

    def test_frigate_labels_and_clips(self):
        ev = frigate.frigate_event(json.dumps({"type": "new", "after": {"id": "1732.5-abc", "camera": "garden",
                                                                   "label": "person", "sub_label": ["Alice", 0.92],
                                                                   "has_clip": True}}))
        self.assertEqual(ev["sub_label"], "Alice")
        self.assertEqual(frigate.frigate_title(ev), "Alice")
        ev["sub_label"] = ""
        self.assertEqual(frigate.frigate_title(ev), "Person")
        self.assertEqual(frigate.frigate_clip_url("192.168.1.10:5000", "1732.5-abc"),
                         "http://192.168.1.10:5000/api/events/1732.5-abc/clip.mp4")
        self.assertIsNone(frigate.frigate_clip_url("http://f:5000", "../x"))
        self.assertIsNone(frigate.frigate_clip_url("", "1"))
        self.assertEqual(mqtt_topics.mqtt_command(b'{"cam": "a", "label": "Person"}')["label"], "Person")

    def test_registry(self):
        self.assertEqual(sorted(triggers.REGISTRY), ["foscam", "frigate"])
        self.assertEqual(triggers.enabled_sources({}), [])
        on = triggers.enabled_sources({"frigate_enabled": True, "foscam_enabled": True})
        self.assertEqual([s.name for s in on], ["foscam", "frigate"])
        self.assertEqual([s.name for s in triggers.enabled_sources({"frigate_enabled": True, "foscam_enabled": True},
                                                                    "poll")], ["foscam"])
        self.assertEqual(triggers.mqtt_topics(on), ["frigate/events"])

    def test_register_a_new_source(self):
        @triggers.register
        class Doorbell(triggers.TriggerSource):
            name, transport = "test_doorbell", "mqtt"

            def topics(self):
                return ["bell/ring"]

            def parse(self, topic, payload, now=0.0):
                return triggers.Trigger(payload.decode(), "high", "test")
        try:
            srcs = triggers.enabled_sources({"test_doorbell_enabled": True}, "mqtt")
            self.assertEqual(triggers.dispatch(srcs, "bell/ring", b"front_door"),
                             (True, triggers.Trigger("front_door", "high", "test")))
            self.assertEqual(triggers.dispatch(srcs, "other/topic", b"x"), (False, None))
        finally:
            del triggers.REGISTRY["test_doorbell"]

    def test_frigate_source(self):
        src = frigate.FrigateSource({"frigate_enabled": True, "frigate_prefix": "frigate2/", "frigate_labels": "person",
                                     "frigate_map": "garden_cam=garden", "frigate_priority": "high"})
        self.assertEqual(src.topics(), ["frigate2/events"])
        trig = src.parse("frigate2/events", EVENT)
        self.assertEqual(trig.show_args(), ("garden", None, None, "high", "frigate", "Anna", "1.5-x"))
        self.assertIsNone(src.parse("frigate2/events", EVENT.replace("person", "car")))
        self.assertIsNone(src.parse("frigate2/events", b"not json"))
        self.assertEqual(frigate.frigate_topic(""), "frigate/events")
        self.assertIn("Trigger(", repr(trig))

    def test_frigate_mode_seconds_and_debounce(self):
        src = frigate.FrigateSource({"frigate_enabled": True, "frigate_mode": "live", "frigate_seconds": 20,
                                     "frigate_debounce": 5})
        self.assertEqual(src.parse("frigate/events", EVENT, now=100).show_args()[:3], ("garden_cam", 20, "live"))
        self.assertIsNone(src.parse("frigate/events", EVENT, now=103))
        self.assertIsNotNone(src.parse("frigate/events", EVENT, now=106))

    def test_foscam_source(self):
        src = foscam.FoscamSource({"foscam_enabled": True, "foscam_priority": "high", "foscam_label": "Motion"})
        devs = {"a": {"type": "foscam"}, "b": {"type": "onvif"}}
        self.assertEqual(list(src.devices(devs)), ["a"])
        self.assertEqual(src.check("a", False, True).show_args(), ("a", None, None, "high", "foscam", "Motion", None))
        self.assertIsNone(src.check("a", True, True))   # alarm still running
        self.assertIsNone(src.check("a", None, False))
        self.assertFalse(foscam.FoscamSource({}).enabled())


if __name__ == "__main__":
    unittest.main()
