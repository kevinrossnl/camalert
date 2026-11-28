"""#87: several photo windows at the same time, each with its own id; places from the configured corner."""
import unittest

import _paths

_paths.core()
from camalert_core import layout, windows  # noqa: E402
from camalert_core.mqtt.topics import mqtt_command, mqtt_hide  # noqa: E402


class TestWindowId(unittest.TestCase):
    def test_param(self):
        self.assertIsNone(windows.window_id_param(None))
        self.assertIsNone(windows.window_id_param("  "))
        self.assertEqual(windows.window_id_param(" doorbell "), "doorbell")
        self.assertEqual(windows.window_id_param("drive-way.2_x"), "drive-way.2_x")
        for bad in ("a b", "../x", "x" * 33, "ä", "a/b"):
            with self.assertRaises(ValueError):
                windows.window_id_param(bad)

    def test_max_windows(self):
        self.assertEqual([windows.max_windows(v) for v in (1, "3", 0, 9, None, "x")], [1, 3, 1, 3, 2, 2])

    def test_mqtt(self):
        self.assertEqual(mqtt_command('{"cam": "garden", "id": "door"}'), {"cam": "garden", "id": "door"})
        self.assertEqual(mqtt_command('{"cam": "garden", "id": "a b"}'), {"cam": "garden"})
        self.assertEqual(mqtt_command("garden"), {"cam": "garden"})
        self.assertEqual(mqtt_hide(b'{"id": "door"}'), "door")
        self.assertIsNone(mqtt_hide(b""))
        self.assertIsNone(mqtt_hide(b'{"id": 5}'))
        self.assertIsNone(mqtt_hide(b"{broken"))


class TestWindowSlots(unittest.TestCase):
    def test_places_extend_and_free(self):
        w = windows.WindowSlots(3)
        self.assertEqual(w.place("door"), (1, None, False))    # place 0 is always the normal window's
        self.assertEqual(w.place(""), (0, None, False))
        self.assertEqual(w.place("garden"), (2, None, False))
        self.assertEqual(w.place("door"), (1, None, True))     # same id: same place (extend or replace)
        self.assertEqual(w.place(""), (0, None, True))
        w.remove("door")
        self.assertEqual(w.place("drive"), (1, None, False))   # the free place is reused
        self.assertEqual(w.ids(), ["", "drive", "garden"])

    def test_full_evicts_oldest_id_window_of_lowest_priority(self):
        w = windows.WindowSlots(3)
        w.place("", "normal")                                  # the normal window never gives way
        w.place("bell", "high")
        w.place("a")
        self.assertEqual(w.place("b"), (2, "a", False))        # a: normal, below bell
        self.assertEqual(w.place("c", "alarm"), (2, "b", False))
        self.assertEqual(w.place("d", "alarm"), (1, "bell", False))  # bell (high) is now the lowest
        self.assertEqual(w.ids(), ["", "d", "c"])

    def test_one_window_is_the_old_behaviour(self):
        w = windows.WindowSlots(1)
        self.assertEqual(w.place(""), (0, None, False))
        self.assertEqual(w.place("door"), (0, None, True))     # no id windows: every id is the normal window
        self.assertEqual(w.ids(), [""])
        w.clear()
        self.assertEqual(w.ids(), [])


class TestSlotGeometry(unittest.TestCase):
    def test_slot_zero_is_unchanged(self):
        for pos in layout.POSITIONS:
            self.assertEqual(layout.window_geometry(pos, "medium", 1920, 1080),
                             layout.window_geometry(pos, "medium", 1920, 1080, slot=0))

    def test_stack_towards_the_centre(self):
        g = [layout.window_geometry("top_right", "medium", 1920, 1080, slot=s) for s in range(3)]
        self.assertEqual(g[0][:2], (1240, 40))
        self.assertEqual(g[1][:2], (1240, 456))               # below
        self.assertEqual(g[2][:2], (584, 40))                 # column full: next column inwards
        b = [layout.window_geometry("bottom_left", "small", 1280, 720, slot=s) for s in range(2)]
        self.assertEqual(b[1][0], b[0][0])
        self.assertLess(b[1][1], b[0][1])                    # bottom corners stack upwards

    def test_never_off_screen(self):
        for pos in layout.POSITIONS:
            for size in layout.SIZES:
                for slot in range(3):
                    x, y, w, h, t = layout.window_geometry(pos, size, 1280, 720, "large", "xlarge", slot)
                    self.assertTrue(0 <= x and x + w <= 1280 and 0 <= y and y + h + t <= 720, (pos, size, slot))


if __name__ == "__main__":
    unittest.main()
