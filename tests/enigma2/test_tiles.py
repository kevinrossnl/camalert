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
        self.assertTrue(screen[error].visible)  # #110: 'Loading picture...' until the first picture
        self.assertEqual(screen[error].text, "Loading picture...")
        self.assertTrue(tile.first)
        tile.failed(ERR)
        self.assertEqual(screen[error].text, "Loading picture...")  # one miss is not shown
        tile.failed(ERR)
        self.assertTrue(screen[error].visible)
        self.assertEqual(screen[error].text, "Camera not reachable")
        self.assertFalse(screen[picture].visible)
        tile.loaded(None)
        self.assertFalse(screen[error].visible)
        self.assertTrue(screen[picture].visible)
        self.assertFalse(tile.first)

    def test_first_picture_loads_at_once(self):
        """#110: the first picture hides 'Loading picture...' without a failure first."""
        w = self.session.instantiateDialog(self.d.PhotoWindow, "garden", SNAP % "garden", "Garden")
        w.active = True
        self.assertEqual(w["error"].text, "Loading picture...")
        w.loaded(None)
        self.assertFalse(w["error"].visible)
        self.assertTrue(w["photo"].visible)

    def test_download_asks_for_a_cached_first_picture(self):
        asked = []

        class R(object):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"jpeg"
        self.d.open_url = lambda url, timeout=8: asked.append(url) or R()
        import tempfile
        import os
        path = os.path.join(tempfile.mkdtemp(), "p.jpg")
        self.d._download(SNAP % "garden", path, None, True)
        self.d._download(SNAP % "garden", path)
        self.assertEqual(asked, [SNAP % "garden" + "&cache=10s", SNAP % "garden"])
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"jpeg")

    def test_protect_camera_pictures_come_from_protect(self):
        """#109: a UniFi Protect camera gets its picture from the console in the devices file, other cameras and the
        setting off from go2rtc."""
        import tempfile
        import os
        asked, protect = [], []

        class R(object):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"go2rtc"
        self.d.open_url = lambda url, timeout=8: asked.append(url) or R()
        console = {"type": "unifi", "host": "192.168.1.1", "port": 443, "user": "viewer", "password": "pw"}
        self.ctl.load_devices = lambda: {"nvr": console}
        self.ctl.devices_mtime = 1.0
        self.addCleanup(setattr, self.d.SNAPSHOTS.protect, "fetch", None)
        self.d.SNAPSHOTS.protect.fetch = lambda dev, cam, names, width: (
            protect.append((dev["host"], cam, width)) or (b"protect" if cam == "front_door" else None))
        self.d._SNAPSHOT_KEY[0] = None
        path = os.path.join(tempfile.mkdtemp(), "p.jpg")
        self.d._download(SNAP % "front_door", path, None, True, "front_door")
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"protect")
        self.d._download(SNAP % "garden", path, None, True, "garden")
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"go2rtc")
        self.assertEqual(protect, [("192.168.1.1", "front_door", 640), ("192.168.1.1", "garden", 640)])
        self.assertEqual(asked, [SNAP % "garden" + "&cache=10s"])
        self.env.config.plugins.camalert.protect_snapshots.value = False
        self.d._download(SNAP % "front_door", path, None, False, "front_door")
        self.assertEqual(len(protect), 2)  # turned off: go2rtc
        self.assertEqual(asked[-1], SNAP % "front_door")

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
        self.assertEqual(n["error"].text, "Loading picture...")  # #110
        n.failed(ERR)
        self.assertTrue(n["error"].visible)
        self.assertEqual(n["error"].text, "Camera not reachable")
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
