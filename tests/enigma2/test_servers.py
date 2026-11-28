"""#15: several go2rtc servers on Enigma2. The main server keeps its camera names; another server's cameras get
its prefix (or s<n>. when a name is taken), and every URL goes to the server that has the camera."""
import unittest

import _paths  # noqa: F401
from enigma2.test_ui_findings import Base
from fakes.go2rtc import FakeGo2rtc


class TestServers(Base):
    def fake(self, cameras):
        f = FakeGo2rtc(cameras=cameras).start()
        self.addCleanup(f.server_close)
        self.addCleanup(f.shutdown)
        return f

    def test_two_servers(self):
        a = self.fake({"front_door": (0, 92, 140), "garden": (0, 110, 80)})
        b = self.fake({"garden": (0, 110, 80), "shed": (150, 100, 0)})
        c = self.fake({"drive": (120, 60, 100)})
        self.c.server.value = a.url
        self.c.more_servers.value = "back=%s, %s" % (b.url, c.url)
        names = self.d.all_camera_names()
        self.assertEqual(names, ["back.garden", "back.shed", "drive", "front_door", "garden"])
        live, snap, _title = self.d.camera_urls("back.shed")
        self.assertTrue(snap.startswith(b.url + "/api/frame.jpeg?src=shed"), snap)
        self.assertIn("/shed", live)
        self.assertTrue(self.d.camera_urls("drive")[1].startswith(c.url), "a server without prefix")
        self.assertTrue(self.d.camera_urls("garden")[1].startswith(a.url), "the main server wins a name")

    def test_one_server_down_keeps_the_others(self):
        a = self.fake({"front_door": (0, 92, 140)})
        self.c.server.value = a.url
        self.c.more_servers.value = "back=http://127.0.0.1:9"  # nothing listens there
        self.assertEqual(self.d.all_camera_names(), ["front_door"])

    def test_single_server_unchanged(self):
        a = self.fake({"front_door": (0, 92, 140)})
        self.c.server.value = a.url
        self.c.more_servers.value = ""
        self.assertEqual(self.d.all_camera_names(), ["front_door"])
        self.assertTrue(self.d.camera_urls("front_door")[1].startswith(a.url))

    def test_channel_list_per_server(self):
        a = self.fake({"front_door": (0, 92, 140)})
        b = self.fake({"shed": (150, 100, 0)})
        self.c.server.value = a.url
        self.c.more_servers.value = "back=%s" % b.url
        text = self.ca.bouquet.build(self.d.all_camera_names())
        self.assertIn("/shed:Back.shed", text)  # the stream name on its own server, the camera name in the list
        self.assertIn("/front_door:", text)


if __name__ == "__main__":
    unittest.main()
