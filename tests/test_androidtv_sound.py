"""#88: on Android TV / Fire TV the camera never takes over the sound of what is playing underneath. Live view starts
muted (live_volume 0) and the player does not request audio focus, so the TV app keeps playing its own sound."""
import os
import re
import unittest

import _paths

_paths.core()
from camalert_core import schema  # noqa: E402

OVERLAY = os.path.join(_paths.ROOT, "players", "androidtv", "app", "src", "main", "kotlin", "org", "camalert", "tv",
                       "Overlay.kt")


class TestAndroidTvSound(unittest.TestCase):
    def test_live_view_starts_muted(self):
        self.assertEqual(schema.defaults("androidtv")["live_volume"], 0)
        self.assertEqual(schema.defaults("kodi")["live_volume"], 100)  # other players keep their own default

    def test_no_audio_focus(self):
        """setAudioAttributes(..., handleAudioFocus = true) would pause or duck the TV app underneath."""
        text = open(OVERLAY, encoding="utf-8").read()
        self.assertIn("ExoPlayer.Builder(ctx)", text)
        self.assertNotRegex(text, r"setAudioAttributes\s*\(")
        self.assertNotRegex(text, r"handleAudioFocus")
        self.assertNotRegex(text, r"requestAudioFocus")
        self.assertRegex(text, re.escape("p.volume = volume.coerceIn(0, 100) / 100f"))
