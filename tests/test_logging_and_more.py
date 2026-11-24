import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "CamAlert"))
import logic as L  # noqa: E402
import camlog  # noqa: E402


class TestRedact(unittest.TestCase):
    def test_redact(self):
        cases = {
            "rtsp://admin:password@10.0.0.5:554/s1": "rtsp://***:***@10.0.0.5:554/s1",
            "rtsp://admin:" + "s3cr3t@10.0.0.5/s1": "rtsp://***:***@10.0.0.5/s1",
            "http://tok3n@host/x": "http://***@host/x",
            "http://10.0.0.2:88/cgi-bin/CGIProxy.fcgi?cmd=getDevState&usr=admin&pwd=s3cr3t":
                "http://10.0.0.2:88/cgi-bin/CGIProxy.fcgi?cmd=getDevState&usr=***&pwd=***",
            "GET /camalert/show?cam=a&token=abc123": "GET /camalert/show?cam=a&token=***",
            "Authorization: Bearer eyJhbGciOi.x.y": "Authorization: ***",
            '{"token": "abc", "cam": "x"}': '{"token": "***", "cam": "x"}',
            "<Password Type=\"#PasswordDigest\">abc=</Password>": "<Password Type=\"#PasswordDigest\">***</Password>",
            "mqtt password=hunter2 user ok": "mqtt password=*** user ok",
            "camera garden shown": "camera garden shown",
        }
        for raw, want in cases.items():
            self.assertEqual(L.redact(raw), want)
        self.assertEqual(L.redact(None), "")

    def test_levels(self):
        self.assertTrue(L.log_allowed("errors", "error"))
        self.assertFalse(L.log_allowed("errors", "normal"))
        self.assertTrue(L.log_allowed("normal", "normal"))
        self.assertFalse(L.log_allowed("normal", "verbose"))
        self.assertTrue(L.log_allowed("verbose", "verbose"))
        self.assertFalse(L.log_allowed("off", "error"))

    def test_syslog(self):
        line = L.syslog_line("shown rtsp://a:b@h/x", "error", "my box", 1795464900.25)
        self.assertEqual(line, "<131>1 2026-11-23T20:15:00.250Z my_box camalert - - - shown rtsp://***:***@h/x")
        self.assertTrue(L.syslog_line("x", "normal", "h", 0).startswith("<134>1 "))
        self.assertEqual(L.parse_hostport("10.0.0.9:1514"), ("10.0.0.9", 1514))
        self.assertEqual(L.parse_hostport("loki.lan"), ("loki.lan", 514))
        self.assertIsNone(L.parse_hostport(""))

    def test_camlog_rotation_and_redaction(self):
        with tempfile.TemporaryDirectory() as d:
            log = camlog.CamLog(dirs=(d,), max_bytes=300)
            log.configure("normal")
            for i in range(20):
                log.write("normal", "line %d token=geheim%d" % (i, i))
            log.write("verbose", "not written")
            self.assertTrue(os.path.exists(os.path.join(d, "camalert.log.1")))
            text = open(os.path.join(d, "camalert.log")).read() + open(os.path.join(d, "camalert.log.1")).read()
            self.assertNotIn("geheim", text)
            self.assertNotIn("not written", text)
            self.assertLessEqual(os.path.getsize(os.path.join(d, "camalert.log")), 400)
            self.assertIn("line 19 token=***", log.tail(5)[-1])


class TestEventsButtonsUpdates(unittest.TestCase):
    def test_events(self):
        events = []
        for i in range(25):
            dropped = L.add_event(events, {"n": i}, limit=20)
        self.assertEqual(len(events), 20)
        self.assertEqual(events[0]["n"], 24)
        self.assertEqual(dropped, [{"n": 4}])
        self.assertEqual(L.caller_source("HomeAssistant/2026.11 aiohttp/3.12 Python/3.13"), "ha")
        self.assertEqual(L.caller_source("curl/8.5"), "api")
        self.assertEqual(L.event_title("Front door", "Person"), "Person · Front door")
        self.assertEqual(L.event_title("Front door", None), "Front door")
        line = L.event_line({"time": 0, "camera": "garden", "label": "Person", "source": "frigate", "priority": "normal",
                             "action": "show"})
        self.assertIn("garden · Person  (frigate, normal) -> show", line)
        self.assertEqual(L.diag_line(True, "pwd=x ok"), "[ OK ]  pwd=*** ok")
        self.assertEqual(L.diag_line(False, "x")[:6], "[FAIL]")

    def test_frigate_labels_and_clips(self):
        ev = L.frigate_event(json.dumps({"type": "new", "after": {"id": "1732.5-abc", "camera": "garden",
                                                                   "label": "person", "sub_label": ["Alice", 0.92],
                                                                   "has_clip": True}}))
        self.assertEqual(ev["sub_label"], "Alice")
        self.assertEqual(L.frigate_title(ev), "Alice")
        ev["sub_label"] = ""
        self.assertEqual(L.frigate_title(ev), "Person")
        self.assertEqual(L.frigate_clip_url("192.168.1.10:5000", "1732.5-abc"),
                         "http://192.168.1.10:5000/api/events/1732.5-abc/clip.mp4")
        self.assertIsNone(L.frigate_clip_url("http://f:5000", "../x"))
        self.assertIsNone(L.frigate_clip_url("", "1"))
        self.assertEqual(L.mqtt_command(b'{"cam": "a", "label": "Person"}')["label"], "Person")

    def test_buttons_discovery(self):
        msgs = dict(L.discovery("abc", "CamAlert test", [("garden", "Garden")]))
        conf = json.loads(msgs["homeassistant/event/camalert_abc/button/config"])
        self.assertEqual(conf["event_types"], ["red", "green", "yellow", "blue"])
        self.assertEqual(conf["state_topic"], "camalert/abc/button")
        self.assertEqual(json.loads(L.button_event("abc", "garden", "red")),
                         {"event_type": "red", "button": "red", "camera": "garden", "receiver": "abc"})

    def test_updates(self):
        self.assertEqual(L.newer_version("1.0.0", "v1.1.0"), "1.1.0")
        self.assertIsNone(L.newer_version("1.0.0", "v1.0.0"))
        self.assertIsNone(L.newer_version("1.2.0", "1.10.0") and None)
        self.assertEqual(L.newer_version("1.2.0", "1.10.0"), "1.10.0")
        self.assertIsNone(L.newer_version("1.0.0", None))
        self.assertEqual(L.github_repo("Package: x\nHomepage: https://github.com/someone/camalert\n"), "someone/camalert")
        self.assertIsNone(L.github_repo("Homepage: https://example.com/x"))
        self.assertEqual(L.latest_tag('{"tag_name": "v1.1.0", "draft": false}'), "v1.1.0")
        self.assertIsNone(L.latest_tag('{"tag_name": "v2.0.0-rc1", "prerelease": true}'))
        self.assertIsNone(L.latest_tag("not json"))

    def test_picons_and_chime(self):
        self.assertEqual(L.picon_name("Grüner Weg"), "grunerweg.png")
        self.assertEqual(L.picon_name("Tom & Jerry+*"), "tomandjerryplusstar.png")
        self.assertIsNone(L.picon_name("!!"))
        cmd = L.chime_command("/x/chime.wav")
        self.assertEqual(cmd[0], "gst-launch-1.0")
        self.assertIn("location=/x/chime.wav", cmd)
        self.assertEqual(cmd[-1], "alsasink")
        import wave
        w = wave.open(os.path.join(os.path.dirname(__file__), "..", "src", "CamAlert", "chime.wav"))
        self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 22050))
        self.assertLess(w.getnframes() / 22050.0, 2.0)

    def test_title_size(self):
        self.assertEqual(L.window_geometry("top_right", "medium", 1920, 1080, "large")[4], 56)
        self.assertEqual(L.window_geometry("top_right", "medium", 1280, 720)[4], 26)
        self.assertEqual(L.title_font("small", 1920), 22)


if __name__ == "__main__":
    unittest.main()
