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


class TestLiveStill(unittest.TestCase):
    """#91: a still picture at once while the live stream opens, gone at its first frame."""

    def setUp(self):
        self.now = [100.0]
        self.still = frames.LiveStill(clock=lambda: self.now[0])

    def test_picture_before_first_frame_is_shown_then_hidden(self):
        t = self.still.start("front_door")
        self.assertTrue(self.still.picture(t))
        self.assertTrue(self.still.showing)
        self.assertTrue(self.still.playing(t))
        self.assertFalse(self.still.showing)
        self.assertFalse(self.still.playing(t))  # hidden once

    def test_picture_after_first_frame_is_not_shown(self):
        t = self.still.start("front_door")
        self.assertFalse(self.still.playing(t))  # nothing shown yet
        self.assertFalse(self.still.picture(t))  # stream was faster: never cover it

    def test_picture_of_an_earlier_camera_is_ignored(self):
        old = self.still.start("front_door")
        new = self.still.start("garden")  # LEFT/RIGHT or a new alert
        self.assertFalse(self.still.picture(old))
        self.assertFalse(self.still.playing(old))
        self.assertTrue(self.still.picture(new))

    def test_still_never_stays_longer_than_the_maximum(self):
        t = self.still.start("front_door")
        self.assertTrue(self.still.picture(t))
        self.now[0] += frames.STILL_MAX_SECONDS - 1
        self.assertFalse(self.still.expired())
        self.now[0] += 2
        self.assertTrue(self.still.expired())
        self.assertFalse(self.still.expired())
        t = self.still.start("garden")
        self.now[0] += frames.STILL_MAX_SECONDS + 1
        self.assertFalse(self.still.picture(t))  # too late to be useful

    def test_stop_hides_and_drops_late_pictures(self):
        t = self.still.start("front_door")
        self.assertTrue(self.still.picture(t))
        self.assertTrue(self.still.stop())
        self.assertFalse(self.still.picture(t))
        self.assertFalse(self.still.stop())

    def test_still_picture_uses_the_fast_sources_in_order(self):
        class Warm(object):
            def __init__(self, data):
                self.data = data

            def frame(self, camera):
                return self.data

        asked = []

        def download(url):
            asked.append(url)
            return b"go2rtc"

        url = "http://go2rtc:1984/api/frame.jpeg?src=front_door&width=640"
        snaps = frames.Snapshots(download, protect=lambda cam, w: None, warm=Warm(b"warm"))
        self.assertEqual(frames.still_picture(snaps, "front_door", url), (b"warm", "warm"))
        snaps = frames.Snapshots(download, protect=lambda cam, w: b"protect", warm=Warm(None))
        self.assertEqual(frames.still_picture(snaps, "front_door", url), (b"protect", "protect"))
        snaps = frames.Snapshots(download, protect=lambda cam, w: None, warm=Warm(None))
        self.assertEqual(frames.still_picture(snaps, "front_door", url), (b"go2rtc", "cache"))
        self.assertIn("cache=", asked[-1])
        self.assertEqual(frames.still_picture(snaps, "front_door", None), (None, None))

        def broken(url):
            raise IOError("down")
        self.assertEqual(frames.still_picture(frames.Snapshots(broken), "front_door", url), (None, None))
