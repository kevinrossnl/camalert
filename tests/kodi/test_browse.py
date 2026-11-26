"""Kodi camera list for the home screen (#107): the video add-on (plugin.py) and its pure list builder (browse.py).
Runs with the strict Kodi stubs (tests/kodi/stubs.py); nothing contacts a camera or a player."""
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

import _paths  # noqa: E402
from kodi import stubs as kodi_stubs  # noqa: E402
from kodi.test_kodi import Built  # noqa: E402

ADDON = _paths.KODI_ADDON
BASE = "plugin://service.camalert/"
CAMS = [("front_door", "Front door", "http://192.168.1.10:1984/api/frame.jpeg?src=front_door"),
        ("garden", "Garden", None)]


def query(url):
    return url.split("?", 1)[1]


class TestBrowse(unittest.TestCase):
    def setUp(self):
        self.b = Built.module("browse")

    def test_root_order_and_actions(self):
        items = self.b.root_items(BASE, CAMS, None, 1000)
        self.assertEqual([i["kind"] for i in items], ["mosaic", "tour", "camera", "camera", "events", "settings"])
        self.assertEqual([self.b.parse(query(i["url"]))["do"] for i in items],
                         ["mosaic", "tour", "live", "live", "events", "settings"])
        self.assertEqual([items[n]["label"] for n in (0, 1, 4, 5)], [30171, 30172, 30204, 30284])
        cam = items[2]
        self.assertEqual((cam["label"], cam["camera"], cam["label2"]), ("Front door", "front_door", 30043))
        self.assertEqual(self.b.parse(query(cam["url"])), {"do": "live", "cam": "front_door"})
        (label, url), = cam["context"]
        self.assertEqual(label, 30291)
        self.assertEqual(self.b.parse(query(url)), {"do": "show", "cam": "front_door"})
        for i in items:
            self.assertTrue(i["url"].startswith(BASE + "?"), i)
            self.assertFalse(i["folder"], i)

    def test_thumbnail_is_fresh_and_never_secret(self):
        b = self.b
        self.assertEqual(b.safe_thumb("http://192.168.1.10:1984/api/frame.jpeg?src=front_door", 1000.7),
                         "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&camalert_t=990")
        self.assertEqual(b.safe_thumb("http://192.168.1.10/snap.jpg", 1000),
                         "http://192.168.1.10/snap.jpg?camalert_t=990")
        self.assertNotEqual(b.safe_thumb("http://a.invalid/x.jpg", 1000), b.safe_thumb("http://a.invalid/x.jpg", 1031))
        for bad in ("http://user:PASSWORD@192.168.1.10/snap.jpg", "http://user@192.168.1.10/snap.jpg",
                    "http://192.168.1.10/snap.cgi?user=admin&pwd=secret", "http://192.168.1.10/a?token=abc",
                    "http://192.168.1.10/a?password=x", "rtsp://192.168.1.10/live", "", None):
            self.assertIsNone(b.safe_thumb(bad, 1000), bad)
        items = b.root_items(BASE, [("cam", "Cam", "http://admin:PASSWORD@192.168.1.10/snap.jpg")], None, 1000)
        self.assertNotIn("PASSWORD", json.dumps(items))
        self.assertIsNone(items[2]["thumb"])

    def test_camera_names_are_quoted(self):
        items = self.b.root_items(BASE, [("a b&c=d", "A", None)], None, 1000)
        url = items[2]["url"]
        self.assertNotIn(" ", url)
        self.assertEqual(self.b.parse(query(url))["cam"], "a b&c=d")

    def test_problem_instead_of_an_empty_list(self):
        items = self.b.root_items(BASE, [], "go2rtc address not set", 1000)
        self.assertEqual([i["kind"] for i in items], ["problem", "settings"])
        self.assertEqual(items[0]["label"], "go2rtc address not set")
        self.assertEqual(self.b.parse(query(items[0]["url"]))["do"], "settings")
        # no problem but no cameras: mosaic and tour stay, no camera items
        self.assertEqual([i["kind"] for i in self.b.root_items(BASE, [], None, 1000)],
                         ["mosaic", "tour", "events", "settings"])

    def test_parse(self):
        p = self.b.parse
        self.assertIsNone(p(""))
        self.assertIsNone(p("?"))
        self.assertEqual(p("?do=mosaic"), {"do": "mosaic"})
        self.assertEqual(p("do=live&cam=garden"), {"do": "live", "cam": "garden"})
        self.assertEqual(p("do=nonsense"), {"do": "unknown"})
        self.assertEqual(p("do=live"), {"do": "unknown"})  # a camera action needs a camera
        self.assertEqual(p("do=show&cam=garden&extra=1"), {"do": "show", "cam": "garden"})


class TestPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = Built.module("plugin")
        kodi_stubs.CALLS[:] = []
        self.addCleanup(setattr, self.plugin, "cameras", self.plugin.cameras)
        self.addCleanup(setattr, self.plugin, "pause", self.plugin.pause)
        self.plugin.pause = lambda: None

    def sent(self):
        return [json.loads(c[1][1]) for c in kodi_stubs.calls("xbmcgui.Window.setProperty") if c[1][0] == "camalert.cmd"]

    def test_root_listing(self):
        self.plugin.cameras = lambda: (CAMS, None)
        self.plugin.run([BASE, "7", ""])
        added = kodi_stubs.calls("xbmcplugin.addDirectoryItems")
        self.assertEqual(len(added), 1)
        handle, items = added[0][1][0], added[0][1][1]
        self.assertEqual((handle, len(items)), (7, 6))
        url, li, folder = items[2]
        self.assertEqual((li.label, folder), ("Front door", False))
        self.assertIn("do=live", url)
        arts = [c[1][0] for c in kodi_stubs.calls("xbmcgui.ListItem.setArt")]
        self.assertTrue(any("camalert_t=" in a.get("thumb", "") for a in arts), arts)
        menus = kodi_stubs.calls("xbmcgui.ListItem.addContextMenuItems")
        self.assertTrue(any(m[1][0][0][1].startswith("RunPlugin(%s?" % BASE) for m in menus), menus)
        self.assertEqual(kodi_stubs.calls("xbmcplugin.endOfDirectory")[0][1][0], 7)
        self.assertEqual(self.sent(), [])  # a listing sends nothing to the service

    def test_actions_go_to_the_service(self):
        for q, want in (("?do=live&cam=garden", {"do": "show", "cam": "garden", "mode": "live"}),
                        ("?do=show&cam=garden", {"do": "show", "cam": "garden", "mode": "photo"}),
                        ("?do=mosaic", {"do": "mosaic"}), ("?do=tour", {"do": "tour"})):
            kodi_stubs.CALLS[:] = []
            self.plugin.run([BASE, "-1", q])
            self.assertEqual(self.sent(), [want], q)
            self.assertEqual(kodi_stubs.calls("xbmcplugin.endOfDirectory"), [], q)

    def test_settings_events_and_unknown(self):
        opened, shown = [], []
        script = Built.module("script")
        self.addCleanup(setattr, script, "events", script.events)
        script.events = lambda: shown.append(1)
        kodiapi = Built.module("kodiapi")
        self.addCleanup(setattr, kodiapi, "addon", kodiapi.addon)

        class A(object):
            def openSettings(self):
                opened.append(1)
        kodiapi.addon = lambda: A()
        for q in ("?do=settings", "?do=events", "?do=whatever"):
            self.plugin.run([BASE, "-1", q])
        self.assertEqual((opened, shown, self.sent()), ([1], [1], []))

    def test_cameras_problem_and_unreachable(self):
        sources = Built.module("sources")
        for name in ("go2rtc_problem", "all_camera_names", "camera_urls"):
            self.addCleanup(setattr, sources, name, getattr(sources, name))
        sources.go2rtc_problem = lambda s: "go2rtc address not set"
        self.assertEqual(self.plugin.cameras(), ([], "go2rtc address not set"))
        sources.go2rtc_problem = lambda s: None

        def boom(s=None):
            raise OSError("timed out http://admin:PASSWORD@192.168.1.10/x")
        sources.all_camera_names = boom
        cams, problem = self.plugin.cameras()
        self.assertEqual(cams, [])
        self.assertIn("timed out", problem)
        self.assertNotIn("\n", problem)
        self.assertNotIn("PASSWORD", problem)
        sources.all_camera_names = lambda s=None: ["front_door", "gone"]
        sources.camera_urls = lambda n, s=None: ("live", "http://192.168.1.10:1984/api/frame.jpeg?src=" + n,
                                                 "Front door") if n == "front_door" else None
        cams, problem = self.plugin.cameras()
        self.assertIsNone(problem)
        self.assertEqual(cams[0], ("front_door", "Front door", "http://192.168.1.10:1984/api/frame.jpeg?src=front_door"))
        self.assertEqual((cams[1][0], cams[1][2]), ("gone", None))


class TestServiceCommands(unittest.TestCase):
    def test_show_with_mode(self):
        service = Built.module("service")
        xbmcgui = sys.modules["xbmcgui"]
        got = []

        class Ctl(object):
            def show(self, *a):
                got.append(a)
        svc = service.Service.__new__(service.Service)
        svc.ctl = Ctl()
        orig = xbmcgui.Window.getProperty
        self.addCleanup(setattr, xbmcgui.Window, "getProperty", orig)
        for cmd, mode in (({"do": "show", "cam": "garden"}, None),
                          ({"do": "show", "cam": "garden", "mode": "live"}, "live"),
                          ({"do": "show", "cam": "garden", "mode": "photo"}, "photo"),
                          ({"do": "show", "cam": "garden", "mode": "evil"}, None)):
            xbmcgui.Window.getProperty = lambda self, k, c=json.dumps(cmd): c if k == "camalert.cmd" else ""
            svc.script_commands()
            self.assertEqual(got[-1], ("garden", None, mode, "high", "menu"), cmd)


class TestPackage(unittest.TestCase):
    def test_pluginsource_in_addon_xml_and_zip(self):
        b = Built.get()
        z = zipfile.ZipFile(b.addon_zip)
        root = ET.fromstring(z.read("service.camalert/addon.xml"))
        src = [e for e in root.findall("extension") if e.get("point") == "xbmc.python.pluginsource"]
        self.assertEqual(len(src), 1)
        self.assertEqual(src[0].get("library"), "plugin.py")
        self.assertEqual(src[0].find("provides").text.split(), ["video"])
        self.assertIn("service.camalert/plugin.py", z.namelist())
        self.assertTrue(os.path.exists(os.path.join(ADDON, "plugin.py")))


if __name__ == "__main__":
    unittest.main()
