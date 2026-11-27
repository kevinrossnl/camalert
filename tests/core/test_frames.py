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


class FakeClock(object):
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


UNIFI = {"type": "unifi", "host": "192.168.1.1", "port": 443, "user": "viewer", "password": "pw"}
FOSCAM = {"type": "foscam", "host": "192.168.1.30", "port": 88}


class TestProtectSnapshots(unittest.TestCase):
    """#109: Protect pictures for Protect cameras, go2rtc for everything else and after an error."""

    def make(self, answers):
        calls = []

        def fetch(dev, camera, names, width):
            calls.append((dev["host"], camera, dict(names), width))
            a = answers.get(camera)
            if isinstance(a, Exception):
                raise a
            return a
        clock = FakeClock()
        p = frames.ProtectSnapshots(fetch, clock)
        p.configure([FOSCAM, UNIFI], "Garten=garden", True)
        return p, calls, clock

    def test_only_unifi_consoles_and_mapped_names(self):
        p, calls, _clock = self.make({"front_door": b"jpg"})
        self.assertTrue(p.active())
        self.assertEqual(p("front_door", 320), b"jpg")
        self.assertEqual(calls, [("192.168.1.1", "front_door", {"garten": "garden"}, 320)])

    def test_off_without_console_or_when_turned_off(self):
        p, calls, _clock = self.make({"front_door": b"jpg"})
        p.configure([FOSCAM], "", True)
        self.assertFalse(p.active())
        self.assertIsNone(p("front_door"))
        p.configure([UNIFI], "", False)
        self.assertIsNone(p("front_door"))
        self.assertIsNone(p(None))
        self.assertEqual(calls, [])

    def test_unknown_camera_and_errors_are_skipped_for_a_while(self):
        p, calls, clock = self.make({"garden": OSError("console down"), "driveway": None})
        self.assertIsNone(p("garden"))
        self.assertIsNone(p("garden"))  # not asked again right away
        self.assertIsNone(p("driveway"))
        self.assertIsNone(p("driveway"))
        self.assertEqual([c[1] for c in calls], ["garden", "driveway"])
        clock.now += frames.PROTECT_ERROR_SKIP + 1
        p("garden")
        p("driveway")  # an unknown camera waits longer
        self.assertEqual([c[1] for c in calls], ["garden", "driveway", "garden"])
        clock.now += frames.PROTECT_UNKNOWN_SKIP
        p("driveway")
        self.assertEqual([c[1] for c in calls][-1], "driveway")

    def test_default_fetch_is_the_client(self):
        p = frames.ProtectSnapshots()
        p.configure([UNIFI], "", True)
        from camalert_core.devices import client
        orig = client.protect_snapshot
        client.protect_snapshot = lambda dev, cam, names, width: b"x"
        try:
            self.assertEqual(p("front_door"), b"x")
        finally:
            client.protect_snapshot = orig


class TestSnapshots(unittest.TestCase):
    def test_protect_first_then_go2rtc_with_cache(self):
        asked = []
        protect = {"front_door": b"protect"}
        s = frames.Snapshots(lambda url: asked.append(url) or b"go2rtc", lambda cam, w: protect.get(cam))
        self.assertEqual(s.fetch("front_door", URL, True), (b"protect", "protect"))
        self.assertEqual(s.fetch("garden", URL.replace("front_door", "garden"), True), (b"go2rtc", "cache"))
        self.assertEqual(s.fetch("garden", URL.replace("front_door", "garden"), False), (b"go2rtc", "go2rtc"))
        self.assertEqual(asked, [URL.replace("front_door", "garden") + "&cache=10s", URL.replace("front_door", "garden")])
        self.assertEqual(s.last_source, {"front_door": "protect", "garden": "go2rtc"})

    def test_without_protect_and_without_camera(self):
        s = frames.Snapshots(lambda url: b"x")
        self.assertEqual(s.fetch(None, URL), (b"x", "go2rtc"))
        self.assertEqual(s.last_source, {})

    def test_url_width(self):
        self.assertEqual(frames.url_width(URL), 640)
        self.assertEqual(frames.url_width("http://h/api/frame.jpeg?src=a&width=1280&cache=10s"), 1280)
        self.assertEqual(frames.url_width("http://192.168.1.20/snap.jpg"), 640)
        self.assertEqual(frames.url_width(None, 320), 320)


class TestTileLabel(unittest.TestCase):
    def test_loading_and_unreachable(self):
        tr = lambda s: "<%s>" % s  # noqa: E731
        self.assertEqual(present.tile_label("loading", tr), "<Loading picture...>")
        self.assertEqual(present.tile_label("unreachable", tr), "<Camera not reachable>")
        self.assertEqual(present.tile_label(None, tr), "")
        self.assertEqual(present.tile_label("other", tr), "")


if __name__ == "__main__":
    unittest.main()
