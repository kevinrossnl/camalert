"""camalert_core.frames: where the pictures of a window come from (#110 cache for the first picture)."""
import unittest

import _paths

_paths.core()
from camalert_core import frames, present  # noqa: E402

URL = "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640"


class TestCache(unittest.TestCase):
    def test_first_picture_asks_for_a_cached_frame(self):
        self.assertEqual(frames.with_cache(URL), URL + "&cache=10s")
        self.assertEqual(frames.snapshot_request(URL, True), URL + "&cache=10s")
        self.assertEqual(frames.with_cache(URL, 3), URL + "&cache=3s")

    def test_later_pictures_and_other_urls_unchanged(self):
        self.assertEqual(frames.snapshot_request(URL, False), URL)
        direct = "http://192.168.1.20/snap.jpg"  # direct mode: the camera's own snapshot URL
        self.assertEqual(frames.with_cache(direct), direct)
        self.assertEqual(frames.with_cache(URL + "&cache=1m"), URL + "&cache=1m")
        self.assertEqual(frames.with_cache(URL, 0), URL)
        self.assertIsNone(frames.with_cache(None))
        self.assertEqual(frames.with_cache("http://h:1984/api/frame.jpeg"), "http://h:1984/api/frame.jpeg?cache=10s")


class TestTileLabel(unittest.TestCase):
    def test_loading_and_unreachable(self):
        tr = lambda s: "<%s>" % s  # noqa: E731
        self.assertEqual(present.tile_label("loading", tr), "<Loading picture...>")
        self.assertEqual(present.tile_label("unreachable", tr), "<Camera not reachable>")
        self.assertEqual(present.tile_label(None, tr), "")
        self.assertEqual(present.tile_label("other", tr), "")


if __name__ == "__main__":
    unittest.main()
