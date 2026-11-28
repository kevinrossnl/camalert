"""camalert_core.keymap: the remote-key map of every player (#42), colour keys and the button event."""
import json
import sys
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
        # Kodi and Android TV: live bar; MENU(/INFO) = PTZ in the window on Kodi; on Android TV MENU opens the
        # action menu, a screen only Android TV has (Fire TV remotes have no colour keys, #64, #118)
        allowed = {("live", "kodi"), ("window", "kodi"), ("live", "androidtv"), ("window", "androidtv"),
                   ("actions", "androidtv")}
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
        self.assertEqual(keymap.action_for("androidtv", "window", "MENU"), "menu")
        self.assertEqual(keymap.action_for("androidtv", "live", "MENU"), "menu")
        self.assertEqual(keymap.action_for("androidtv", "actions", "MENU"), "close")
        self.assertEqual(keymap.action_for("androidtv", "actions", "OK"), "choose")

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

    def test_action_menu(self):
        """#118: the action menu offers exactly what the colour keys would do (colour_action), plus camera control."""
        self.assertEqual(keymap.action_menu(), [("button", c) for c in keymap.COLOURS])
        self.assertEqual(keymap.action_menu(True, "blue"),
                         [("ptz", None), ("button", "red"), ("button", "green"), ("button", "yellow")])
        self.assertEqual(keymap.action_menu(True, "off"), [("ptz", None)] + [("button", c) for c in keymap.COLOURS])
        self.assertEqual(keymap.action_menu(True, "blue", ha_buttons=False), [("ptz", None)])
        self.assertEqual(keymap.action_menu(False, ha_buttons=False), [])
        for has_ptz in (False, True):
            for key in keymap.PTZ_TOGGLE_KEYS:
                for on in (False, True):
                    sent = [c for kind, c in keymap.action_menu(has_ptz, key, on) if kind == "button"]
                    self.assertEqual(sent, [c for c in keymap.COLOURS if keymap.colour_action(c, key, has_ptz, on) == c])

    def test_button_event(self):
        d = json.loads(keymap.button_event("node1", "garden", "red"))
        self.assertEqual(d, {"event_type": "red", "button": "red", "camera": "garden", "receiver": "node1"})
        self.assertEqual(json.loads(keymap.button_event("n", None, "blue"))["camera"], "")


if __name__ == "__main__":
    unittest.main()


class TestSignedButtons(unittest.TestCase):
    """#82: colour keys to the Home Assistant webhook carry ts, nonce and an HMAC; MQTT payloads never do."""
    SECRET = "ab" * 32

    def test_unsigned_payload_unchanged(self):
        self.assertEqual(json.loads(keymap.button_event("node1", "gate", "green")),
                         {"event_type": "green", "button": "green", "camera": "gate", "receiver": "node1"})

    def test_signed_payload(self):
        d = json.loads(keymap.button_event("node1", "gate", "green", self.SECRET, now=1700000000, nonce="0f" * 16))
        self.assertEqual((d["ts"], d["nonce"]), (1700000000, "0f" * 16))
        # fixed vector: the Kotlin port (MqttTopics.buttonSignature) and the integration must give the same value
        self.assertEqual(d["sig"], keymap.button_signature(self.SECRET, "node1", "gate", "green", 1700000000, "0f" * 16))
        self.assertEqual(d["sig"], "9475c980198548186a1f9043e69695c6726fdaa8a541b2217a0815ea4c35370e")  # also in Kotlin

    def test_nonce_is_fresh(self):
        a = json.loads(keymap.button_event("n", "c", "red", self.SECRET))
        b = json.loads(keymap.button_event("n", "c", "red", self.SECRET))
        self.assertNotEqual(a["nonce"], b["nonce"])
        self.assertRegex(a["nonce"], r"^[0-9a-f]{32}$")

    def test_integration_checks_the_same_signature(self):
        sys.path.insert(0, _paths.HA)
        try:
            import signing  # custom_components/camalert/signing.py: stdlib only
        finally:
            sys.path.remove(_paths.HA)
        d = json.loads(keymap.button_event("node1", "gate", "green", self.SECRET, now=1700000000, nonce="0f" * 16))
        self.assertEqual(signing.signature(self.SECRET, "node1", "gate", "green", 1700000000, "0f" * 16), d["sig"])
        g = signing.ButtonGuard(self.SECRET, clock=lambda: 1700000010)
        self.assertIsNone(g.check(d))
        self.assertEqual(g.check(d), "used twice")
        self.assertEqual(signing.ButtonGuard(self.SECRET, clock=lambda: 1700000500).check(d), "too old")
        self.assertEqual(signing.ButtonGuard("cd" * 32, clock=lambda: 1700000010).check(d), "wrong signature")
        self.assertEqual(g.check({"button": "green"}), "not signed")
