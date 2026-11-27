"""#122 on Kodi: /camalert/setup saves the go2rtc address and camera and shows a notification."""
import unittest

import _paths  # noqa: F401
from contract.adapters import KodiAdapter, Request
from kodi import stubs as kodi_stubs


class TestKodiSetup(unittest.TestCase):
    def test_setup_is_saved_and_shown(self):
        a = KodiAdapter()
        del kodi_stubs.CALLS[:]
        ans = a.call(Request("/camalert/setup", {"server": "192.168.1.10:1984", "camera": "garden"}, method="POST"))
        self.assertEqual((ans.code, ans.body["server"]), (200, "http://192.168.1.10:1984"))
        self.assertEqual((a.store["server"], a.store["camera"]), ("http://192.168.1.10:1984", "garden"))
        shown = kodi_stubs.calls("xbmcgui.Dialog.notification")
        self.assertEqual(len(shown), 1)
        self.assertIn("Settings received from Home Assistant", repr(shown[0]))


if __name__ == "__main__":
    unittest.main()
