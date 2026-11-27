"""camalert_core.urls: server addresses, stream and snapshot URLs."""
import unittest

import _paths

_paths.core()
from camalert_core import urls  # noqa: E402


class TestUrls(unittest.TestCase):
    def test_normalize_server(self):
        self.assertEqual(urls.normalize_server("192.168.1.10"), "http://192.168.1.10:1984")
        self.assertEqual(urls.normalize_server("http://cam.local:1984/"), "http://cam.local:1984")
        self.assertEqual(urls.normalize_server("https://go2rtc.example"), "https://go2rtc.example:443")
        self.assertIsNone(urls.normalize_server(""))
        self.assertIsNone(urls.normalize_server("ftp://x"))

    def test_go2rtc_state(self):
        """#73: no default address; empty = not set (nothing is contacted), garbage = invalid."""
        for value in ("", "  ", None):
            self.assertEqual(urls.go2rtc_state(value), "not_set")
        self.assertEqual(urls.go2rtc_state("ftp://x"), "invalid")
        self.assertEqual(urls.go2rtc_state("http://:1984"), "invalid")
        self.assertEqual(urls.go2rtc_state("192.168.1.10"), "ok")
        self.assertEqual(set(urls.GO2RTC_STATES), {"not_set", "invalid", "ok"})

    def test_derived_streams_are_not_cameras(self):
        """#117: a stream whose only source transcodes another stream of the same go2rtc (ffmpeg:<stream>#...) is a
        helper (Keep cameras ready, live substream), not a camera, on every player whatever its own settings."""
        streams = {
            "front_door": {"producers": [{"url": "rtsp://192.168.1.10:7447/abc"}]},
            "front_door_jpeg": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg#width=640#raw=-r 2"}]},
            "garden": {"producers": [{"url": "ffmpeg:rtsp://192.168.1.11/stream1#video=h264"}]},  # own source
            "garden_sub": {"producers": [{"url": "ffmpeg:garden#video=h264#width=640"}]},
            "mixed": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg"}, {"url": "rtsp://192.168.1.12/x"}]},
            "orphan": {"producers": [{"url": "ffmpeg:gone#video=mjpeg"}]},  # source is not a stream here
            "empty": {},
        }
        import json
        text = json.dumps(streams)
        self.assertEqual(urls.derived_streams(streams), {"front_door_jpeg", "garden_sub"})
        self.assertEqual(urls.streams_from_json(text), ["empty", "front_door", "garden", "mixed", "orphan"])
        self.assertEqual(urls.streams_from_json(text, all_streams=True),
                         ["empty", "front_door", "front_door_jpeg", "garden", "garden_sub", "mixed", "orphan"])
        self.assertEqual(urls.derived_streams({"a": {"producers": "x"}, "b": None}), set())

    def test_composite_streams(self):
        """#125: a stream that puts other streams of the same go2rtc together (an own mosaic) stays a camera, but is
        left out of the default mosaic, tour and overview lists."""
        mix = ("exec:ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/front_door "
               "-rtsp_transport tcp -i rtsp://127.0.0.1:8554/garden -rtsp_transport tcp -i rtsp://127.0.0.1:8554/garage "
               "-rtsp_transport tcp -i rtsp://127.0.0.1:8554/side -filter_complex [0:v]fps=10,scale=960:540[v0];"
               "[1:v]fps=10[v1];[v0][v1]xstack=inputs=2 -c:v libx264 -f rtsp {output}")
        cam = {"producers": [{"url": "rtsp://192.168.1.10:7447/abc"}]}
        streams = {
            "front_door": cam, "garden": cam, "garage": cam, "side": cam,
            "all_cameras": {"producers": [{"url": mix}]},
            "one_input": {"producers": [{"url": "exec:ffmpeg -i rtsp://127.0.0.1:8554/garden -c:v copy -f rtsp {output}"}]},
            "lan_mix": {"producers": [{"url": "exec:ffmpeg -i rtsp://192.168.1.10/a -i rtsp://192.168.1.11/b "
                                              "-filter_complex hstack -f rtsp {output}"}]},
            "half_known": {"producers": [{"url": "exec:ffmpeg -i rtsp://127.0.0.1:8554/garden "
                                                 "-i rtsp://127.0.0.1:8554/gone -filter_complex hstack {output}"}]},
            "two_producers": {"producers": [{"url": "ffmpeg:garden#video=h264"}, {"url": "ffmpeg:side#video=h264"}]},
        }
        self.assertEqual(urls.composite_streams(streams), {"all_cameras"})
        self.assertEqual(urls.composite_streams(None), set())
        import json
        names, composites = urls.stream_info_from_json(json.dumps(streams))
        self.assertIn("all_cameras", names)  # still a camera: show, default camera
        self.assertEqual(composites, {"all_cameras"})
        self.assertNotIn("all_cameras", urls.overview_cameras(names, composites))
        self.assertEqual(urls.overview_cameras(["a", "b"], None), ["a", "b"])
        self.assertEqual(urls.stream_info_from_json("not json"), ([], set()))

    def test_derived_stream_while_running(self):
        """#117 seen on a real go2rtc 1.9.15: while a derived stream runs, its producer url is go2rtc's own RTSP
        server with the original source in the query, not ``ffmpeg:<stream>#...``."""
        running = "rtsp://127.0.0.1:8554/front_door?video&source=ffmpeg:front_door%23video%3Dmjpeg%23width%3D640"
        streams = {
            "front_door": {"producers": [{"url": "rtsp://192.168.1.10:7447/abc", "format_name": "rtsp"}]},
            "front_door_jpeg": {"producers": [{"url": running, "format_name": "mjpeg", "protocol": "pipe"}]},
            "loop_sub": {"producers": [{"url": "rtsp://localhost:8554/front_door?video"}]},
            "elsewhere": {"producers": [{"url": "rtsp://127.0.0.1:8554/not_here?video"}]},  # no such stream here
            "lan": {"producers": [{"url": "rtsp://192.168.1.10:8554/front_door"}]},  # another host: a camera
        }
        self.assertEqual(urls.derived_streams(streams), {"front_door_jpeg", "loop_sub"})

    def test_streams_from_json(self):
        self.assertEqual(urls.streams_from_json('{"garden": {}, "front_door": {}, "bad name": {}}'), ["front_door", "garden"])
        self.assertEqual(urls.streams_from_json("not json"), [])
        self.assertEqual(urls.streams_from_json("[]"), [])

    def test_valid_port(self):
        self.assertEqual(urls.valid_port("8554", 1), 8554)
        self.assertEqual(urls.valid_port(0, 8099), 8099)
        self.assertEqual(urls.valid_port("x", 1883), 1883)
        self.assertEqual(urls.valid_port(70000, 1883), 1883)
        self.assertEqual(urls.valid_port(float("inf"), 1883), 1883)  # found by the property tests (#34)

    def test_ipv6_servers(self):
        self.assertEqual(urls.normalize_server("fd00::10"), "http://[fd00::10]:1984")
        self.assertEqual(urls.normalize_server("[fd00::10]:1985"), "http://[fd00::10]:1985")
        self.assertEqual(urls.normalize_server("https://[2001:db8::1]"), "https://[2001:db8::1]:443")
        self.assertIsNone(urls.normalize_server("http://host:99999"))
        self.assertEqual(urls.rtsp_url("http://[fd00::10]:1984", "garden"), "rtspt://[fd00::10]:8554/garden")
        self.assertEqual(urls.snapshot_url("http://[fd00::10]:1984", "garden"),
                         "http://[fd00::10]:1984/api/frame.jpeg?src=garden&width=640")

    def test_split_credentials(self):
        self.assertEqual(urls.split_credentials("http://admin:" + "p%40ss@cam:8080/snap.jpg?x=1"),
                         ("http://cam:8080/snap.jpg?x=1", "admin", "p@ss"))
        self.assertEqual(urls.split_credentials("http://cam/snap.jpg"), ("http://cam/snap.jpg", None, None))


if __name__ == "__main__":
    unittest.main()
