"""#91: live view shows a still picture at once (warm feed, Protect, go2rtc cache, frame.jpeg) until the stream
shows video; the picture is fetched in a thread, never on the GUI thread."""
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

    def test_still_until_the_first_frame(self):
        self.assertIn(self.ctl.service_event, self.session.nav.event)
        self.live()
        d, = self.stills()  # fetched in a thread: the live view starts at once
        self.assertEqual(d.args[0], "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640")
        self.assertIs(d.args[3], True)  # first picture: warm / Protect / go2rtc cache (Snapshots order)
        self.assertIsNone(self.ctl.still_screen)
        d.fire(self.d.STILL)
        self.assertIsNotNone(self.ctl.still_screen)
        self.ctl.service_event(self.ev.evStart)  # not video yet
        self.assertIsNotNone(self.ctl.still_screen)
        self.ctl.service_event(self.ev.evVideoSizeChanged)
        self.assertIsNone(self.ctl.still_screen)

    def test_stream_faster_than_the_picture(self):
        self.live()
        d, = self.stills()
        self.ctl.service_event(self.ev.evVideoSizeChanged)
        d.fire(self.d.STILL)
        self.assertIsNone(self.ctl.still_screen)  # never cover a running stream

    def test_end_and_other_camera_drop_late_pictures(self):
        self.live()
        d, = self.stills()
        self.ctl.end_live()
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
        for ok, err in d.callbacks:
            if err:
                err(ERR)
        self.assertIsNone(self.ctl.still_screen)
        self.assertEqual(self.ctl.live_stream, "garden")


if __name__ == "__main__":
    unittest.main()
