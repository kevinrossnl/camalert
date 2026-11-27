"""#48 text size and priority marking, #13 'Look at the door', #10 own language on Enigma2."""
import os
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

import _paths  # noqa: F401
from enigma2.harness import e2fake

CAMS = ["front_door", "garden"]


def widgets(screen):
    return {w.get("name"): w for w in ET.fromstring(screen.skin).iter("widget")}


def font(w):
    return int(w.get("font").split(";")[1])


class Base(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.ca = self.env.camalert
        self.d = self.ca.display
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.c = self.env.config.plugins.camalert
        self.c.server.value = "http://192.168.1.10:1984"
        self.c.camera.value = "front_door"
        self.ca.plugin.sessionstart(0, session=self.session)
        self.ctl = self.d.Controller.instance
        self.ctl._names, self.ctl._names_at = list(CAMS), time.time()

    def tearDown(self):
        self.ca.set_language("system")
        e2fake.uninstall()


class TestPriorityFrame(Base):
    def test_alarm_gets_a_vermillion_frame_and_the_word(self):
        self.assertEqual(self.ctl.show("garden", 10, "photo", "alarm"), "show")
        w = widgets(self.ctl.window)
        self.assertEqual({w["frame%d" % i].get("backgroundColor") for i in range(4)}, {"#D55E00"})
        self.assertTrue(self.ctl.window["title"].text.startswith("ALARM · "))

    def test_normal_and_off_have_no_frame(self):
        self.ctl.show("garden", 10, "photo", "normal")
        self.assertNotIn("frame0", widgets(self.ctl.window))
        self.ctl.hide()
        self.c.priority_border.value = "off"
        self.ctl.last_shown.clear()
        self.ctl.show("garden", 10, "photo", "high")
        self.assertNotIn("frame0", widgets(self.ctl.window))
        self.assertNotIn("Doorbell", self.ctl.window["title"].text)

    def test_flashing_frame(self):
        self.c.priority_border.value = "flash"
        self.ctl.show("garden", 10, "photo", "high")
        frame = self.ctl.window.frame
        self.assertTrue(frame.timer.active)
        self.assertEqual(frame.timer.interval, self.d.FLASH_MS)
        self.assertGreaterEqual(self.d.FLASH_MS, 167)  # at most 3 flashes per second (WCAG 2.3.1)
        window = self.ctl.window
        frame.toggle()
        self.assertFalse(window["frame0"].visible)
        self.ctl.hide()
        self.assertFalse(frame.timer.active)

    def test_multi_camera_window_is_marked_too(self):
        self.ctl.show("front_door,garden", 10, "photo", "high")
        self.assertEqual(widgets(self.ctl.window)["frame0"].get("backgroundColor"), "#E69F00")


class TestTextSize(Base):
    def fonts(self):
        self.ctl.last_shown.clear()
        self.ctl.show("garden", 10, "photo", "normal")
        w = widgets(self.ctl.window)
        out = font(w["title"]), int(ET.fromstring(self.ctl.window.skin).get("size").split(",")[1])
        self.ctl.hide()
        return out

    def test_text_size_scales_title_and_window(self):
        normal = self.fonts()
        self.c.text_size.value = "xlarge"
        big = self.fonts()
        self.assertGreater(big[0], normal[0])
        self.assertGreater(big[1], normal[1])  # the title bar grows with the text

    def test_other_screens_follow(self):
        self.c.text_size.value = "large"
        tour = self.d.TourScreen(self.session, [("garden", "Garden", "http://x/y")], 5)
        self.assertEqual(font(widgets(tour)["title"]), int(30 * 1.25))
        ptz = self.d.PtzOverlay(self.session, "PTZ")
        self.assertEqual(font(widgets(ptz)["text"]), 35)


class TestLookAtDoor(Base):
    def test_default_camera_without_chime_or_frame(self):
        rang = []
        self.ctl.chime = lambda: rang.append(1)
        self.c.chime.value = "all"
        self.c.dnd.value = True  # the viewer asked for it himself: do-not-disturb does not stop it
        descriptors = {d.name: d for d in self.ca.plugin.Plugins()}
        descriptors["CamAlert: default camera"].fnc(self.session)
        self.assertEqual(self.ctl.window.stream, "front_door")
        self.assertNotIn("frame0", widgets(self.ctl.window))
        self.assertEqual(rang, [])
        self.assertEqual(self.ctl.events[0]["source"], "menu")


class TestPreset(Base):
    def test_simple_preset(self):
        from importlib import import_module
        setup = import_module(self.ca.__name__ + ".setup")
        changes = setup.apply_preset(self.c, "simple")
        self.assertEqual(self.c.text_size.value, "xlarge")
        self.assertEqual(self.c.size.value, "large")
        self.assertEqual(int(self.c.duration.value), 60)
        self.assertEqual(self.c.ptz_key.value, "off")
        self.assertIn("chime", changes)
        self.assertEqual(setup.apply_preset(self.c, "simple"), {})  # nothing left to change


class TestLanguage(Base):
    def test_own_language_and_back(self):
        sys.path.insert(0, os.path.join(_paths.ROOT, "tools"))
        from msgfmt import make_mo, parse_po
        folder = tempfile.mkdtemp()
        os.makedirs(os.path.join(folder, "nl", "LC_MESSAGES"))
        with open(os.path.join(_paths.ROOT, "players", "enigma2", "po", "nl.po"), encoding="utf-8") as f:
            mo = make_mo(parse_po(f.read()))
        with open(os.path.join(folder, "nl", "LC_MESSAGES", "CamAlert.mo"), "wb") as f:
            f.write(mo)
        self.ca.set_language("nl", folder)
        self.assertEqual(self.ca._("Close"), "Sluiten")
        self.ca.set_language("en", folder)
        self.assertEqual(self.ca._("Close"), "Close")
        self.ca.set_language("system")
        self.assertIsNone(self.ca._LANGUAGE["catalogue"])

    def test_setting_changes_the_language(self):
        seen = []
        own = self.ca.set_language
        self.ca.set_language = lambda code, *a: seen.append(code)
        try:
            self.c.language.value = "de"
            self.ca._language_changed(self.c.language)
        finally:
            self.ca.set_language = own
        self.assertEqual(seen, ["de"])
        self.assertEqual(self.c.language.choices[0], "system")

if __name__ == "__main__":
    unittest.main()
