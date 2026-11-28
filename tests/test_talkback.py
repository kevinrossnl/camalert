"""tools/talkback.py (#98): the go2rtc talk stream line and the read-only Protect lookup."""
import io
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "core"))
import talkback  # noqa: E402
from camalert_core import urls  # noqa: E402


class FakeOpener:
    def __init__(self, cams):
        self.cams, self.seen = cams, []

    def open(self, req, timeout=None):
        self.seen.append((req.get_method(), req.full_url))
        if req.full_url.endswith("/api/auth/login"):
            r = io.BytesIO(b"{}")
            r.headers = {"X-CSRF-Token": "t"}
            return r
        return io.BytesIO(json.dumps(self.cams).encode())


class TestTalkback(unittest.TestCase):
    def test_stream_line_is_a_talk_stream(self):
        line = talkback.stream_line("front_door", "192.168.1.14")
        name, url = line.strip().split(": ", 1)
        self.assertEqual(name, "front_door_talk")
        url = url.strip('"')
        self.assertIn("udp://192.168.1.14:7004#backchannel=1#audio=alaw/8000", url)
        self.assertIn("-ar 22050 -ac 1 -f adts", url)
        streams = {"front_door": {"producers": [{"url": "rtsp://192.168.1.10/x"}]},
                   "front_door_talk": {"producers": [{"url": url}]}}
        self.assertEqual(urls.talk_streams(streams), {"front_door": "front_door_talk"})
        self.assertIn("front_door_talk", urls.derived_streams(streams))
        for bad in (("front door", "192.168.1.14"), ("x", "1.2.3.4; rm -rf /"), ("x", "")):
            with self.assertRaises(ValueError):
                talkback.stream_line(*bad)
        with self.assertRaises(ValueError):
            talkback.stream_line("x", "192.168.1.14", port=70000)

    def test_protect_lookup_is_read_only(self):
        cams = [{"name": "Front", "host": "192.168.1.14", "featureFlags": {"hasSpeaker": True},
                 "talkbackSettings": {"typeFmt": "aac", "bindPort": 7004}},
                {"name": "Garden", "host": "192.168.1.15", "featureFlags": {"hasSpeaker": False}}]
        op = FakeOpener(cams)
        self.assertEqual(talkback.protect_speakers("https://192.168.1.1/", "u", "p", op),
                         [("Front", "192.168.1.14", {"typeFmt": "aac", "bindPort": 7004})])
        self.assertEqual(op.seen, [("POST", "https://192.168.1.1/api/auth/login"),
                                   ("GET", "https://192.168.1.1/proxy/protect/api/cameras")])


if __name__ == "__main__":
    unittest.main()
