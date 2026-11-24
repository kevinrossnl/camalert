"""#56: Enigma2 UI findings of the screenshot session - titles and key hints fit at every window size, mosaic tiles
keep their camera name when the camera is not reachable, no empty GREEN button in the event list, texts only from
CamAlert's own catalogue, short Do-not-disturb values, display modes named as in the glossary."""
import gettext
import os
import re
import time
import types
import unittest
import xml.etree.ElementTree as ET

import _paths  # noqa: F401
from enigma2.harness import e2fake

SNAP = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
CAMS = [("front_door", "Front door", SNAP % "front_door"), ("garden", "Garden", SNAP % "garden"),
        ("driveway", "Driveway", SNAP % "driveway")]
ERR = types.SimpleNamespace(getErrorMessage=lambda: "timed out")


def widgets(screen):
    return {w.get("name"): w for w in ET.fromstring(screen.skin).iter("widget")}


def size(w):
    return [int(v) for v in w.get("size").split(",")]


def font(w):
    return int(w.get("font").split(";")[1])


class Base(unittest.TestCase):
    profile = "openatv"

    def setUp(self):
        self.env = e2fake.install(self.profile)
        self.ca = self.env.camalert
        self.d = self.ca.display
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.c = self.env.config.plugins.camalert
        self.c.server.value = "http://192.168.1.10:1984"
        self.ca.plugin.sessionstart(0, session=self.session)
        self.ctl = self.d.Controller.instance
        self.ctl._names, self.ctl._names_at = [n for n, _t, _u in CAMS], time.time()
        self.d.GLYPHS = True

    def tearDown(self):
        e2fake.uninstall()

    def assert_fits(self, w, text):
        """One line, and the estimated text width fits the widget."""
        self.assertEqual(w.get("noWrap"), "1", w.get("name"))
        self.assertLessEqual(self.d.CHAR_W * font(w) * len(text), size(w)[0], (w.get("name"), text, font(w)))


class TestFit(Base):
    def test_fit_font(self):
        self.assertEqual(self.d.fit_font("Garden", 400, 26), 26)
        self.assertEqual(self.d.fit_font("", 400, 26), 26)
        self.assertEqual(self.d.fit_font("x" * 30, 400, 26), int(400 / (self.d.CHAR_W * 30)))
        self.assertEqual(self.d.fit_font("x" * 500, 400, 26), 15)  # never below 60 %
        self.assertEqual(self.d.fit_font("x" * 500, 400, 26, minimum=10), 10)


class TestTitles(Base):
    def check_photo_window(self):
        for window_size in ("small", "medium", "large"):
            for title_size in ("small", "normal", "large"):
                self.c.size.value, self.c.title_size.value = window_size, title_size
                w = self.session.instantiateDialog(self.d.PhotoWindow, "front_door", SNAP % "front_door",
                                                   "Person · Front door", True)
                skin = widgets(w)
                self.assertEqual(w["title"].text, "Person · Front door")
                self.assert_fits(skin["title"], w["title"].text)
                self.assertIn("EXIT = close", w["hint"].text)
                self.assert_fits(skin["hint"], w["hint"].text)
                self.assertGreater(int(skin["hint"].get("zPosition")), int(skin["error"].get("zPosition")))

    def test_photo_window_1080(self):
        self.check_photo_window()

    def test_strip_window_three_cameras(self):
        self.c.size.value = "medium"
        w = self.session.instantiateDialog(self.d.StripWindow, CAMS, True, "Motion")
        skin = widgets(w)
        self.assertEqual(w["title"].text, "Motion · Front door  ·  Garden  ·  Driveway")
        self.assert_fits(skin["title"], w["title"].text)
        self.assertEqual(w["hint"].text, "OK = live   EXIT = close")
        self.assert_fits(skin["hint"], w["hint"].text)

    def test_other_camera_updates_title_and_hint(self):
        self.ctl.show("front_door", 10, "photo", "high")
        w = self.ctl.window
        self.ctl.other_camera(1)
        self.assertEqual((w.stream, w["title"].text), ("garden", "Garden"))
        self.assertIn("EXIT = close", w["hint"].text)


class TestTitles720(TestTitles):
    profile = "openpli"  # 1280x720 skin

    def test_photo_window_720(self):
        self.check_photo_window()


class TestMosaicLabels(Base):
    def test_label_stays_on_unreachable_tile(self):
        for screen in (self.session.open(self.d.MosaicScreen, CAMS, 0),
                       self.session.instantiateDialog(self.d.StripWindow, CAMS, True, None)):
            skin = widgets(screen)
            self.assertGreater(int(skin["label0"].get("zPosition")), int(skin["error0"].get("zPosition")))
            screen.active = True
            screen.tiles[0].failed(ERR)
            screen.tiles[0].failed(ERR)
            self.assertTrue(screen["error0"].visible)
            self.assertTrue(screen["label0"].visible)
            self.assertEqual(screen["label0"].text, " Front door ")


class TestEventListGreen(Base):
    def open(self, frigate_id):
        self.ctl.record_event("front_door", "Person", "frigate", "normal", "show", "", frigate_id)
        s = self.session.open(self.ca.diagnostics.EventsScreen)
        s.selected()
        return s

    def test_no_clip_no_green_button(self):
        self.c.frigate_url.value = ""
        self.assertFalse(self.open("1700000000.1-abc")["key_green"].visible)
        self.c.frigate_url.value = "http://192.168.1.10:5000"
        self.assertFalse(self.open(None)["key_green"].visible)

    def test_clip_has_a_labelled_green_button(self):
        self.c.frigate_url.value = "http://192.168.1.10:5000"
        s = self.open("1700000000.1-abc")
        self.assertTrue(s["key_green"].visible)
        self.assertEqual(s["key_green"].text, "Play clip")

    def test_empty_list(self):
        s = self.session.open(self.ca.diagnostics.EventsScreen)
        s.selected()
        self.assertFalse(s["key_green"].visible)


class TestOwnCatalogueOnly(Base):
    def test_image_catalogue_is_never_used(self):
        image = gettext.gettext
        gettext.gettext = lambda t: t.lower()  # an English image translating our msgids ("Normal" -> "normal")
        try:
            self.assertEqual(self.ca._("Normal"), "Normal")
            self.assertEqual(self.ca._("High (doorbell)"), "High (doorbell)")
        finally:
            gettext.gettext = image

    def test_plugin_catalogue_is_used(self):
        own = gettext.dgettext
        gettext.dgettext = lambda domain, t: "Normaal" if (domain, t) == ("CamAlert", "Normal") else t
        try:
            self.assertEqual(self.ca._("Normal"), "Normaal")
        finally:
            gettext.dgettext = own


class TestSettingValues(Base):
    def test_display_modes_use_glossary_terms(self):
        self.assertEqual([t for _k, t in self.ca.MODES()], ["Photo window", "Live view", "Notification"])

    def test_do_not_disturb_values_are_short(self):
        # the fake ConfigSelection keeps only the keys: read the texts from the source
        source = open(os.path.join(_paths.ENIGMA2, "__init__.py"), encoding="utf-8").read()
        block = re.search(r'_add\("dnd_level".*?\]\)\)', source, re.S).group(0)
        self.assertEqual(re.findall(r'_\("([^"]+)"\)', block), ["Normal priority", "Normal and high priority"])
        self.assertEqual(self.c.dnd_level.choices, ["normal", "high"])


if __name__ == "__main__":
    unittest.main()
