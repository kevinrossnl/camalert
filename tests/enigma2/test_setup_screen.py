"""Enigma2 settings screen (#40, #130): basic settings and one screen per section, hidden what is off, BLUE for expert settings, HELP key,
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

    def test_asks_for_the_go2rtc_address(self):
        """#73: no default address; the setup starts on the go2rtc address and its help line says it is not set."""
        self.c.server.value = ""
        self.c.wizard_done.value = True  # wizard skipped (#120): the settings open
        s = self.open()
        for fn in s.onLayoutFinish:
            fn()
        i = s["config"].getCurrentIndex()
        self.assertIs(s["config"].list[i][1], self.c.server)
        self.assertTrue(s["description"].text.startswith("go2rtc address not set. Address of your go2rtc server"),
                        s["description"].text)
        self.c.server.value = "ftp://x"
        s = self.open()
        self.assertTrue(any(t.startswith("No valid go2rtc address. ") for t in s.help_texts))

    def test_configured_address_is_not_asked_for(self):
        s = self.open()
        for fn in s.onLayoutFinish:
            fn()
        self.assertEqual(s["config"].getCurrentIndex(), 0)
        self.assertFalse([t for t in s.help_texts if "not set" in t])

    def section(self, first, name):
        first.open_section(name)
        return self.session.opened[-1]

    def test_first_screen_basic_settings_then_sections(self):
        """#130: basic settings, then one line per section (in schema order) with a summary."""
        s = self.open()
        labels = self.labels(s)
        self.assertEqual(labels[:4], ["Enable CamAlert", "Cameras via", "go2rtc address", "Default camera"])
        sections = ["General", "Display", "Rules", "Triggers", "Camera control", "Home Assistant", "API",
                    "Channel list", "Log and diagnostics"]
        self.assertEqual(labels[-len(sections):], sections)
        self.assertLessEqual(len(labels), 20)
        self.assertEqual(s.help_texts[0], "Turn the HTTP API and the camera display on or off.")
        values = self.ca.setup.values
        self.assertEqual(s.summary("log", values(self.c)), "default")
        self.c.foscam_enabled.value = True
        self.c.tour_interval.value = 12
        self.assertEqual(s.summary("triggers", values(self.c)), "Foscam motion and sound alarms")
        self.assertEqual(s.summary("display", values(self.c)), "1 changed")

    def test_section_screen_and_ok(self):
        s = self.open()
        rows = self.labels(s)
        s["config"].setCurrentIndex(rows.index("Display"))
        s.ok()
        d = self.session.opened[-1]
        self.assertEqual((d.title, d.section), ("CamAlert - Display", "display"))
        self.assertNotIn("Window position", self.labels(d))  # basic: on the first screen
        self.assertEqual(d["key_green"].text, "OK")

    def test_hide_what_is_off(self):
        """#130: Foscam, UniFi Protect, MQTT and Frigate show their fields only while they are on."""
        s = self.open()
        trig = self.section(s, "triggers")
        self.assertEqual(self.labels(trig), ["   Foscam", "Foscam motion and sound alarms", "   UniFi Protect",
                                             "UniFi Protect events"])
        self.c.foscam_enabled.value = self.c.unifi_enabled.value = True
        trig.build()
        labels = self.labels(trig)
        self.assertGreater(len(labels), 8)
        self.assertNotIn("   Frigate", labels)  # Frigate needs MQTT (Home Assistant section)
        self.c.mqtt_enabled.value = self.c.frigate_enabled.value = True
        trig.build()
        labels = self.labels(trig)
        self.assertEqual(labels[0], "   Frigate")
        self.assertTrue(all(l != "   Frigate" for l in labels[labels.index("   Foscam"):]))
        ha = self.section(s, "home_assistant")
        self.assertIn("MQTT broker", " ".join(self.labels(ha)))

    def test_more_settings_with_blue(self):
        """#130: expert settings only after BLUE; the choice is kept."""
        s = self.open()
        log = self.section(s, "log")
        self.assertNotIn("Remote syslog (host:port)", self.labels(log))
        self.assertEqual(log["key_blue"].text, "More settings")
        self.assertIn("more settings with BLUE", log["footnote"].text)
        log.toggle_expert()
        self.assertIn("Remote syslog (host:port)", self.labels(log))
        self.assertEqual((log["key_blue"].text, self.c.all_settings.saved_value), ("Fewer settings", True))
        again = self.section(self.open(), "log")
        self.assertIn("Remote syslog (host:port)", self.labels(again))

    def test_section_cancel_and_ok(self):
        """RED in a section undoes only that section; GREEN keeps the values for Save on the first screen."""
        s = self.open()
        disp = self.section(s, "display")
        self.c.tour_interval.value = 20
        self.c.duration.value = 90  # on the first screen
        disp.cancel()
        self.assertEqual((self.c.tour_interval.value, self.c.duration.value), (8, 90))
        disp = self.section(s, "display")
        self.c.tour_interval.value = 20
        disp.save()
        self.assertEqual((self.c.tour_interval.value, self.c.tour_interval.saved_value), (20, None))
        s.save()
        self.assertEqual(self.c.tour_interval.saved_value, 20)

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
