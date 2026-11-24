"""Remote keys on Enigma2 in PTZ mode (#42): only EXIT and the configured PTZ key leave PTZ mode."""
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class TestPtzKeys(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        session = self.env.Session()
        self.env.InfoBar(session)
        self.env.camalert.plugin.sessionstart(0, session=session)
        self.ctl = self.env.camalert.display.Controller.instance
        self.ctl.ptz_stream = "garden"
        self.moves = []
        self.ctl.ptz_move = lambda action, name=None: self.moves.append(action)
        self.hook = self.env.camalert.display.GlobalKeys()
        self.keys = self.env.camalert.keys

    def tearDown(self):
        self.hook.remove()
        e2fake.uninstall()

    def press(self, name):
        self.env.reactor.calls[:] = []
        handled = self.hook.key(self.keys.CODES[name], 0)
        later = [c.fn.__name__ for c in self.env.reactor.calls]
        return handled, later

    def test_yellow_does_not_leave_ptz_mode_when_blue_is_the_ptz_key(self):
        self.env.config.plugins.camalert.ptz_key.value = "blue"
        self.assertEqual(self.press("YELLOW"), (1, []))       # swallowed, nothing happens
        self.assertEqual(self.press("BLUE"), (1, ["leave_ptz"]))

    def test_yellow_leaves_when_it_is_the_ptz_key(self):
        self.env.config.plugins.camalert.ptz_key.value = "yellow"
        self.assertEqual(self.press("YELLOW"), (1, ["leave_ptz"]))

    def test_exit_arrows_and_volume(self):
        self.assertEqual(self.press("EXIT"), (1, ["leave_ptz"]))
        self.assertEqual(self.press("UP")[0], 1)
        self.assertEqual(self.moves, ["up"])
        self.assertEqual(self.press("VOLUME_UP"), (0, []))   # volume passes


if __name__ == "__main__":
    unittest.main()
