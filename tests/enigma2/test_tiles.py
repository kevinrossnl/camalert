"""#49 (v1.0 part): every tile type shows 'camera not reachable' instead of a frozen or black picture, and the
notification mode shows a snapshot with the title and priority (like Kodi)."""
import time
import types
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake

SNAP = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
CAMS = [("front_door", "Front door", SNAP % "front_door"), ("garden", "Garden", SNAP % "garden")]
ERR = types.SimpleNamespace(getErrorMessage=lambda: "timed out")


class TestTiles(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.ca = self.env.camalert
        self.d = self.ca.display
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.env.config.plugins.camalert.server.value = "http://192.168.1.10:1984"
        self.ca.plugin.sessionstart(0, session=self.session)
        self.ctl = self.d.Controller.instance
        self.ctl._names, self.ctl._names_at = ["front_door", "garden"], time.time()

    def tearDown(self):
        e2fake.uninstall()

    def check_tile(self, screen, tile, error, picture):
        screen.active = True
        self.assertFalse(screen[error].visible)
        tile.failed(ERR)
        self.assertFalse(screen[error].visible)  # one miss is not shown
        tile.failed(ERR)
        self.assertTrue(screen[error].visible)
        self.assertEqual(screen[error].text, "Camera not reachable")
        self.assertFalse(screen[picture].visible)
        tile.loaded(None)
        self.assertFalse(screen[error].visible)
        self.assertTrue(screen[picture].visible)

    def test_mosaic_strip_and_tour_tiles(self):
        m = self.session.open(self.d.MosaicScreen, CAMS, 10)
        self.check_tile(m, m.tiles[1], "error1", "tile1")
        s = self.session.instantiateDialog(self.d.StripWindow, CAMS, False, None)
        self.check_tile(s, s.tiles[0], "error0", "tile0")
        t = self.session.open(self.d.TourScreen, CAMS, 8)
        t.started()
        self.check_tile(t, t.tile, "error0", "tile0")

    def test_photo_window(self):
        w = self.session.instantiateDialog(self.d.PhotoWindow, "garden", SNAP % "garden", "Garden")
        self.check_tile(w, w, "error", "photo")
        w.failed(ERR)
        w.failed(ERR)
        self.assertEqual(w["title"].text, "Garden - camera not reachable")

    def test_notification_shows_snapshot_title_and_priority(self):
        self.assertEqual(self.ctl.show("front_door", 10, "notify", "high", "frigate", "Person"), "show")
        n = self.ctl.notice
        self.assertEqual(type(n).__name__, "NotifyWindow")
        self.assertEqual(n["title"].text, "Camera: Person · Front door  ·  High")
        self.assertEqual(n.url, SNAP % "front_door")
        self.assertNotIn("AddPopup", self.env.rec.names())
        n.active = True
        n.failed(ERR)
        self.assertTrue(n["error"].visible)
        self.ctl.show("garden", 10, "notify", "normal")
        self.assertIsNot(self.ctl.notice, n)  # replaced
        self.assertEqual(self.ctl.notice["title"].text, "Camera: Garden")
        self.ctl.notice.stop()
        self.assertIsNone(self.ctl.notice)

    def test_notification_without_snapshot_uses_a_popup(self):
        self.d.camera_urls = lambda name: ("rtsp://192.168.1.10/x", None, "Front door")
        self.ctl.show("front_door", 10, "notify", "alarm")
        self.assertIsNone(self.ctl.notice)
        popups = [c for c in self.env.rec.calls if c[0] == "AddPopup"]
        self.assertEqual(popups[-1][1][0], "Camera: Front door  ·  Alarm")


if __name__ == "__main__":
    unittest.main()
