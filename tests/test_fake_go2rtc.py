"""tests/fakes/go2rtc.py: neutral demo cameras for screenshots and tests (#32, #47)."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

import _paths  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fakes"))
import go2rtc  # noqa: E402

_paths.tools()
import check_images  # noqa: E402

_paths.core()
from camalert_core import urls  # noqa: E402


class TestFakeGo2rtc(unittest.TestCase):
    def setUp(self):
        self.srv = go2rtc.FakeGo2rtc(unreachable=["driveway"]).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def get(self, path):
        return urllib.request.urlopen(self.srv.url + path, timeout=5)

    def test_streams_and_frames(self):
        names = urls.streams_from_json(self.get("/api/streams").read().decode())
        self.assertEqual(names, ["back_door", "driveway", "front_door", "garden"])
        r = self.get(urls.snapshot_url(self.srv.url, "garden", 320)[len(self.srv.url):])
        data = r.read()
        self.assertIn(r.headers["Content-Type"], ("image/jpeg", "image/png"))
        self.assertEqual(check_images.metadata(data), [])  # no EXIF, no text

    def test_unreachable_and_unknown(self):
        for path in ("/api/frame.jpeg?src=driveway", "/api/frame.jpeg?src=nope", "/api/stream.mp4?src=garden"):
            with self.assertRaises(urllib.error.HTTPError, msg=path):
                self.get(path)

    def test_png_without_pillow(self):
        data = go2rtc.png_frame(64, 36, (0, 92, 140))
        self.assertEqual(check_images.metadata(data), [])
        self.assertEqual(json.loads(json.dumps(sorted(go2rtc.CAMERAS))), ["back_door", "driveway", "front_door", "garden"])


if __name__ == "__main__":
    unittest.main()
