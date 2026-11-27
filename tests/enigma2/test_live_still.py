"""#91: live view shows a still picture at once (warm feed, Protect, go2rtc cache, frame.jpeg) until the stream
shows video; the picture is fetched in a thread, never on the GUI thread. On Enigma2 the stream starts only after
the picture is on screen, or after STILL_WAIT_SECONDS: opening a stream holds the box for about 2.5 s, so a picture
fetched alongside it arrived only when the stream was already there (measured on a Solo 4K, Protect ~1 s idle)."""
import os
import time
import types
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake

ERR = types.SimpleNamespace(getErrorMessage=lambda: "timed out")


class TestLiveStill(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openpli")
        self.d = self.env.camalert.display
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.env.config.plugins.camalert.server.value = "http://192.168.1.10:1984"
        self.env.camalert.plugin.sessionstart(0, session=self.session)
        self.ctl = self.d.Controller.instance
        self.ctl._names, self.ctl._names_at = ["front_door", "garden"], time.time()
        self.ev = __import__("enigma").iPlayableService
        with open(self.d.STILL, "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")  # what _download would have written

    def tearDown(self):
        e2fake.uninstall()
        if os.path.exists(self.d.STILL):
            os.remove(self.d.STILL)

    def stills(self):
        """The still-picture downloads started by the controller, removed from the fake reactor."""
        out = [d for d in self.env.reactor.deferred
               if getattr(d.fn, "__name__", "") == "_download" and d.args[1] == self.d.STILL]
        for d in out:
            self.env.reactor.deferred.remove(d)
        return out

    def stills_open(self):
        return [s for s in self.session.dialogs if isinstance(s, self.d.LiveStillScreen)
                and s not in self.session.closed and getattr(s, "shown", True)]

    def live(self, cam="front_door"):
        self.assertEqual(self.ctl.show(cam, 30, "live", "high"), "show")

    def playing(self):
        ref = self.session.current_ref
        return ref.toString() if ref is not None else None

    def play_now(self):
        """The play timer fires: after the still is up (a moment to draw it) or at STILL_WAIT_SECONDS."""
        self.ctl.play_timer.callback[0]()

    def test_still_until_the_first_frame(self):
        self.assertIn(self.ctl.service_event, self.session.nav.event)
        self.live()
        d, = self.stills()  # fetched in a thread: the live view starts at once
        self.assertEqual(d.args[0], "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640")
        self.assertIs(d.args[3], True)  # first picture: warm / Protect / go2rtc cache (Snapshots order)
        self.assertIsNone(self.ctl.still_screen)
        self.assertIsNone(self.playing())  # the stream waits for the picture
        self.ctl.service_event(self.ev.evVideoSizeChanged)  # the TV channel, not the camera: ignored
        d.fire(self.d.STILL)
        self.assertIsNotNone(self.ctl.still_screen)
        self.assertTrue(self.ctl.play_timer.active)
        self.assertLess(self.ctl.play_timer.interval, 500)  # just long enough to draw the picture
        self.play_now()
        self.assertIn("front_door", self.playing())
        self.ctl.service_event(self.ev.evStart)  # not video yet
        self.assertIsNotNone(self.ctl.still_screen)
        self.ctl.service_event(self.ev.evVideoSizeChanged)
        self.assertIsNone(self.ctl.still_screen)

    def test_stream_faster_than_the_picture(self):
        self.live()
        d, = self.stills()
        self.assertEqual(self.ctl.play_timer.interval, int(self.d.STILL_WAIT_SECONDS * 1000))
        self.play_now()  # no picture within STILL_WAIT_SECONDS: start the stream anyway
        self.assertIn("front_door", self.playing())
        self.ctl.service_event(self.ev.evVideoSizeChanged)
        d.fire(self.d.STILL)
        self.assertIsNone(self.ctl.still_screen)  # never cover a running stream

    def test_without_a_picture_the_stream_starts_at_once(self):
        orig = self.d.camera_urls
        self.d.camera_urls = lambda name: ("rtsp://192.168.1.12:554/live", None, "Garden")  # direct, no picture
        try:
            self.live("garden")
        finally:
            self.d.camera_urls = orig
        self.assertEqual(self.stills(), [])
        self.assertIsNotNone(self.playing())

    def test_end_and_other_camera_drop_late_pictures(self):
        self.live()
        d, = self.stills()
        self.ctl.end_live()
        self.assertFalse(self.ctl.play_timer.active)  # nothing left to start
        d.fire(self.d.STILL)
        self.assertIsNone(self.ctl.still_screen)
        self.live("garden")
        old, = self.stills()
        self.live("front_door")  # another camera while the first is still opening
        new, = self.stills()
        old.fire(self.d.STILL)
        self.assertIsNone(self.ctl.still_screen)
        new.fire(self.d.STILL)
        self.assertIsNotNone(self.ctl.still_screen)

    def test_still_has_a_maximum_and_a_failed_picture_is_quiet(self):
        self.live()
        d, = self.stills()
        d.fire(self.d.STILL)
        self.assertIsNotNone(self.ctl.still_screen)
        self.ctl.still_timer.callback[0]()  # STILL_MAX_SECONDS without video
        self.assertIsNone(self.ctl.still_screen)
        self.ctl.end_live()
        self.live("garden")
        d, = self.stills()
        self.assertNotIn("garden", self.playing() or "")
        for ok, err in d.callbacks:
            if err:
                err(ERR)
        self.assertIsNone(self.ctl.still_screen)
        self.assertEqual(self.ctl.live_stream, "garden")
        self.assertIn("garden", self.playing())  # a failed picture does not hold the stream back


if __name__ == "__main__":
    unittest.main()
