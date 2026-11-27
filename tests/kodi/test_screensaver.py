"""CamAlert mosaic as Kodi screensaver (#99): the xbmc.ui.screensaver extension of service.camalert and
screensaver.py. Runs with the strict Kodi stubs (tests/kodi/stubs.py); nothing contacts a camera or a player."""
import os
import unittest
import xml.etree.ElementTree as ET
import zipfile

import _paths  # noqa: E402
from kodi import stubs as kodi_stubs  # noqa: E402
from kodi.test_kodi import Built, KNOWN_STUB_PROBLEMS  # noqa: E402

ADDON = _paths.KODI_ADDON
SNAP = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
NAMES = ["front_door", "garden", "drive", "shed", "c5", "c6", "c7", "c8", "c9", "c10"]


class Action(object):
    def __init__(self, aid):
        self.aid = aid

    def getId(self):
        return self.aid

    def getButtonCode(self):
        return 0


class _Screensaver(object):
    kodi = None

    def setUp(self):
        self.ss = Built.module("screensaver", self.kodi)
        self.sources = Built.module("sources", self.kodi)
        self.display = Built.module("display", self.kodi)
        for name in ("all_camera_names", "camera_urls"):
            self.addCleanup(setattr, self.sources, name, getattr(self.sources, name))
        self.asked = []

        def all_names(s=None):
            self.asked.append("all")
            return list(NAMES)

        def urls(name, s=None):
            if name == "garden":
                return ("rtsp://x/garden", None, "Garden")  # no snapshot: left out
            return ("rtsp://x/" + name, SNAP % name, name.title())

        self.sources.all_camera_names = all_names
        self.sources.camera_urls = urls

    def settings(self, **kw):
        return dict(Built.module("klogic", self.kodi).parse_settings({"server": "http://192.168.1.10:1984"}), **kw)

    def test_extension_in_addon_xml_and_zip(self):
        z = zipfile.ZipFile(Built.get().addon_zip)
        root = ET.fromstring(z.read("service.camalert/addon.xml"))
        ext = [e for e in root.findall("extension") if e.get("point") == "xbmc.ui.screensaver"]
        self.assertEqual([e.get("library") for e in ext], ["screensaver.py"])
        self.assertIn("service.camalert/screensaver.py", z.namelist())
        self.assertTrue(os.path.exists(os.path.join(ADDON, "screensaver.py")))
        points = [e.get("point") for e in root.findall("extension")]
        for kept in ("xbmc.service", "xbmc.python.script", "xbmc.python.pluginsource", "xbmc.addon.metadata"):
            self.assertIn(kept, points)

    def test_mosaic_cameras_or_all_at_most_nine(self):
        cams = self.ss.cameras(self.settings())
        self.assertEqual(self.asked, ["all"])
        self.assertEqual(len(cams), 9)
        self.assertNotIn("garden", [c[0] for c in cams])
        self.assertEqual(cams[0], ("front_door", "Front_Door", SNAP % "front_door"))
        self.asked = []
        cams = self.ss.cameras(self.settings(mosaic="shed, garden,drive"))
        self.assertEqual(self.asked, [])
        self.assertEqual([c[0] for c in cams], ["shed", "drive"])

    def test_no_go2rtc_is_black_without_cameras(self):
        s = self.settings(server="")
        self.assertTrue(self.sources.go2rtc_problem(s))
        win = self.ss.window(self.ss.Done(), s)()
        self.assertIsInstance(win, self.ss.Blank)
        self.assertFalse(hasattr(win, "feeder"))
        self.assertEqual(self.asked, [])  # no camera list fetched

    def test_no_cameras_is_black(self):
        self.sources.all_camera_names = lambda s=None: []
        self.assertIsInstance(self.ss.window(self.ss.Done(), self.settings())(), self.ss.Blank)

        def broken(s=None):
            raise IOError("timed out")
        self.sources.all_camera_names = broken
        self.assertIsInstance(self.ss.window(self.ss.Done(), self.settings())(), self.ss.Blank)

    def test_every_key_closes(self):
        done = self.ss.Done()
        blank = self.ss.Blank(done, "No go2rtc address")
        blank.onAction(Action(1))
        self.assertTrue(done.event.is_set())
        if "mosaic labels" in KNOWN_STUB_PROBLEMS:
            return
        for aid in (1, 7, 92, 88, 135, 251):  # LEFT, OK, BACK, volume, ENTER, anything
            done = self.ss.Done()
            win = self.ss.ScreenSaver(done, self.ss.cameras(self.settings()), self.settings(), tour=False)
            labels = []
            win.title.setLabel = labels.append
            win.update_title()
            self.assertEqual(labels, [""])  # no title and no key hints over the pictures
            win.onAction(Action(aid))
            self.assertTrue(done.event.is_set(), aid)

    def run_saver(self, s, waits):
        """run() with the window made in this thread and recorded start/stop."""
        made = []

        def open_window(factory):
            w = factory()
            w.start = lambda: made.append("start")
            stop = w.stop
            w.stop = lambda: (made.append("stop"), stop())
            made.append(w)
            return w
        self.addCleanup(setattr, self.display, "open_window", self.display.open_window)
        self.display.open_window = open_window
        settings = self.ss.kodiapi.settings
        self.addCleanup(setattr, self.ss.kodiapi, "settings", settings)
        self.ss.kodiapi.settings = lambda: s
        kodi_stubs.MONITOR["waits"] = waits
        return made

    def test_run_ends_when_kodi_ends_the_screensaver(self):
        if "mosaic labels" in KNOWN_STUB_PROBLEMS:
            return
        made = self.run_saver(self.settings(), 1000)
        Monitor = self.ss.Monitor
        monitors = []

        def remember(done):
            m = Monitor(done)
            monitors.append(m)
            m.onScreensaverDeactivated()  # Kodi ends the screensaver (a key, a notification, playback)
            return m
        self.addCleanup(setattr, self.ss, "Monitor", Monitor)
        self.ss.Monitor = remember
        self.ss.run()
        self.assertIsInstance(made[0], self.ss.ScreenSaver)
        self.assertEqual(made[1:], ["start", "stop"])
        self.assertEqual(kodi_stubs.MONITOR["waits"], 1000)  # ended by the deactivation, not by Kodi's abort

    def test_run_ends_on_abort_and_survives_errors(self):
        made = self.run_saver(self.settings(server=""), 3)
        self.ss.run()
        self.assertIsInstance(made[0], self.ss.Blank)
        self.assertEqual(made[1:], ["start", "stop"])

        def broken(factory):
            raise RuntimeError("window could not be created")
        self.display.open_window = broken
        self.ss.run()  # logged, no exception into Kodi
        self.assertTrue(any("screensaver failed" in m for m in kodi_stubs.LOGGED))


# once per Kodi version, each with the strict stubs of that version (#29)
for _v in kodi_stubs.VERSIONS:
    _name = "TestScreensaver_%d" % _v
    globals()[_name] = type(_name, (_Screensaver, unittest.TestCase), {"kodi": _v})


if __name__ == "__main__":
    unittest.main()
