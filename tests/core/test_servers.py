"""#15: several go2rtc servers. The setting `server` stays the main server (s1); `more_servers` adds others,
each `[prefix=]address`. Camera names stay unique and keep their old meaning on the main server."""
import unittest

import _paths

_paths.core()
from camalert_core import servers as S  # noqa: E402

A, B, C = "http://192.168.1.10:1984", "http://192.168.1.20:1984", "http://192.168.1.30:1984"


class TestServers(unittest.TestCase):
    def test_parse_more(self):
        entries, problems = S.parse_more("garden=192.168.1.20, 192.168.1.30:1984\nBad Prefix=192.168.1.40;"
                                         "s3=192.168.1.50, ftp://x, ")
        self.assertEqual(entries, [("garden", B), (None, C)])
        self.assertEqual(problems, ["bad prefix=192.168.1.40", "s3=192.168.1.50", "ftp://x"])
        self.assertEqual(S.parse_more(""), ([], []))
        self.assertEqual(S.parse_more("http://a.example:1984/?x=1"), ([(None, "http://a.example:1984")], []))

    def test_server_list(self):
        self.assertEqual(S.server_list("192.168.1.10", "garden=192.168.1.20, 192.168.1.30, 192.168.1.10, "
                                                       "garden=192.168.1.60"),
                         [S.Server("s1", A), S.Server("s2", B, "garden"), S.Server("s3", C)])
        self.assertEqual(S.server_list("", ""), [])
        self.assertEqual(S.server_list("", "192.168.1.20"), [S.Server("s1", B)])  # no main: the first one is s1
        self.assertFalse(S.multiple(S.server_list("192.168.1.10")))

    def test_combine_names_stay_unique(self):
        s1, s2, s3 = S.server_list("192.168.1.10", "garden=192.168.1.20, 192.168.1.30")
        names, comp, mapping = S.combine([
            (s1, ["front_door", "garage", "all"], {"all"}),
            (s2, ["front_door", "shed"], set()),
            (s3, ["garage", "drive"], set()),
        ])
        self.assertEqual(names, ["all", "drive", "front_door", "garage", "garden.front_door", "garden.shed",
                                 "s3.garage"])
        self.assertEqual(comp, {"all"})
        self.assertEqual(mapping["garden.shed"], (B, "shed"))
        self.assertEqual(mapping["s3.garage"], (C, "garage"))
        self.assertEqual(mapping["drive"], (C, "drive"))
        self.assertEqual(mapping["garage"], (A, "garage"))

    def test_resolve(self):
        servers = S.server_list("192.168.1.10", "garden=192.168.1.20, 192.168.1.30")
        self.assertEqual(S.resolve("front_door", servers), (A, "front_door"))  # as before #15
        self.assertEqual(S.resolve("garden.shed", servers), (B, "shed"))
        self.assertEqual(S.resolve("s3.garage", servers), (C, "garage"))
        self.assertEqual(S.resolve("s1.x", servers), (A, "s1.x"))  # the main server has no prefix
        self.assertEqual(S.resolve("cam.1", servers), (A, "cam.1"))  # a dot in a main-server stream name
        self.assertEqual(S.resolve("drive", servers, {"drive": (C, "drive")}), (C, "drive"))
        self.assertEqual(S.resolve("x", []), (None, "x"))
        self.assertEqual(S.resolve("drive", servers, {"drive": ("http://192.168.1.99:1984", "drive")}), (A, "drive"))
        self.assertEqual(S.resolve("drive", [], {"drive": (C, "drive")}), (None, "drive"))


    def test_name_for_stream(self):
        mapping = {"garage": (A, "garage"), "s3.garage": (C, "garage"), "garden.shed": (B, "shed")}
        self.assertEqual(S.name_for_stream("192.168.1.30", "garage", mapping), "s3.garage")
        self.assertEqual(S.name_for_stream("192.168.1.10", "garage", mapping), "garage")
        self.assertIsNone(S.name_for_stream("192.168.1.99", "garage", mapping))

    def test_warm_feeds_per_server(self):
        from camalert_core.warm import WarmFeeds
        started = []
        w = WarmFeeds(lambda url: None, start=lambda fn: started.append(fn))
        servers = S.server_list("192.168.1.10", "garden=192.168.1.20")
        w.update(A, "front_door=front_door_jpeg, garden.shed=garden.shed_jpeg", True,
                 lambda n: S.resolve(n, servers))
        self.assertEqual(w.urls, {"front_door": A + "/api/stream.mjpeg?src=front_door_jpeg",
                                  "garden.shed": B + "/api/stream.mjpeg?src=shed_jpeg"})
        w.stop()


if __name__ == "__main__":
    unittest.main()
