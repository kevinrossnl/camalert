"""#15 on Kodi: several go2rtc servers; camera names stay unique and URLs go to the server that has the camera."""
import unittest

import _paths
from fakes.go2rtc import FakeGo2rtc
from kodi import stubs as kodi_stubs


class TestKodiServers(unittest.TestCase):
    def setUp(self):
        self.store = kodi_stubs.install()
        _paths.kodi_package()
        self.sources = _paths.kodi_module("sources")
        self.kodiapi = _paths.kodi_module("kodiapi")

    def fake(self, cameras):
        f = FakeGo2rtc(cameras=cameras).start()
        self.addCleanup(f.server_close)
        self.addCleanup(f.shutdown)
        return f

    def test_two_servers(self):
        a = self.fake({"front_door": (0, 92, 140)})
        b = self.fake({"front_door": (0, 92, 140), "shed": (150, 100, 0)})
        self.store.clear()
        self.store.update({"server": a.url, "more_servers": b.url})
        s = self.kodiapi.settings()
        self.assertEqual(self.sources.all_camera_names(s), ["front_door", "s2.front_door", "shed"])
        self.assertTrue(self.sources.camera_urls("s2.front_door", s)[1].startswith(b.url + "/api/frame.jpeg?src=front_door"))
        self.assertTrue(self.sources.camera_urls("front_door", s)[1].startswith(a.url))
        self.assertTrue(self.sources.camera_urls("shed", s)[1].startswith(b.url))


if __name__ == "__main__":
    unittest.main()
