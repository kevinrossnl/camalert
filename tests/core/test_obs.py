"""camalert_core.obs: log levels, redaction, syslog, camalert.log, metrics."""
import os
import tempfile
import unittest

import _paths

_paths.core()
from camalert_core.obs import camlog  # noqa: E402
from camalert_core.obs import metrics  # noqa: E402
from camalert_core.obs import log as obs_log  # noqa: E402
from camalert_core import urls  # noqa: E402


class TestObs(unittest.TestCase):
    def test_syslog(self):
        line = obs_log.syslog_line("shown rtsp://a:b@h/x", "error", "my box", 1795464900.25)
        self.assertEqual(line, "<131>1 2026-11-23T20:15:00.250Z my_box camalert - - - shown rtsp://***:***@h/x")
        self.assertTrue(obs_log.syslog_line("x", "normal", "h", 0).startswith("<134>1 "))
        self.assertEqual(urls.parse_hostport("10.0.0.9:1514"), ("10.0.0.9", 1514))
        self.assertEqual(urls.parse_hostport("loki.lan"), ("loki.lan", 514))
        self.assertIsNone(urls.parse_hostport(""))

    def test_metrics(self):
        text = metrics.metrics_text({"requests_total": ("counter", "Requests", {"show": 3}), "dnd": ("gauge", "DND", True),
                               "uptime_seconds": ("gauge", "Up", 12.5)}, {"version": "1.0.0"})
        self.assertIn("# TYPE camalert_requests_total counter", text)
        self.assertIn('camalert_requests_total{version="1.0.0",key="show"} 3', text)
        self.assertIn('camalert_dnd{version="1.0.0"} 1', text)
        self.assertIn('camalert_uptime_seconds{version="1.0.0"} 12.5', text)
        self.assertTrue(text.endswith("\n"))

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
            self.assertEqual(obs_log.redact(raw), want)
        self.assertEqual(obs_log.redact(None), "")

    def test_levels(self):
        self.assertTrue(obs_log.log_allowed("errors", "error"))
        self.assertFalse(obs_log.log_allowed("errors", "normal"))
        self.assertTrue(obs_log.log_allowed("normal", "normal"))
        self.assertFalse(obs_log.log_allowed("normal", "verbose"))
        self.assertTrue(obs_log.log_allowed("verbose", "verbose"))
        self.assertFalse(obs_log.log_allowed("off", "error"))

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


if __name__ == "__main__":
    unittest.main()
