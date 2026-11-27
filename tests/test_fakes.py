"""Shared test fakes (#32): go2rtc error switches, colour-coded camera, Frigate, test media and the fixture anonymiser."""
import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

import _paths

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fakes"))
import camera  # noqa: E402
import frigate  # noqa: E402
import go2rtc  # noqa: E402

_paths.tools()
import check_images  # noqa: E402
import make_test_media  # noqa: E402
import record_fixture  # noqa: E402

_paths.core()
from camalert_core.triggers import frigate as core_frigate  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is optional
    Image = None


def get(url, timeout=5):
    return urllib.request.urlopen(url, timeout=timeout)


class TestGo2rtcSwitches(unittest.TestCase):
    def start(self, **kw):
        srv = go2rtc.FakeGo2rtc(**kw).start()
        self.addCleanup(srv.stop)
        return srv

    def test_fail_and_empty(self):
        srv = self.start(fail=True)
        with self.assertRaises(urllib.error.HTTPError) as e:
            get(srv.url + "/api/streams")
        self.assertEqual(e.exception.code, 500)
        srv.fail, srv.empty = False, True
        self.assertEqual(json.loads(get(srv.url + "/api/streams").read()), {})
        self.assertEqual(srv.requests, ["/api/streams", "/api/streams"])

    def test_hang_runs_into_the_client_timeout(self):
        srv = self.start(hang=True)
        with self.assertRaises((socket.timeout, urllib.error.URLError, OSError)):
            get(srv.url + "/api/streams", timeout=0.3)

    def test_latency(self):
        import time
        srv = self.start(latency=0.2)
        t = time.time()
        get(srv.url + "/api/streams").read()
        self.assertGreaterEqual(time.time() - t, 0.2)


class TestCamera(unittest.TestCase):
    def test_colour_frames_have_no_metadata(self):
        for fmt in ("png", None):
            ctype, data = camera.colour_frame(2, 320, fmt)
            self.assertIn(ctype, ("image/png", "image/jpeg"))
            self.assertEqual(check_images.metadata(data), [])

    @unittest.skipIf(Image is None, "Pillow not installed")
    def test_tiles_can_be_told_apart_by_colour(self):
        """A mosaic of camera frames: sampling each tile gives back the camera index (screenshot checks, #32)."""
        mosaic = Image.new("RGB", (640, 360))
        boxes = [(0, 0, 320, 180), (320, 0, 640, 180), (0, 180, 320, 360), (320, 180, 640, 360)]
        for i, box in enumerate(boxes, 1):
            for fmt in ("png", None):
                tile = Image.open(io.BytesIO(camera.colour_frame(i, 320, fmt)[1]))
                mosaic.paste(tile, box[:2])
                self.assertEqual(camera.tile_index(mosaic, box), i)
        self.assertIsNone(camera.colour_of((0, 0, 0)))

    def test_server_snapshot_and_foscam(self):
        srv = camera.start_camera(3)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        r = get(srv.url + "/snapshot.jpg?width=200")
        self.assertIn(r.headers["Content-Type"], ("image/png", "image/jpeg"))
        r.read()
        bad = get(srv.url + "/cgi-bin/CGIProxy.fcgi?cmd=ptzMoveUp&usr=admin&pwd=wrong").read()
        self.assertIn(b"<result>-2</result>", bad)
        get(srv.url + "/cgi-bin/CGIProxy.fcgi?cmd=ptzMoveUp&usr=admin&pwd=pa%7Css").read()
        self.assertEqual(srv.RequestHandlerClass.calls, ["snapshot", "ptzMoveUp"])
        self.assertEqual(camera.MockCamera.calls, [])  # each started camera records its own calls


class TestFrigate(unittest.TestCase):
    def test_sequence_matches_the_core_parser(self):
        seq = frigate.event_sequence("garden", "person", updates=2, sub_label="postman")
        types = [json.loads(p)["type"] for p in seq]
        self.assertEqual(types, ["new", "update", "update", "end"])
        parsed = [core_frigate.frigate_event(p) for p in seq]
        self.assertEqual([p and p["type"] for p in parsed], ["new", "update", "update", None])
        self.assertEqual(parsed[0]["camera"], "garden")
        self.assertEqual(parsed[0]["sub_label"], "postman")
        self.assertIsNone(core_frigate.frigate_event(frigate.event_sequence("garden", false_positive=True)[0]))

    def test_snapshot_api(self):
        srv = frigate.FakeFrigate().start()
        self.addCleanup(srv.stop)
        event_id = json.loads(frigate.event_sequence("driveway")[0])["after"]["id"]
        url = srv.url + "/api/events/%s/snapshot.jpg" % event_id
        data = get(url).read()
        self.assertEqual(check_images.metadata(data), [])
        with self.assertRaises(urllib.error.HTTPError):
            get(srv.url + "/api/events/%s/clip.mp4" % event_id)
        self.assertEqual(len(srv.requests), 2)


class TestTestMedia(unittest.TestCase):
    def test_make(self):
        with tempfile.TemporaryDirectory() as d:
            paths = make_test_media.make(d, count=3, width=160)
            self.assertEqual(len(paths), 3)
            for p in paths:
                with open(p, "rb") as f:
                    self.assertEqual(check_images.metadata(f.read()), [])


class TestAnonymiser(unittest.TestCase):
    STREAMS = json.dumps({
        "porch": {"producers": [{"url": "rtsp://admin" + ":hunter22@10.20.30.40:554/Streaming/Channels/101",
                                 "remote_addr": "[fe80::1234:5678]:554"}], "consumers": []},
        "carport": {"producers": [{"url": "ffmpeg:porch#video=mjpeg"},
                                  {"url": "http://nvr.home.lan:5000/api/carport?token=abcdef123456"}]},
    })

    def test_streams_answer(self):
        out = record_fixture.anonymise(self.STREAMS, streams=True)
        data = json.loads(out)
        self.assertIs(data["anonymised"], True)
        self.assertEqual(sorted(k for k in data if k != "anonymised"), ["cam1", "cam2"])
        for secret in ("hunter22", "10.20.30.40", "fe80::1234:5678", "nvr.home.lan", "abcdef123456", "porch",
                       "carport"):
            self.assertNotIn(secret, out)
        self.assertIn("192.0.2.10", out)
        self.assertIn("ffmpeg:cam2#video=mjpeg", out)  # names are replaced inside urls too
        self.assertEqual(record_fixture.leaks(out, deny=[]), [])

    def test_same_address_same_replacement_and_timestamps(self):
        a = record_fixture.Anonymiser()
        out = a.text("from 172.16.5.9 at 2025-03-01T08:12:44.123 (1740816764) and 172.16.5.9 again; doc 192.0.2.7")
        self.assertEqual(out.count("192.0.2.10"), 2)
        self.assertIn("192.0.2.7", out)  # documentation ranges stay
        self.assertIn(record_fixture.FIXED_ISO, out)
        self.assertIn(record_fixture.FIXED_EPOCH, out)

    def test_list_answer_is_wrapped(self):
        out = json.loads(record_fixture.anonymise('[{"camera": "porch"}]', names={"porch": "cam1"}))
        self.assertEqual(out, {"anonymised": True, "data": [{"camera": "cam1"}]})

    def test_refuses_to_write_what_still_leaks(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.json")
            with open(src, "w") as f:
                f.write('{"note": "%s"}' % ("-----BEGIN RSA " + "PRIVATE KEY-----"))
            out = os.path.join(d, "out.json")
            self.assertEqual(record_fixture.main([src, out, "--file"]), 1)
            self.assertFalse(os.path.exists(out))
            with open(src, "w") as f:
                f.write(self.STREAMS)
            self.assertEqual(record_fixture.main([src, out, "--file", "--streams"]), 0)
            self.assertTrue(json.load(open(out))["anonymised"])


if __name__ == "__main__":
    unittest.main()
