"""Enigma2 settings screen (#40): sections in schema order, basic/advanced from the image's setup level, HELP key,
title without key hints, BLUE Test asks before saving, Cancel undoes everything."""
import types
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class TestSetupScreen(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.ca = self.env.camalert
        self.schema = self.ca.camalert_core.schema
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.c = self.env.config.plugins.camalert
        self.c.server.value = "http://192.168.1.10:1984"
        self.ca.plugin.sessionstart(0, session=self.session)

    def tearDown(self):
        e2fake.uninstall()

    def open(self, level=None):
        if level is not None:
            self.env.config.usage = types.SimpleNamespace(setup_level=types.SimpleNamespace(index=level))
        self.ca.plugin.main(self.session)
        return self.session.opened[-1]

    def labels(self, screen):
        return [row[0] for row in screen["config"].list]

    def test_title_and_skin(self):
        s = self.open()
        self.assertEqual(s.title, "CamAlert")
        self.assertEqual(s.skinName, ["CamAlertSetup", "Setup"])
        self.assertTrue(s["footnote"].text.startswith("CamAlert 1."))
        self.assertIn("description", s)

    def test_sections_in_schema_order(self):
        s = self.open()
        heads = [l.strip("- ") for l in self.labels(s) if l.startswith("-- ")]
        self.assertEqual(heads, ["General", "Display", "Rules", "Triggers", "Camera control", "Home Assistant", "API",
                                 "Channel list", "Log and diagnostics"])
        self.assertEqual(self.labels(s)[:3], ["-- General --", "Enable CamAlert", "Cameras via"])
        self.assertEqual(s.help_texts[1], "Turn the HTTP API and the camera display on or off.")
        self.assertEqual(s.help_texts[0], "")

    def test_trigger_groups(self):
        self.c.mqtt_enabled.value = self.c.frigate_enabled.value = self.c.foscam_enabled.value = True
        s = self.open()
        labels = self.labels(s)
        triggers = labels[labels.index("-- Triggers --") + 1:labels.index("-- Camera control --")]
        self.assertEqual(triggers[0], "   Frigate")
        self.assertIn("   Foscam", triggers)
        self.assertTrue(all(l != "   Frigate" for l in triggers[triggers.index("   Foscam"):]))

    def test_levels(self):
        basic = {s.label for s in self.schema.SETTINGS if s.level == "basic"}
        simple = self.open(level=0)
        shown = [l for l in self.labels(simple) if not l.startswith("-- ")]
        self.assertTrue(set(shown) <= basic, set(shown) - basic)
        self.assertIn("more settings via MENU", simple["footnote"].text)
        simple.menu()
        self.assertEqual(type(self.session.opened[-1]).__name__, "ChoiceBox")
        simple.menu_chosen(("Show all settings", "all"))
        self.assertIn("Log level", self.labels(simple))
        expert = self.open(level=2)
        self.assertIn("Remote syslog (host:port)", self.labels(expert))
        middle = self.open(level=1)
        self.assertIn("Log level", self.labels(middle))
        self.assertNotIn("Remote syslog (host:port)", self.labels(middle))

    def test_help_key(self):
        s = self.open()
        texts = [h[3] for h in s.helpList]
        self.assertIn("Save and show the default camera", texts)
        self.assertIn("Close without saving", texts)
        tour = self.session.open(self.ca.display.TourScreen, [("garden", "Garden", "http://x/g.jpg")], 8)
        self.assertEqual(sorted({h[3] for h in tour.helpList}), ["close", "live", "other camera", "pause"])

    def test_blue_asks_before_saving(self):
        self.c.camera.value = "garden"
        s = self.open()
        self.c.duration.value = 60
        s.test()
        box = self.session.opened[-1]
        self.assertEqual(type(box).__name__, "MessageBox")
        self.assertEqual(self.c.duration.saved_value, None)  # nothing saved yet
        shown = []
        self.ca.display.Controller.instance.show = lambda *a: shown.append(a)
        s.test_confirmed(False)
        self.assertEqual((shown, self.c.duration.saved_value), ([], None))
        s.test_confirmed(True)
        self.assertEqual(self.c.duration.saved_value, 60)
        self.assertEqual(shown, [("garden", 15, "photo")])

    def test_cancel_undoes_everything(self):
        s = self.open()
        self.c.duration.value = 90
        for setting, camera, value in (("orientation", "garden", "flip"), ("refresh", "garden", "5")):
            s.map_setting, s.map_camera = setting, camera
            s.map_value_chosen(("x", value))
        self.c.titles.value = "garden=Back garden"
        self.c.mosaic.value = "garden"
        self.assertEqual(self.c.orientation.value, "garden=flip")
        s.cancel()
        self.assertEqual((self.c.duration.value, self.c.orientation.value, self.c.refresh.value, self.c.titles.value,
                          self.c.mosaic.value), (30, "", "", "", ""))


if __name__ == "__main__":
    unittest.main()
