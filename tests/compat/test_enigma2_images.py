"""The Enigma2 plugin against the API of other images (openATV, OpenPLi, OpenBH, VTi, DreamOS).

The fake modules (tests/compat/e2fake.py) are built from API snapshots of the real enigma2 sources
(tests/compat/fixtures/e2api/*.json, made by tools/e2_api_snapshot.py): only methods that exist on that image,
called with the parameters that image accepts. Results are summarised in docs/compatibility.md.
"""
import os
import re
import sys
import time
import unittest
import xml.etree.ElementTree as ET

import _paths  # noqa: E402,F401
from compat import e2fake  # noqa: E402

SUPPORTED = ("openatv", "openpli", "openbh", "vti")
SNAP = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
CAMS = [("front_door", "Front door", SNAP % "front_door"), ("garden", "Garden", SNAP % "garden")]
# attributes of the <screen> element itself (handled by the screen code, not by the widget attribute parser)
SCREEN_ATTRS = {"name", "position", "size", "title", "flags", "backgroundColor", "zPosition", "id"}


def skin_problems(screen, snapshot):
    """What the image's skin loader would refuse: unknown attributes and widgets without a component."""
    problems = []
    root = ET.fromstring(screen.skin)
    known = set(snapshot["skin_attributes"])
    for attr in root.attrib:
        if attr not in SCREEN_ATTRS and attr not in known:
            problems.append("screen attribute %s" % attr)
    for el in root.iter():
        if el is root or el.tag == "convert":
            continue
        for attr in el.attrib:
            if attr not in known:
                problems.append("%s attribute %s" % (el.tag, attr))
        if el.tag == "widget":
            key = el.get("name") or el.get("source")
            if key and key not in screen:
                problems.append("widget %s has no component (SkinError on the receiver)" % key)
    return problems


class ImageCase(object):
    profile = None

    def setUp(self):
        self.env = e2fake.install(self.profile)
        self.ca = self.env.camalert
        self.session = self.env.Session()
        self.infobar = self.env.InfoBar(self.session)
        self.env.config.plugins.camalert.server.value = "http://192.168.1.10:1984"

    def tearDown(self):
        e2fake.uninstall()

    def start(self):
        self.ca.plugin.sessionstart(0, session=self.session)
        return self.ca.display.Controller.instance

    def test_plugin_descriptors(self):
        descriptors = self.ca.plugin.Plugins()
        self.assertGreaterEqual(len(descriptors), 4)
        where_names = [a for a in self.env.snapshot["classes"]["PluginDescriptor"]["attrs"] if a.startswith("WHERE_")]
        for d in descriptors:
            for w in d.where if isinstance(d.where, list) else [d.where]:
                self.assertIn(w, where_names)

    def test_session_start(self):
        ctrl = self.start()
        self.assertIsNotNone(ctrl)
        self.assertIn("listenTCP", self.env.rec.names())

    def test_settings_screen(self):
        self.start()
        c = self.env.config.plugins.camalert
        for source in ("go2rtc", "direct"):
            for mode in ("photo", "live", "notify"):
                c.source.value, c.mode.value = source, mode
                self.ca.plugin.main(self.session)
                screen = self.session.opened[-1]
                self.assertEqual(type(screen).__name__, "CamAlertSetup")
                self.assertTrue(screen["config"].list)
                self.assertEqual(skin_problems(screen, self.env.snapshot), [])

    def test_settings_skin_scales_to_desktop(self):
        w = self.env.profile["desktop"][0]
        root = ET.fromstring(self.ca.setup.CamAlertSetup.build_skin(w))
        width = int(root.get("size").split(",")[0])
        self.assertLessEqual(width, w)

    def test_other_screens_and_skins(self):
        ctrl = self.start()
        d = self.ca.display
        screens = [
            self.session.open(self.ca.diagnostics.DiagnosticsScreen),
            self.session.open(self.ca.diagnostics.EventsScreen),
            self.session.open(d.MosaicScreen, CAMS, 10),
            self.session.open(d.TourScreen, CAMS, 8),
            self.session.instantiateDialog(d.PhotoWindow, "front_door", SNAP % "front_door", "Front door", True),
            self.session.instantiateDialog(d.StripWindow, CAMS, True, None),
            self.session.instantiateDialog(d.PtzOverlay, "PTZ"),
        ]
        for s in screens:
            self.assertEqual(skin_problems(s, self.env.snapshot), [], type(s).__name__)
        self.assertIsNotNone(ctrl)

    def test_photo_window_and_mosaic_via_controller(self):
        ctrl = self.start()
        ctrl._names, ctrl._names_at = ["front_door", "garden"], time.time()
        self.assertEqual(ctrl.show("front_door", 10, "photo", "high"), "show")
        self.assertEqual(type(ctrl.window).__name__, "PhotoWindow")
        ctrl.hide()
        self.assertIsNone(ctrl.window)
        self.assertEqual(ctrl.mosaic("front_door,garden"), "show")
        self.assertEqual(type(self.session.opened[-1]).__name__, "MosaicScreen")

    def test_live_view_switches_and_returns(self):
        ctrl = self.start()
        ctrl._names, ctrl._names_at = ["front_door"], time.time()
        self.assertIn(ctrl.show("front_door", 10, "live", "high"), ("show", "live"))
        self.assertIn("playService", self.env.rec.names())

    def test_pause_tv_uses_timeshift_api(self):
        ctrl = self.start()
        ctrl.pause_tv()
        self.assertTrue(ctrl.paused, "InfoBar has neither startTimeshift nor pauseService")
        self.assertIn("InfoBar.startTimeshift", self.env.rec.names())
        ctrl.resume_tv()
        self.assertIn("InfoBar.unPauseService", self.env.rec.names())

    def test_standby_is_respected_and_alarm_wakes(self):
        ctrl = self.start()
        standby = sys.modules["Screens.Standby"]
        standby.inStandby = standby.Standby(self.session)
        ctrl._names, ctrl._names_at = ["front_door"], time.time()
        self.assertEqual(ctrl._show("front_door", 10, "photo", "normal"), "ignore")
        self.env.config.plugins.camalert.alarm_wake.value = True
        self.assertEqual(ctrl._show("front_door", 10, "photo", "alarm"), "wake")
        self.assertIn("Standby.Power", self.env.rec.names())

    def test_bouquet_reload(self):
        self.start()
        self.ca.bouquet.reload()
        self.assertIn("eDVBDB.reloadBouquets", self.env.rec.names())

    def test_remote_key_hooks_bind_and_unbind(self):
        self.start()
        amap = sys.modules["enigma"].eActionMap.getInstance()
        for cls in (self.ca.display.KeyHook, self.ca.display.GlobalKeys):
            before = len(amap.bound)
            hook = cls()
            self.assertEqual(len(amap.bound), before + 1)
            hook.remove()
            self.assertEqual(len(amap.bound), before)


def _case(name):
    return type("Test_%s" % name, (ImageCase, unittest.TestCase), {"profile": name})


for _name in SUPPORTED:
    globals()["Test_%s" % _name] = _case(_name)


class TestDreamOSKnownGaps(unittest.TestCase):
    """DreamOS is not supported. These tests pin down why, so docs/compatibility.md stays true."""

    def setUp(self):
        self.env = e2fake.install("dreamos")
        self.session = self.env.Session()
        self.env.InfoBar(self.session)

    def tearDown(self):
        e2fake.uninstall()

    def test_python_2(self):
        self.assertTrue(self.env.profile["python"].startswith("2."))

    def test_etimer_has_no_callback_list(self):
        with self.assertRaises(AttributeError):
            self.env.camalert.plugin.sessionstart(0, session=self.session)

    def test_config_list_screen_creates_no_help_widgets(self):
        provides = self.env.snapshot["classes"]["ConfigListScreen"]["provides"]
        self.assertNotIn("HelpWindow", provides)
        self.assertNotIn("VKeyIcon", provides)

    def test_navigation_has_no_service_or_group(self):
        self.assertNotIn("getCurrentlyPlayingServiceOrGroup", self.env.snapshot["classes"]["Navigation"]["methods"])


class TestSnapshots(unittest.TestCase):
    def test_every_profile_has_a_snapshot(self):
        for name, p in e2fake.PROFILES.items():
            snap = e2fake.api(p["api"])
            self.assertTrue(snap["source"], name)
            for cls in ("InfoBar", "Navigation", "Screen", "ConfigListScreen", "PluginDescriptor", "Session"):
                self.assertIn(cls, snap["classes"], "%s: %s" % (name, cls))

    def test_compatibility_doc_lists_every_profile(self):
        doc = os.path.join(e2fake.ROOT, "docs", "compatibility.md")
        with open(doc, encoding="utf-8") as f:
            text = f.read()
        for p in e2fake.PROFILES.values():
            self.assertIn(p["label"], text)
        for name in e2fake.PROFILES:
            self.assertTrue(re.search(r"\b%s\b" % name, text), name)


if __name__ == "__main__":
    unittest.main()
