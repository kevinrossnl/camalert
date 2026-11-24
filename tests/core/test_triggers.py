"""camalert_core.triggers: Frigate."""
import json
import unittest

import _paths

_paths.core()
from camalert_core.triggers import frigate  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
