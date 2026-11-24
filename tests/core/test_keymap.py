"""camalert_core.keymap: colour keys and the button event."""
import json
import unittest

import _paths

_paths.core()
from camalert_core import keymap  # noqa: E402

RED, GREEN, YELLOW, BLUE = 398, 399, 400, 401


class TestKeymap(unittest.TestCase):
    def test_colour_keys(self):
        self.assertEqual(keymap.button_for(YELLOW, "yellow", has_ptz=True), "ptz")
        self.assertEqual(keymap.button_for(YELLOW, "yellow", has_ptz=False), "yellow")
        self.assertEqual(keymap.button_for(BLUE, "blue", has_ptz=True), "ptz")
        self.assertEqual(keymap.button_for(RED, "blue", has_ptz=True), "red")
        self.assertIsNone(keymap.button_for(RED, "blue", enabled=False))
        self.assertIsNone(keymap.button_for(352))

    def test_button_event(self):
        d = json.loads(keymap.button_event("node1", "garden", "red"))
        self.assertEqual(d, {"event_type": "red", "button": "red", "camera": "garden", "receiver": "node1"})
        self.assertEqual(json.loads(keymap.button_event("n", None, "blue"))["camera"], "")


if __name__ == "__main__":
    unittest.main()
