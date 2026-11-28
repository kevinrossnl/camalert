"""#132: the problem report never contains secrets, and its issue link fits in a QR code."""
import json
import unittest

import _paths

_paths.core()
from camalert_core import qr, report, schema  # noqa: E402

SECRET = "s3cr3t-Pa55"


def full_settings():
    out = {}
    for s in schema.SETTINGS:
        out[s.id] = SECRET if s.type == "password" else s.default
    out.update({"token": SECRET, "ha_webhook": "http://192.168.1.5:8123/api/webhook/" + SECRET,
                "server": "http://user:%s@192.168.1.10:1984" % SECRET, "camera": "front_door"})
    return out


class TestReport(unittest.TestCase):
    def test_scrub(self):
        cases = {
            "rtsp://admin:%s@192.168.1.10/stream" % SECRET: SECRET,
            "token=%s&x=1" % SECRET: SECRET,
            "Authorization: Bearer %s" % SECRET: SECRET,
            "mail me at someone@example.com": "someone@example.com",
            "go2rtc at http://my.public-host.example:1984/api": "my.public-host.example",
            "reached 203.0.113.7 from outside": "203.0.113.7",
            "POST /api/webhook/abcDEF123": "abcDEF123",
        }
        for text, leak in cases.items():
            self.assertNotIn(leak, report.scrub(text), text)
        keep = "go2rtc http://192.168.1.10:1984 and http://homeassistant.local:8123, version 1.2.300.4"
        self.assertEqual(report.scrub(keep), keep)

    def test_build_has_no_secrets(self):
        status = {"result": True, "version": "1.4.0", "id": "00f1f52edd14", "platform": "kodi", "screen": "none",
                  "capabilities": ["show"], "mqtt": True}
        log = ["INFO started", "ERROR camera failed: rtsp://u:%s@192.168.1.10/x" % SECRET, "token=%s" % SECRET]
        rep = report.build(status, full_settings(), log, {"kodi": "21.3", "os": "LibreELEC 12"}, now=1795000000)
        dump = json.dumps(rep)
        self.assertNotIn(SECRET, dump)
        for sid in report.SECRET_IDS:
            self.assertNotIn(sid, rep["settings"])
        self.assertEqual(rep["status"]["id"], "00f1…")
        self.assertNotIn("capabilities", rep["status"])
        self.assertEqual(len(rep["errors"]), 1)
        self.assertEqual(rep["settings"]["camera"], "front_door")
        self.assertIn("CamAlert 1.4.0 on Kodi", report.text(rep))

    def test_issue_url_fits_a_qr_code(self):
        status = {"version": "1.4.0", "platform": "enigma2", "screen": "none"}
        log = ["ERROR " + "x" * 400] * 20
        rep = report.build(status, {}, log, {"model": "vusolo4k", "image": "openatv 8.0.1"}, now=0)
        url = report.issue_url(rep)
        self.assertLessEqual(len(url.encode()), report.URL_MAX)
        self.assertTrue(url.startswith(report.ISSUES_URL + "?template=bug_report.yml&player=Enigma2%20receiver"))
        self.assertIn("camalert_version=1.4.0", url)
        m = qr.encode(url, "M")
        self.assertLessEqual(len(m), 17 + 4 * 17)  # version 17 or lower: easy to scan from a TV

    def test_player_labels_match_the_issue_form(self):
        import os
        form = open(os.path.join(_paths.ROOT, ".github", "ISSUE_TEMPLATE", "bug_report.yml"), encoding="utf-8").read()
        for label in report.PLAYER_LABELS.values():
            self.assertIn(label, form)
        for field in ("player", "camalert_version", "player_version", "logs"):
            self.assertIn("id: %s" % field, form)


class TestQr(unittest.TestCase):
    def test_sizes_and_function_patterns(self):
        for text, level in (("a", "M"), ("x" * 100, "L"), ("x" * 500, "M")):
            m = qr.encode(text, level)
            n = len(m)
            self.assertEqual((n - 17) % 4, 0)
            for x, y in ((0, 0), (n - 7, 0), (0, n - 7)):  # finder patterns: dark 7x7 ring
                self.assertTrue(all(m[y][x + i] and m[y + 6][x + i] for i in range(7)))
        with self.assertRaises(qr.TooLong):
            qr.encode("x" * 3000, "M")

    def test_png(self):
        data = qr.png(qr.encode("CamAlert", "M"), scale=2, border=4)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
