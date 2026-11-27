"""#73: no default go2rtc address on Enigma2. Not set (or invalid) = no network call, diagnostics say why."""
import unittest

import _paths  # noqa: F401
from enigma2.test_ui_findings import Base
from fakes.go2rtc import FakeGo2rtc


class TestGo2rtcNotSet(Base):
    def go2rtc_lines(self):
        return [l for l in self.ca.diagnostics.collect() if "go2rtc" in l]

    def test_not_set(self):
        self.c.server.value = ""
        self.assertEqual(self.d.all_camera_names(), [])
        self.assertIsNone(self.d.camera_urls("garden"))
        lines = self.go2rtc_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("[FAIL]"), lines)
        self.assertIn("go2rtc address not set", lines[0])

    def test_invalid(self):
        self.c.server.value = "ftp://x"
        self.assertEqual(self.d.all_camera_names(), [])
        lines = self.go2rtc_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("No valid go2rtc address", lines[0])

    def test_set(self):
        fake = FakeGo2rtc().start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        self.c.server.value = fake.url
        lines = self.go2rtc_lines()
        self.assertTrue("OK" in lines[0][:6] and "go2rtc reachable (4 cameras" in lines[0], lines)
        self.assertFalse([l for l in lines if "not set" in l or "No valid" in l])

    def test_helper_stream_is_not_a_camera(self):
        """#113: the stream behind 'Keep cameras ready' stays out of the camera list (mosaic, channel list, API)."""
        from fakes.go2rtc import CAMERAS
        cams = dict(CAMERAS, front_door_jpeg=(0, 0, 0))
        fake = FakeGo2rtc(cameras=cams).start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        self.c.server.value = fake.url
        self.assertIn("front_door_jpeg", self.d.all_camera_names())
        self.c.ready_cameras.value = "front_door=front_door_jpeg"
        self.assertNotIn("front_door_jpeg", self.d.all_camera_names())
        self.assertEqual(len(self.d.all_camera_names()), len(CAMERAS))

    def test_direct_mode_needs_no_address(self):
        self.c.server.value = ""
        self.c.source.value = "direct"
        self.assertFalse([l for l in self.ca.diagnostics.collect() if "go2rtc address" in l])


if __name__ == "__main__":
    unittest.main()
