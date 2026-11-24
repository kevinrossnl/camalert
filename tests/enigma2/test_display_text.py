"""On-screen texts of the Enigma2 plugin come from camalert_core.present (#41): key hints from the key map,
event-list values as codes with translated labels; no hard-coded English hints."""
import os
import re
import time
import unittest

import _paths
from enigma2.harness import e2fake

SNAP = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
CAMS = [("front_door", "Front door", SNAP % "front_door"), ("garden", "Garden", SNAP % "garden")]


class TestNoHardCodedHints(unittest.TestCase):
    def test_sources(self):
        for name in ("display.py", "diagnostics.py"):
            text = open(os.path.join(_paths.ENIGMA2, name), encoding="utf-8").read()
            for pattern in (r'"[^"\n]*OK = live', r'"[^"\n]*< >', r'_\("EXIT = close"\)', r'_\("GREEN = live"\)',
                            r'MENU = diagnostics', r'%d-%m-%Y', r'reason = "[^"]'):
                self.assertFalse(re.search(pattern, text), "%s: %s" % (name, pattern))


class TestTexts(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.ca = self.env.camalert
        self.present = self.ca.camalert_core.present
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.c = self.env.config.plugins.camalert
        self.c.server.value = "http://192.168.1.10:1984"
        self.ca.plugin.sessionstart(0, session=self.session)
        self.ctl = self.ca.display.Controller.instance
        self.ctl._names, self.ctl._names_at = ["front_door", "garden"], time.time()
        self.ca.display.GLYPHS = True

    def tearDown(self):
        e2fake.uninstall()

    def test_ascii_without_fallback_font(self):
        self.ca.display.GLYPHS = False
        self.assertIn("< > = other camera", self.ca.display.window_hint("garden"))

    def hint(self, context, **kw):
        return self.present.key_hint("enigma2", context, self.ca._, ptz_key=self.c.ptz_key.value, **kw)

    def test_photo_window_hint(self):
        w = self.session.instantiateDialog(self.ca.display.PhotoWindow, "front_door", SNAP % "front_door", "Front door",
                                           True)
        self.assertEqual(w["title"].text, "Front door" + self.present.SEPARATOR + self.hint("window"))
        self.assertIn("◀ ▶ = other camera", w["title"].text)
        plain = self.session.instantiateDialog(self.ca.display.PhotoWindow, "garden", SNAP % "garden", "Garden")
        self.assertEqual(plain["title"].text, "Garden")

    def test_ptz_camera_hint_has_the_ptz_key(self):
        self.ctl.devices = {"front_door": {"type": "onvif"}}
        self.ctl.load_devices = lambda: self.ctl.devices
        self.assertIn("BLUE = camera control", self.ca.display.window_hint("front_door"))
        self.ctl.enter_ptz("front_door")
        self.assertEqual(self.ctl.ptz_overlay["text"].text, "Camera control (PTZ): Front door   "
                         + self.hint("ptz"))
        self.assertIn("EXIT/BLUE = end camera control", self.ctl.ptz_overlay["text"].text)

    def test_strip_window_hint_has_no_other_camera(self):
        w = self.session.instantiateDialog(self.ca.display.StripWindow, CAMS, True, None)
        self.assertTrue(w["title"].text.endswith("OK = live   EXIT = close"), w["title"].text)

    def test_mosaic_and_tour(self):
        m = self.session.open(self.ca.display.MosaicScreen, CAMS, 10)
        self.assertEqual(m["title"].text, "Cameras   OK/EXIT = close")
        t = self.session.open(self.ca.display.TourScreen, CAMS, 8)
        t.started()
        self.assertEqual(t["title"].text, " Front door   (1/2, tour)   " + self.hint("tour") + " ")
        t.toggle_hold()
        self.assertIn("(1/2, paused)", t["title"].text)

    def test_event_reasons_are_codes(self):
        self.c.dnd.value = True
        self.assertEqual(self.ctl.show("front_door", 10, "photo", "normal"), "ignore")
        self.assertEqual(self.ctl.events[0]["reason"], "dnd")
        self.c.dnd.value = False
        self.c.cooldown.value = "*=30"
        self.assertEqual(self.ctl.show("garden", 10, "photo", "normal"), "show")
        self.ctl.hide()
        self.assertEqual(self.ctl.show("garden", 10, "photo", "normal"), "ignore")
        self.assertEqual(self.ctl.events[0]["reason"], "cooldown:30")
        self.assertEqual(self.ctl.show("nope", 10, "photo", "high"), "error")
        self.assertEqual(self.ctl.events[0]["reason"], "unknown_camera")
        for e in self.ctl.events:
            code, _n = self.present.parse_reason(e["reason"])
            self.assertTrue(code is None or code in self.present.REASONS, e["reason"])

    def test_event_list_screen(self):
        self.c.dnd.value = True
        self.ctl.show("front_door", 10, "photo", "normal", "frigate", "Person")
        s = self.session.open(self.ca.diagnostics.EventsScreen)
        line = s["list"].list[0][0]
        self.assertRegex(line, r"^\d\d:\d\d:\d\d  front_door · Person  \(Frigate, Normal\) -> Ignored$")
        s.selected()
        info = s["info"].text.split("\n")
        self.assertEqual(info[2:], ["Source: Frigate", "Priority: Normal", "Result: Ignored", "Reason: Do not disturb"])
        self.assertRegex(info[0], r"^Time: \d\d/\d\d/\d{4} \d\d:\d\d:\d\d$")  # en_GB


if __name__ == "__main__":
    unittest.main()
