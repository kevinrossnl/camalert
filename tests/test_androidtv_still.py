"""#91: on Android TV / Fire TV live view shows a still picture at once until the first video frame. The rules
are the core LiveStill (Kotlin port tested in StillTest.kt); this checks the app wires them as intended: the
picture is fetched off the UI thread from the fast sources in order and hidden at the first rendered frame."""
import os
import re
import unittest

import _paths

OVERLAY = os.path.join(_paths.ROOT, "players", "androidtv", "app", "src", "main", "kotlin", "org", "camalert", "tv",
                       "Overlay.kt")


class TestAndroidTvStill(unittest.TestCase):
    def setUp(self):
        text = open(OVERLAY, encoding="utf-8").read()
        self.live = text[text.index("private inner class LiveWin"):text.index("private inner class MosaicWin")]

    def test_still_until_the_first_frame(self):
        self.assertIn("org.camalert.core.LiveStill()", self.live)
        first = self.live[self.live.index("override fun onRenderedFirstFrame"):]
        self.assertRegex(first[:300], r"if \(still\.playing\(\)\) stillView\?\.visibility = View\.GONE")
        self.assertIn("still.stop()", self.live[self.live.index("override fun detach"):])

    def test_picture_off_the_ui_thread_in_source_order(self):
        body = self.live[self.live.index("fun showStill"):self.live.index("override fun key")]
        self.assertIn("Thread({", body)
        order = [body.index(k) for k in ("host.warmPicture", "host.protectPicture", "Urls.withCache")]
        self.assertEqual(order, sorted(order))  # warm frame, Protect, go2rtc cache (frame.jpeg if go2rtc has none)
        self.assertRegex(body, re.escape("main.post {") + r"\s*if \(!stop\.get\(\) && still\.picture\(token\)\)")
        self.assertIn("stillMaxSeconds", body)

    def test_every_camera_change_starts_a_new_still(self):
        play = self.live[self.live.index("fun play(t: Tile)"):self.live.index("fun showStill")]
        self.assertIn("showStill(t)", play)


if __name__ == "__main__":
    unittest.main()
