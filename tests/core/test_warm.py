"""Keep cameras ready (#111): MJPEG parser, setting, and the warm feeds against the fake go2rtc (real HTTP)."""
import time
import unittest
import urllib.request

import _paths

_paths.core()
from camalert_core import frames, warm  # noqa: E402
from fakes.go2rtc import FakeGo2rtc  # noqa: E402


def part(data, length=True):
    head = b"--frame\r\nContent-Type: image/jpeg\r\n"
    if length:
        head += b"Content-Length: %d\r\n" % len(data)
    return head + b"\r\n" + data + b"\r\n"


def wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


class TestParse(unittest.TestCase):
    def test_parse_ready(self):
        self.assertEqual(warm.parse_ready(""), {})
        self.assertEqual(warm.parse_ready(None), {})
        self.assertEqual(warm.parse_ready("front_door=front_door_jpeg| garden ,=x|back_door="),
                         {"front_door": "front_door_jpeg", "garden": "garden"})

    def test_mjpeg_url(self):
        self.assertEqual(warm.mjpeg_url("192.168.1.10:1984", "front door"),
                         "http://192.168.1.10:1984/api/stream.mjpeg?src=front%20door")
        self.assertIsNone(warm.mjpeg_url("", "x"))
        self.assertIsNone(warm.mjpeg_url("192.168.1.10", ""))

    def test_parser_in_chunks_and_without_length(self):
        stream = part(b"\xff\xd8one\xff\xd9") + part(b"\xff\xd8two\xff\xd9", length=False) + part(b"three")
        p = warm.MjpegParser()
        got = []
        for i in range(0, len(stream), 7):
            got += p.feed(stream[i:i + 7])
        self.assertEqual(got, [b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9", b"three"])

    def test_parser_refuses_garbage(self):
        with self.assertRaises(ValueError):
            warm.MjpegParser().feed(b"--frame\r\nContent-Length: x\r\n\r\n")
        with self.assertRaises(ValueError):
            warm.MjpegParser().feed(b"--frame\r\nContent-Length: %d\r\n\r\n" % (warm.MAX_FRAME + 1))
        p = warm.MjpegParser()
        p.buf = b"x" * (warm.MAX_FRAME + 1)
        with self.assertRaises(ValueError):
            p.feed(b"")


class TestWarmFeeds(unittest.TestCase):
    def setUp(self):
        self.go = FakeGo2rtc(unreachable=["driveway"], mjpeg_fps=20).start()
        self.addCleanup(self.go.stop)
        self.feeds = warm.WarmFeeds(lambda url: urllib.request.urlopen(url, timeout=5), chunk=4096)
        self.addCleanup(self.feeds.stop)

    def test_empty_setting_opens_nothing(self):
        self.feeds.update(self.go.url, "", True)
        time.sleep(0.3)
        self.assertEqual(self.go.mjpeg_opened, 0)
        self.assertIsNone(self.feeds.frame("front_door"))
        self.assertEqual(self.feeds.lines(lambda t: t), [])

    def test_ready_only_while_active(self):
        self.feeds.update(self.go.url, "front_door", False)  # player in standby: no connection
        time.sleep(0.3)
        self.assertEqual(self.go.mjpeg_opened, 0)
        self.assertEqual(self.feeds.lines(lambda t: t), [(None, "Ready: front_door (not while the player is off)")])
        t0 = time.time()
        self.feeds.update(self.go.url, "front_door", True)  # standby left
        self.assertTrue(wait(lambda: self.feeds.frame("front_door") is not None, 1.0), "no picture within 1 s")
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual(self.go.mjpeg_clients, 1)
        ok, text = self.feeds.lines(lambda t: t)[0]
        self.assertTrue(ok and text.startswith("Ready: front_door (last picture"))
        self.assertEqual(self.feeds.state()["active"], True)
        self.feeds.update(self.go.url, "front_door", True)  # nothing changed: no new connection
        self.assertEqual(self.go.mjpeg_opened, 1)
        self.feeds.update(self.go.url, "front_door", False)  # standby again: connection closed
        self.assertTrue(wait(lambda: self.go.mjpeg_clients == 0, 2.0))
        self.assertIsNone(self.feeds.frame("front_door"))
        self.assertTrue(wait(lambda: not self.feeds.running, 2.0))

    def test_other_stream_name_and_unreachable(self):
        self.feeds.update(self.go.url, "door=front_door|driveway", True)
        self.assertTrue(wait(lambda: self.feeds.frame("door") is not None, 2.0))
        self.assertIsNone(self.feeds.frame("driveway"))
        self.assertTrue(wait(lambda: any(t == "Ready: driveway not connected (HTTPError)"
                                         for _ok, t in self.feeds.lines(lambda t: t)), 2.0))

    def test_stale_picture_is_not_used(self):
        now = [1000.0]
        f = warm.WarmFeeds(lambda url: None, clock=lambda: now[0], start=lambda fn: None)
        f.update("192.168.1.10", "front_door", True)
        f.frames["front_door"] = (b"pic", 1000.0)
        self.assertEqual(f.frame("front_door"), b"pic")
        now[0] += warm.STALE_SECONDS + 0.1
        self.assertIsNone(f.frame("front_door"))
        self.assertFalse(f.lines(lambda t: t)[0][0])

    def test_reconnects_after_an_error(self):
        opened = []

        class Dead(object):
            def read(self, n):
                return b""

            def close(self):
                pass

        sleeps = []
        f = warm.WarmFeeds(lambda url: opened.append(url) or Dead(), sleep=sleeps.append, start=lambda fn: None)
        f.update("192.168.1.10", "front_door", True)
        clock = [0.0]
        f.clock = lambda: clock[0]

        def sleep(s):
            clock[0] += s
            if len(opened) >= 3:
                f.active = False
        f.sleep = sleep
        f._run("front_door", "u", f.gen)
        self.assertEqual(len(opened), 3)
        self.assertEqual(f.errors, {"front_door": "OSError"})
        self.assertFalse(f.running)

    def test_lines_from_state(self):
        tr = lambda t: t  # noqa: E731
        self.assertEqual(warm.lines_from_state(None, tr), [])
        st = {"active": True, "cameras": {"a": 1.2, "b": None, "c": 99}}
        self.assertEqual([ok for ok, _t in warm.lines_from_state(st, tr)], [True, False, False])
        self.assertEqual(warm.lines_from_state({"active": False, "cameras": {"a": 1}}, tr)[0][0], None)


class TestSnapshotsOrder(unittest.TestCase):
    def test_warm_first_then_protect_then_go2rtc(self):
        class W(object):
            pic = b"warm"

            def frame(self, camera):
                return self.pic if camera == "front_door" else None
        calls = []
        snaps = frames.Snapshots(lambda url: calls.append(url) or b"go2rtc", protect=lambda c, w: b"protect" if c == "garden" else None,
                                 warm=W())
        self.assertEqual(snaps.fetch("front_door", "http://g/api/frame.jpeg?src=front_door&width=640", True), (b"warm", "warm"))
        self.assertEqual(snaps.fetch("garden", "http://g/api/frame.jpeg?src=garden&width=640", True), (b"protect", "protect"))
        self.assertEqual(snaps.fetch("back_door", "http://g/api/frame.jpeg?src=back_door&width=640", True)[1], "cache")
        W.pic = None
        self.assertEqual(snaps.fetch("front_door", "http://g/api/frame.jpeg?src=front_door&width=640", False)[1], "go2rtc")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
