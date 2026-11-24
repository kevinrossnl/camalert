"""The Enigma2 HTTP API adapter (server.Api.render -> camalert_core.api) driven through e2fake with a fake
Twisted request (#30).

The endpoint-by-endpoint behaviour is in tests/contract/test_http_contract.py (same table for Enigma2 and Kodi);
this file checks what only the Twisted adapter does: headers, the threaded camera list, POST bodies, errors.
"""
import unittest

import _paths  # noqa: F401
from contract.adapters import Enigma2Adapter, FakeTwistedRequest, Request
from fakes.controller import RecordingController


class TestEnigma2Server(unittest.TestCase):
    def setUp(self):
        self.a = Enigma2Adapter("openatv")

    def tearDown(self):
        self.a.close()

    def test_json_header_and_answer(self):
        ans = self.a.call(Request("/camalert/hide"))
        self.assertEqual((ans.code, ans.content_type, ans.body), (200, "application/json", {"result": True, "action": "hide"}))
        self.assertEqual(ans.ctl.calls, [("hide",)])

    def test_cameras_are_listed_in_a_thread(self):
        self.a.server.all_camera_names = lambda: ["front_door", "garden"]
        self.a.server.camera_urls = lambda n: ("rtsp://x/%s" % n, "http://x/%s.jpg" % n, n.title())
        ctl = RecordingController()
        ans = self.a.call(Request("/camalert/cameras"), ctl)
        self.assertEqual(ans.body["cameras"][1], {"name": "garden", "title": "Garden", "snapshot": True})
        self.assertEqual(ctl._names, ["front_door", "garden"])

    def test_camera_list_failure(self):
        def broken():
            raise OSError("down")
        self.a.server.all_camera_names = broken
        ans = self.a.call(Request("/camalert/cameras"))
        self.assertEqual(ans.body, {"result": False, "error": "camera source not reachable"})

    def test_post_form_and_headers(self):
        ans = self.a.call(Request("/camalert/show", {"cam": "garden"}, method="POST"))
        self.assertEqual((ans.code, ans.body["action"]), (200, "show"))
        self.assertNotIn("deprecation", ans.headers)
        ans = self.a.call(Request("/camalert/show", {"cam": "garden"}))
        self.assertEqual(ans.headers.get("deprecation"), "true")
        tw = FakeTwistedRequest(Request("/camalert/hide", method="POST"))
        self.a.display.Controller.instance = RecordingController()
        self.assertIsInstance(self.a.server.Api().render(tw), bytes)

    def test_internal_error_is_500(self):
        ctl = RecordingController()
        ctl.fail = "hide"
        ans = self.a.call(Request("/camalert/hide"), ctl)
        self.assertEqual((ans.code, ans.body), (500, {"result": False, "error": "internal error"}))

    def test_metrics_are_text(self):
        ans = self.a.call(Request("/camalert/metrics"))
        self.assertEqual(ans.content_type, "text/plain")
        self.assertIn("camalert_uptime_seconds", ans.body)

    def test_webhook_is_saved(self):
        ans = self.a.call(Request("/camalert/webhook", {"url": "http://192.168.1.20:8123/api/webhook/x"},
                                  settings={"ha_webhook": ""}))
        self.assertEqual(ans.body, {"result": True, "webhook": True})
        self.assertEqual(self.a.c.ha_webhook.value, "http://192.168.1.20:8123/api/webhook/x")
        self.assertIn("configfile.save", self.a.env.rec.names())


if __name__ == "__main__":
    unittest.main()
