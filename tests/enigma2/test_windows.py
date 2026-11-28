"""#87: several photo windows at once on Enigma2, each with its own id; without an id nothing changes."""
import time
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class TestWindows(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openpli")
        self.d = self.env.camalert.display
        self.c = self.env.config.plugins.camalert
        self.c.server.value = "http://192.168.1.10:1984"
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.env.camalert.plugin.sessionstart(0, session=self.session)
        self.ctl = self.d.Controller.instance
        self.ctl._names, self.ctl._names_at = ["front_door", "garden", "garage"], time.time()

    def tearDown(self):
        e2fake.uninstall()

    def open_windows(self):
        return [s for s in self.session.dialogs if isinstance(s, self.d.PhotoWindow) and s not in self.session.closed]

    def test_default_and_id_windows(self):
        self.assertEqual(self.ctl.show("front_door", 30, "photo", "high"), "show")
        self.assertEqual(self.ctl.show("garden", 30, "photo", "high", window_id="drive"), "show")
        self.assertEqual(len(self.open_windows()), 2)
        self.assertEqual(self.ctl.slots.slot(""), 0)
        self.assertEqual(self.ctl.slots.slot("drive"), 1)
        st = self.ctl.status()
        self.assertEqual(st["windows"], [{"id": "", "camera": "front_door"}, {"id": "drive", "camera": "garden"}])
        self.assertEqual(st["window"], "front_door")
        self.assertEqual(st["screen"], "photo")
        # the same id with the same camera extends, another camera replaces it in its place
        self.assertEqual(self.ctl.show("garden", 30, "photo", "high", window_id="drive"), "extend")
        self.assertEqual(self.ctl.show("garage", 30, "photo", "high", window_id="drive"), "show")
        self.assertEqual(self.ctl.extra["drive"].stream, "garage")
        self.assertEqual(self.ctl.slots.slot("drive"), 1)
        self.assertEqual(len(self.open_windows()), 2)
        # a normal request replaces only the normal window
        self.assertEqual(self.ctl.show("garden", 30, "photo", "high"), "show")
        self.assertEqual(self.ctl.window.stream, "garden")
        self.assertIn("drive", self.ctl.extra)

    def test_hide_by_id_and_hide_all(self):
        self.ctl.show("front_door", 30, "photo", "high")
        self.ctl.show("garden", 30, "photo", "high", window_id="drive")
        self.ctl.hide(window_id="nope")                    # unknown id: nothing
        self.assertEqual(len(self.open_windows()), 2)
        self.ctl.hide(window_id="drive")
        self.assertNotIn("drive", self.ctl.extra)
        self.assertIsNotNone(self.ctl.window)
        self.ctl.show("garden", 30, "photo", "high", window_id="drive")
        self.ctl.hide()
        self.assertEqual(self.open_windows(), [])
        self.assertEqual(self.ctl.slots.ids(), [])

    def test_full_replaces_oldest_lowest_priority_id_window(self):
        self.c.max_windows.value = 3
        self.ctl.show("front_door", 30, "photo", "normal")                # the normal window keeps the corner
        self.ctl.show("garden", 30, "photo", "high", window_id="a")
        self.ctl.show("garage", 30, "photo", "normal", window_id="b")
        self.ctl.show("front_door", 30, "photo", "alarm", window_id="c")  # full: "b" (normal) goes
        self.assertEqual(sorted(self.ctl.extra), ["a", "c"])
        self.assertEqual((self.ctl.slots.slot("a"), self.ctl.slots.slot("c")), (1, 2))
        self.assertEqual(self.ctl.window.stream, "front_door")
        self.assertEqual(len(self.open_windows()), 3)

    def test_one_window_setting_is_the_old_behaviour(self):
        self.c.max_windows.value = 1
        self.ctl.show("front_door", 30, "photo", "high")
        self.ctl.show("garden", 30, "photo", "high", window_id="drive")
        self.assertEqual(self.ctl.extra, {})
        self.assertEqual(self.ctl.window.stream, "garden")
        self.assertEqual(len(self.open_windows()), 1)

    def test_window_runs_out(self):
        self.ctl.show("garden", 30, "photo", "high", window_id="drive")
        w = self.ctl.extra["drive"]
        w.stop()
        self.assertEqual(self.ctl.extra, {})
        self.assertIsNone(self.ctl.slots.slot("drive"))

    def test_live_closes_id_windows(self):
        self.ctl.show("garden", 30, "photo", "high", window_id="drive")
        self.ctl.show("front_door", 30, "live", "high")
        self.assertEqual(self.ctl.extra, {})


if __name__ == "__main__":
    unittest.main()
