"""camalert_core.cameras: names, titles, per-camera settings."""
import unittest

import _paths

_paths.core()
from camalert_core import cameras  # noqa: E402


class TestCameras(unittest.TestCase):
    def test_slug_and_names(self):
        self.assertEqual(cameras.slug("Zürich Süd Straße"), "zuerich_sued_strasse")
        self.assertEqual(cameras.display_name("front_door"), "Front door")

    def test_known_camera(self):
        self.assertTrue(cameras.known_camera("a", []))
        self.assertTrue(cameras.known_camera("a", ["a", "b"]))
        self.assertFalse(cameras.known_camera("x", ["a", "b"]))
        self.assertFalse(cameras.known_camera("", ["a"]))

    def test_neighbour(self):
        self.assertEqual(cameras.neighbour(["a", "b", "c"], "c", 1), "a")
        self.assertEqual(cameras.neighbour(["a", "b", "c"], "a", -1), "c")
        self.assertEqual(cameras.neighbour(["a", "b"], "x", 1), "a")
        self.assertIsNone(cameras.neighbour([], "a", 1))

    def test_orientation_refresh(self):
        self.assertEqual(cameras.parse_orientation("garden=rot180|drive=Mirror|x=spin"), {"garden": "rot180", "drive": "mirror"})
        r = cameras.parse_refresh("garden=5|drive=0,2|x=abc|y=999|z=0")
        self.assertEqual(r, {"garden": 5.0, "drive": 0.5, "y": 300.0})
        self.assertEqual(cameras.refresh_delay("garden", r), 5.0)
        self.assertEqual(cameras.refresh_delay("other", r), 0.2)

    def test_substreams(self):
        self.assertEqual(cameras.live_stream_name("front_door", "front_door=front_door_sub"), "front_door_sub")
        self.assertEqual(cameras.live_stream_name("garden", "front_door=front_door_sub"), "garden")

    def test_camera_file(self):
        cred = "admin:" + "pw@"
        text = """# comment
Front door | rtsp://CRED192.168.1.20:554/stream2 | http://CRED192.168.1.20/cgi-bin/snap.cgi
Garden|rtsp://192.168.1.21/live
broken line
Garden | rtsp://192.168.1.22/dup
""".replace("CRED", cred)
        cams = cameras.parse_camera_file(text)
        self.assertEqual([c["name"] for c in cams], ["front_door", "garden"])
        self.assertIsNone(cams[1]["snapshot"])

    def test_titles(self):
        t = cameras.parse_titles("front_door=Front door | garden=Back garden|bad name=x|empty=|novalue")
        self.assertEqual(t, {"front_door": "Front door", "garden": "Back garden"})
        self.assertEqual(cameras.format_titles({"garden": "Back | garden", "a": "", "front_door": "Front door"}),
                         "front_door=Front door|garden=Back   garden")
        self.assertEqual(cameras.parse_titles(cameras.format_titles(t)), t)
        self.assertEqual(cameras.title_for("garden", t), "Back garden")
        self.assertEqual(cameras.title_for("side_gate", t), "Side gate")
        self.assertEqual(cameras.parse_cams("a, b,,a c"), ["a", "b", "c"])
        self.assertEqual(cameras.format_map({"x": "1"}), "x=1")


if __name__ == "__main__":
    unittest.main()
