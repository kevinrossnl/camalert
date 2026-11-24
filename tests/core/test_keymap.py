"""camalert_core.keymap: the remote-key map of every player (#42), colour keys and the button event."""
import json
import unittest

import _paths

_paths.core()
from camalert_core import keymap  # noqa: E402


class TestKeymap(unittest.TestCase):
    def test_every_player_has_every_context(self):
        for player in keymap.PLAYERS:
            self.assertEqual(sorted(keymap.KEYMAP[player]), sorted(keymap.CONTEXTS), player)

    def test_one_action_per_key_and_context(self):
        for player, contexts in keymap.KEYMAP.items():
            for context, actions in contexts.items():
                seen = {}
                for action, keys in actions.items():
                    for k in keys:
                        self.assertNotIn(k, seen, "%s/%s: %s does %s and %s" % (player, context, k, seen.get(k), action))
                        seen[k] = action

    def test_same_logical_actions_on_every_player(self):
        """The UI guideline (#2): same actions everywhere; documented differences only."""
        # Kodi and Android TV: live bar; MENU(/INFO) = PTZ in the window (Fire TV remotes have no colour keys, #64)
        allowed = {("live", "kodi"), ("window", "kodi"), ("live", "androidtv"), ("window", "androidtv")}
        for context in keymap.CONTEXTS:
            sets = {p: set(keymap.KEYMAP[p][context]) - {"pass"} for p in keymap.PLAYERS}
            for p in keymap.PLAYERS:
                if (context, p) not in allowed:
                    self.assertEqual(sets[p], sets["enigma2"], (context, p))

    def test_lookup(self):
        self.assertEqual(keymap.action_for("enigma2", "window", "OK"), "live")
        self.assertIsNone(keymap.action_for("enigma2", "window", "RED"))
        self.assertIsNone(keymap.action_for("kodi", "ptz", None))
        self.assertEqual(keymap.keys_for("kodi", "tour", "live"), ("GREEN", "PLAY", "UP"))
        self.assertEqual(keymap.action_for("androidtv", "tour", "PLAY_PAUSE"), "live")
        self.assertEqual(keymap.action_for("androidtv", "window", "MENU"), "ptz")

    def test_tour_live_is_green_or_play_on_every_player(self):
        """UI guideline (#2): tour live = GREEN or PLAY on Enigma2 and Kodi."""
        for player in keymap.PLAYERS:
            self.assertEqual(keymap.keys_for(player, "tour", "live")[:2], ("GREEN", "PLAY"), player)

    def test_ptz_is_left_only_with_exit_back_or_the_ptz_key(self):
        """#42: YELLOW was always a leave key on Enigma2."""
        for player in keymap.PLAYERS:
            for colour in ("RED", "GREEN", "YELLOW", "BLUE"):
                self.assertIsNone(keymap.action_for(player, "ptz", colour), (player, colour))

    def test_colour_keys(self):
        self.assertEqual(keymap.colour_action("yellow", "yellow", has_ptz=True), "ptz")
        self.assertEqual(keymap.colour_action("yellow", "yellow", has_ptz=False), "yellow")
        self.assertEqual(keymap.colour_action("blue", "blue", has_ptz=True), "ptz")
        self.assertEqual(keymap.colour_action("red", "blue", has_ptz=True), "red")
        self.assertIsNone(keymap.colour_action("red", "blue", enabled=False))
        self.assertIsNone(keymap.colour_action(None))
        self.assertEqual(keymap.colour_action("blue", "off", has_ptz=True), "blue")

    def test_button_event(self):
        d = json.loads(keymap.button_event("node1", "garden", "red"))
        self.assertEqual(d, {"event_type": "red", "button": "red", "camera": "garden", "receiver": "node1"})
        self.assertEqual(json.loads(keymap.button_event("n", None, "blue"))["camera"], "")


if __name__ == "__main__":
    unittest.main()
